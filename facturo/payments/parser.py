"""Payment PDF text -> structured fields. Pure: text in, dataclasses out.

Three layouts have been met in practice (synthetic mirrors live in
tests/fixtures/payments/text/):

  * quittance       — a client's proof of payment: a date line, the payer, a
                      "Quittance #" reference, one row per billet
                      (`<numero> <dd-mm-yyyy> <plaque>`) preceded by its
                      description line ending in `<qty> <price> $ <ext> $`, and
                      a labelled totals block with an early-payment escompte.
  * bill, inline    — a supplier bill addressed TO the company, labels next to values.
  * bill, scrambled — the same kind of bill whose text layer lists the amounts
                      far from their labels.

Only proofs of payment are imported. Bills addressed to the company (the name
set in facturo.brand.COMPANY_NAME) are still parsed (so the rejection message
can name them) and flagged `facture_adressee_entreprise`; the API refuses them.

`parse()` never raises: an unreadable field comes back blank / None so the user
fills it in, which is always safer than a confidently wrong value.
"""

import re
from dataclasses import dataclass
from itertools import combinations

from facturo.brand import company_key
from facturo.core.billet_fields import fold, normalize_date, tidy_plate

# Two amounts within this many dollars are "equal" (per-line cent rounding).
AMOUNT_TOLERANCE = 0.02
# Bare amounts considered when totals are found by arithmetic alone.
MAX_CONSISTENCY_CANDIDATES = 30

# The company name as it folds (accents, case, spacing, dots and legal suffix
# removed), so every spelling of it on a bill matches.
_COMPANY_FOLDED = company_key()

# Wording that marks a document as a proof of payment even when it lists no
# billet rows. Matched on folded text, so accents and spacing do not matter.
# "payment" alone is deliberately absent: bills say "make all payments payable".
_PAYMENT_WORDING = (
    "quittance", "avisdepaiement", "preuvedepaiement", "recudepaiement",
    "remittanceadvice", "paymentreceipt", "proofofpayment",
)

_EN_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_NUMERIC_DATE = re.compile(r"\d{1,2}-\d{1,2}-\d{4}")
_EN_DATE = re.compile(r"([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})")

# `<numero> <dd-mm-yyyy> <plaque>` — a billet row of the quittance layout.
_BILLET_ROW = re.compile(r"(\d[0-9A-Za-z-]{2,})\s+(\d{1,2}-\d{1,2}-\d{4})\s+([A-Za-z0-9 -]{2,})")
# A lone 1-3 digit line right under a billet row: the number column wrapped.
_WRAP_SUFFIX = re.compile(r"\d{1,3}")

# Trailing money on a totals line: FR "1 207,80 $" / "(200,00 $)" or EN "$2,345.67".
_FR_TRAILING = re.compile(r"(\(?)\s*(\d{1,3}(?:[   ]\d{3})*,\d{2})\s*\$\s*(\)?)\s*$")
_EN_TRAILING = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})*\.\d{2})\s*$")
_EN_ONLY_AMOUNT = re.compile(r"\$\s*\d{1,3}(?:,\d{3})*\.\d{2}")

_QTY_TOKEN = re.compile(r"\d+(?:,\d+)?")
_PRICE_GROUPED = re.compile(r"\d{1,3}(?: \d{3})*,\d{2}")


@dataclass(frozen=True)
class ParsedLigne:
    numero_billet: str                    # as printed (candidates[0])
    numero_candidates: tuple[str, ...]    # unjoined first, then joined wrap form
    date_billet: str                      # ISO yyyy-mm-dd, or "" if unreadable
    plaque: str                           # tidy_plate() applied
    quantite: float | None
    prix: float | None
    montant: float | None


@dataclass(frozen=True)
class ParsedDoc:
    facture_adressee_entreprise: bool     # a bill TO the company — not a proof of payment
    emetteur: str
    reference: str
    date: str                             # ISO, or ""
    sous_total: float | None              # tax base (after escompte)
    tps: float | None
    tvq: float | None
    escompte: float | None                # positive magnitude, None if absent
    total: float | None
    lignes: tuple[ParsedLigne, ...]


# ── Primitive readers ─────────────────────────────────────────────────────

def parse_amount(raw: str | None) -> float | None:
    """FR ("1 207,80 $") or EN ("$2,345.67") money -> float; None if unreadable.

    A parenthesized figure is negative (accounting convention for deductions).
    """
    s = str(raw or "").strip()
    if not s:
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "")
    s = re.sub(r"[\s  ]", "", s)
    if "," in s and "." in s:
        # Whichever separator comes last is the decimal one.
        if s.rfind(".") > s.rfind(","):
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # "312,45" is a decimal comma; "2,345" is an EN thousands separator.
        s = s.replace(",", "") if re.search(r",\d{3}$", s) else s.replace(",", ".")
    if not re.fullmatch(r"\d+(?:\.\d+)?", s):
        return None
    value = float(s)
    return -value if negative else value


def parse_header_date(raw: str | None) -> str:
    """FR numeric "22-09-2026" or EN "July 19, 2026" -> ISO; "" if unreadable."""
    s = str(raw or "").strip()
    if _NUMERIC_DATE.fullmatch(s):
        return normalize_date(s)
    m = _EN_DATE.fullmatch(s)
    if m and m.group(1).lower() in _EN_MONTHS:
        month = _EN_MONTHS[m.group(1).lower()]
        return normalize_date(f"{int(m.group(2))}-{month}-{m.group(3)}")
    return ""


# ── Header ────────────────────────────────────────────────────────────────

def _emetteur(lines: list[str]) -> str:
    """The first company line, stripped of the layout's trailing marker."""
    for line in lines:
        if _NUMERIC_DATE.fullmatch(line) or line.lower().startswith("quittance"):
            continue
        for marker in (" INVOICE", " Date:"):
            if line.endswith(marker):
                return line[: -len(marker)].strip()
        return line
    return ""


def _reference_and_date(text: str, lines: list[str]) -> tuple[str, str]:
    first_line_date = parse_header_date(lines[0]) if lines else ""
    m = re.search(r"Quittance\s*#\s*(\S+)", text)
    if m:
        return m.group(1), first_line_date

    date = ""
    m_date = re.search(r"DATE:[ \t]*([^\r\n]+)", text)
    if m_date:
        date = parse_header_date(m_date.group(1))

    m = re.search(r"INVOICE\s*#:[ \t]*(\S+)", text, re.IGNORECASE)
    if m:
        return m.group(1), date

    # Scrambled layout: a bare INVOICE marker, then the date, then the number.
    for i, line in enumerate(lines):
        if line == "INVOICE" and i + 2 < len(lines):
            return lines[i + 2], parse_header_date(lines[i + 1]) or date
    return "", date or first_line_date


# ── Totals ────────────────────────────────────────────────────────────────

def _trailing_amount(line: str) -> float | None:
    m = _FR_TRAILING.search(line)
    if m:
        value = parse_amount(m.group(2))
        in_parens = bool(m.group(1) and m.group(3))
        return -value if in_parens and value is not None else value
    m = _EN_TRAILING.search(line)
    return parse_amount(m.group(1)) if m else None


# Label -> field, checked in order on each line (first match wins).
_TOTAL_LABELS = (
    (re.compile(r"^TOTAL\b"), "total"),
    (re.compile(r"^S-T\.|^SUBTOTAL\b"), "sous_total"),
    (re.compile(r"^T\.P\.S\.|^TPS\b"), "tps"),
    (re.compile(r"^T\.V\.Q\.|^TVQ\b"), "tvq"),
    (re.compile(r"^Escompte\b", re.IGNORECASE), "escompte"),
)


def _labelled_totals(lines: list[str]) -> dict[str, float]:
    found: dict[str, float] = {}
    for line in lines:
        for label, field in _TOTAL_LABELS:
            if not label.search(line):
                continue
            amount = _trailing_amount(line)
            if amount is not None:
                found[field] = abs(amount)
            break
    return found


def _totals_by_consistency(lines: list[str]) -> dict[str, float] | None:
    """Pick subtotal/tps/tvq/total from bare amount lines by arithmetic alone.

    For text layers that print every amount far from its label: three amounts
    that add up to a fourth (within tolerance) are the subtotal and taxes.
    Among several such sets, the one with the largest total wins.
    """
    amounts = [parse_amount(line) for line in lines if _EN_ONLY_AMOUNT.fullmatch(line)]
    # The search is cubic in candidates times a scan: bound it. Totals are
    # printed at the end of a document, so the last distinct amounts are kept.
    distinct = list(dict.fromkeys(a for a in amounts if a is not None))
    values = distinct[-MAX_CONSISTENCY_CANDIDATES:]
    best: dict[str, float] | None = None
    for combo in combinations(range(len(values)), 3):
        addends = sorted((values[i] for i in combo), reverse=True)
        if min(addends) <= 0:
            continue
        others = (v for j, v in enumerate(values) if j not in combo)
        total = next((v for v in others if abs(v - sum(addends)) <= AMOUNT_TOLERANCE), None)
        if total is None or (best is not None and total <= best["total"]):
            continue
        tps, tvq = sorted(addends[1:])
        best = {"sous_total": addends[0], "tps": tps, "tvq": tvq, "total": total}
    return best


def _reconciles(t: dict[str, float]) -> bool:
    keys = ("sous_total", "tps", "tvq", "total")
    return all(k in t for k in keys) and \
        abs(t["sous_total"] + t["tps"] + t["tvq"] - t["total"]) <= AMOUNT_TOLERANCE


def _totals(lines: list[str]) -> dict[str, float]:
    totals = _labelled_totals(lines)
    if not _reconciles(totals):
        by_sum = _totals_by_consistency(lines)
        if by_sum:
            totals = {**totals, **by_sum}
    return totals


# ── Billet rows ───────────────────────────────────────────────────────────

def _trailing_numbers(text: str) -> list[str]:
    """The run of number tokens at the end of `text` ("Ch. Du 9 134,20" -> ["9", "134,20"])."""
    numbers: list[str] = []
    for token in reversed(text.split()):
        if not _QTY_TOKEN.fullmatch(token):
            break
        numbers.insert(0, token)
    return numbers


def _qty_price_ext(line: str) -> tuple[float | None, float | None, float] | None:
    """(qty, price, ext) from a description line ending in `<qty> <price> $ <ext> $`.

    The price may carry a thousands space ("1 207,80"), which makes "9 134,20"
    ambiguous between qty 9 / price 134,20 and price 9 134,20. The split whose
    qty x price lands on the printed extension wins; failing that, the
    ungrouped price is assumed.
    """
    stripped = line.rstrip()
    if not stripped.endswith("$") or stripped.count("$") < 2:
        return None
    before, ext_raw, _ = stripped.rsplit("$", 2)
    ext = parse_amount(ext_raw)
    numbers = _trailing_numbers(before)
    if ext is None or not numbers:
        return None

    splits = []
    for width in range(1, min(3, len(numbers)) + 1):
        price_raw = " ".join(numbers[-width:])
        if _PRICE_GROUPED.fullmatch(price_raw):
            qty_tokens = numbers[:-width]
            qty = parse_amount(qty_tokens[-1]) if qty_tokens else None
            splits.append((qty, parse_amount(price_raw)))
    if not splits:
        return None
    for qty, price in splits:
        if qty is not None and price is not None and \
                abs(qty * price - ext) <= max(0.05, ext * 0.005):
            return qty, price, ext
    qty, price = splits[0]
    return qty, price, ext


def _billet_lignes(lines: list[str]) -> tuple[ParsedLigne, ...]:
    lignes = []
    amounts: tuple[float | None, float | None, float | None] = (None, None, None)
    for i, line in enumerate(lines):
        parsed = _qty_price_ext(line)
        if parsed:
            amounts = parsed
            continue
        m = _BILLET_ROW.fullmatch(line)
        if not m:
            continue
        numero = m.group(1)
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        candidates = (numero, numero + nxt) if _WRAP_SUFFIX.fullmatch(nxt) else (numero,)
        qty, price, ext = amounts
        lignes.append(ParsedLigne(
            numero_billet=numero,
            numero_candidates=candidates,
            date_billet=normalize_date(m.group(2)),
            plaque=tidy_plate(m.group(3)),
            quantite=qty,
            prix=price,
            montant=ext,
        ))
        amounts = (None, None, None)
    return tuple(lignes)


# ── Whole document ────────────────────────────────────────────────────────

def _is_bill_to_company(text: str, has_billets: bool) -> bool:
    """A bill addressed to the company: names it, lists no billets, no payment wording.

    Billet rows always win — a quittance names the company too (as the payee).
    """
    if has_billets:
        return False
    folded = fold(text)
    if any(word in folded for word in _PAYMENT_WORDING):
        return False
    return _COMPANY_FOLDED in folded


def parse(text: str) -> ParsedDoc:
    text = text or ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    lignes = _billet_lignes(lines)
    reference, date = _reference_and_date(text, lines)
    totals = _totals(lines)
    return ParsedDoc(
        facture_adressee_entreprise=_is_bill_to_company(text, bool(lignes)),
        emetteur=_emetteur(lines),
        reference=reference,
        date=date,
        sous_total=totals.get("sous_total"),
        tps=totals.get("tps"),
        tvq=totals.get("tvq"),
        escompte=totals.get("escompte"),
        total=totals.get("total"),
        lignes=lignes,
    )

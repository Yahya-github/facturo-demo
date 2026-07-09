"""Turn what the model *said* about a billet into what goes on the invoice.

Everything here is pure: strings and numbers in, strings and numbers out, no
network and no Ollama. That is the point of the split — these are the functions
that quietly put a wrong plate or a wrong date on a real invoice when they get
it wrong, and keeping them free of I/O is what makes every one of them testable
without a GPU.

The recurring theme is that a billet is not read in isolation. Handwriting is
ambiguous, but this client's fleet, site list and calendar are not, so a value
that survives every format check can still be settled against what the business
already knows — see History, snap_plate and repair_year.
"""

import difflib
import re
import unicodedata
from collections.abc import Sequence
from datetime import date, timedelta
from typing import NamedTuple

# How far from the current year a billet date may plausibly fall, and so also
# how far back repair_year may reach when it rebuilds a misread year — past
# this, a hopeless read fails closed instead of landing on some date years ago.
#
# One year, not two. A billet is invoiced within weeks, so last year only ever
# turns up in January, for December's work. At two, a misread "2024" on a 2026
# ticket counted as plausible: near enough to skip repair, wrong enough to date
# the invoice two years back. That was a real miss, not a hypothetical.
PLAUSIBLE_YEARS = 1

# A billet records work already done, so it cannot be dated in the future. A few
# days of slack absorb a clock that is off or a driver writing tomorrow's date
# on a night shift, without letting repair_year pick a year that has not
# happened yet.
FUTURE_GRACE_DAYS = 7

# One billet is one shift, so hours past a long day mean the value was
# misparsed (a garbled "12h60" read as 1260, say) rather than genuinely worked.
MAX_PLAUSIBLE_HOURS = 24

_MONTHS_FR = {
    "janvier": 1, "janv": 1, "jan": 1,
    "fevrier": 2, "février": 2, "fev": 2, "fév": 2, "feb": 2,
    "mars": 3, "mar": 3,
    "avril": 4, "avr": 4, "apr": 4,
    "mai": 5, "may": 5,
    "juin": 6, "jun": 6,
    "juillet": 7, "juil": 7, "jul": 7,
    "aout": 8, "août": 8, "aug": 8,
    "septembre": 9, "sept": 9, "sep": 9,
    "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11,
    "decembre": 12, "décembre": 12, "dec": 12, "déc": 12,
}

class History(NamedTuple):
    """Values already billed on this client's past invoices.

    Handwriting is ambiguous; a trucking client's fleet and site list are not.
    The same trucks and the same renters come back billet after billet, so past
    invoices are a stronger authority on a plate or a name than a fresh read of
    someone's cursive. Snapping against them is what fixes the single-character
    misreads (a 7 read as a 9, an H read as an L) that no amount of prompt
    wording has moved.

    Empty by default so every caller — tests, the text endpoint, a fresh
    install with no invoices yet — works without history.
    """

    chantiers: Sequence[str] = ()
    plaques: Sequence[str] = ()

def normalize_date(raw: str) -> str:
    """Best-effort billet date -> YYYY-MM-DD (what the form's date input needs).

    The model is asked to transcribe the date exactly as written rather than to
    reformat it — asking for YYYY-MM-DD directly came back empty on every
    billet — so what arrives here is whatever the driver wrote: "23/06/2026",
    "25 6 2026", "29 JUIN 2026". Reformatting is this function's job.

    Anything that cannot be read confidently becomes "", which leaves the field
    blank for the user rather than silently filing a billet under the wrong
    day. The one exception is a year off by a single digit, which is repaired —
    see repair_year.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    # An already-ISO date still goes through every check below. The model is
    # asked to transcribe, but it sometimes reformats the date itself — and a
    # misread year is exactly as wrong in ISO form ("2016-06-25") as in any
    # other, so returning it as-is would let the one value we most need to
    # sanity-check be the one value that skips the sanity check.
    iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if iso:
        year, month, day = (int(g) for g in iso.groups())
    elif (m := re.search(
            r"(\d{1,2})\s*[/\-. ]\s*(\d{1,2})\s*[/\-. ]\s*(\d{2,4})", s)):
        day, month, year = (int(g) for g in m.groups())
    else:
        named = re.search(r"(\d{1,2})\s*(?:er)?\s+([A-Za-zéûôàÉÛÔÀ]+)\.?\s+(\d{2,4})", s)
        if not named:
            return ""
        month = _MONTHS_FR.get(named.group(2).strip(".").lower())
        if not month:
            return ""
        day, year = int(named.group(1)), int(named.group(3))

    if year < 100:
        year += 2000
    # Quebec billets are written day/month, so a month past 12 is a misread,
    # not a US-ordered date. Swapping the two "repairs" it into a real but
    # unrelated day — a 15 misread from 05 would silently become December —
    # so refuse it and let the user fill the field in.
    if month > 12:
        return ""
    try:
        parsed = date(year, month, day)
    except ValueError:
        return ""

    # A date that cannot belong to a billet being invoiced now is a misread.
    # Try to repair the year before giving up, then fall back to blank: an
    # invoice quietly dated ten years ago is worse than one the user has to
    # fill in, because a blank field is visible and a wrong date is not.
    if abs(parsed.year - date.today().year) > PLAUSIBLE_YEARS:
        repaired = repair_year(month, day)
        if repaired is None:
            return ""
        parsed = date(repaired, month, day)
    return parsed.isoformat()


def repair_year(month: int, day: int) -> int | None:
    """Rebuild a year the model misread, from the day and month it got right.

    The year is the fragile part of a handwritten date, and it fails in a
    different way every time: 2026 comes back as 2016 (a 2 read as a 1), as
    2023 (a 6 read as a 3), or truncated to "20". Guessing which digit slipped
    does not generalise. The day and month survive far better, and together
    with two facts about billets they settle the year on their own:

      * a billet records work already done, so it cannot be dated ahead of
        today; and
      * it is invoiced within weeks, so of the years that put this day/month in
        the recent past, the most recent one is what the driver wrote.

    That is the same common sense a person applies on seeing "22-06-2023" in a
    stack being invoiced today — nobody reaches for a three-year-old ticket.
    Returns None when no year in the plausible window works, leaving the field
    blank for the user rather than inventing a date.
    """
    today = date.today()
    latest = today + timedelta(days=FUTURE_GRACE_DAYS)
    candidates = []
    for year in range(today.year - PLAUSIBLE_YEARS, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue  # 29 February outside a leap year
        if candidate <= latest:
            candidates.append(candidate)
    return max(candidates).year if candidates else None


# Letters the model substitutes for digits when reading handwriting. Applied
# only inside a plate's numeric tail, where a letter cannot be correct.
_DIGIT_LOOKALIKES = str.maketrans({
    "O": "0", "Q": "0", "D": "0",
    "I": "1", "L": "1",
    "Z": "2",
    "S": "5",
    "G": "6",
    "T": "7",
    "B": "8",
})


# difflib's ratio is length-sensitive: one wrong letter clears 0.85 in a
# seven-letter name (foxdale/roxdale = 0.857) and misses in a six-letter one
# (kalrog/kalroc = 0.833). Measured against a real billet history, an
# explicit edit-distance rule recovers Norlx->NORIX, KALROG->KALROC and
# SOLTEC->SOLTEK, which the ratio missed. Below this length the neighbourhood
# is too crowded to guess — "QBS" is one character from "QDS".
MIN_SNAP_LEN = 5


def _near1(a: str, b: str) -> bool:
    """True when exactly one edit — substitute, insert or delete — separates a and b.

    Distance 0 is deliberately False: callers ask this only after an exact
    match has already been ruled out, so "identical" is not a near miss.
    Unlike a similarity ratio, this does not care how long the strings are,
    which is the whole point of using it.
    """
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    if la > lb:                      # walk the shorter string as `a`
        a, b, la, lb = b, a, lb, la
    i = j = skipped = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = 1
            j += 1
    return True


def fold(s: str) -> str:
    """Accent-, case- and punctuation-insensitive identity key for a value.

    Two strings that fold alike are the same thing written differently:
    "L A HÉNARD", "La Henard" and "l a henard" all fold to "lahenard", and
    "FK 68113" folds to the same key as "FK68113". That is what lets one stored
    row stand for every spelling of one client or one truck.
    """
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s)


# Words that only ever appear in a work address, never in a renter's name.
_STREET_WORDS = re.compile(
    r"\b(ch|chemin|rue|boul|boulevard|av|avenue|route|rang|autoroute|"
    r"aeroport|montreal|mtl|laval|anjou)\b",
    re.I,
)


def clean_chantier(raw: str) -> str:
    """Strip the aside a driver adds after the renter's name.

    The invoice lists the renter as a bare name ("NORIX"), so "NORIX (equipe
    pavage)" has to lose its parenthetical or split-by-chantier treats the two
    spellings as two different sites. The closing bracket is optional on
    purpose: drivers run out of line and simply stop writing, so "NORIX (equipe
    pavage" — with nothing to close it — is the form that actually turns up.
    """
    return re.sub(r"\s*\([^)]*(\)|$)", "", raw or "").strip()


def looks_like_address(text: str) -> bool:
    """True when a renter name is really the work address from the line below.

    The model sometimes answers the renter slot with the next line down, and
    leaves lieu_travail empty — so there is nothing to compare against and the
    answer looks perfectly well-formed. What gives it away is the shape: a
    renter is a person or a company, while an address carries a civic number or
    a street word. "7400 CH DU LAC NORD" is not a client, whatever the
    model thinks; and it stays detectable when misread as "T400CH DU LAC NORD".
    """
    text = text or ""
    return bool(_STREET_WORDS.search(text) or re.match(r"\s*\S*\d{3,}", text))


def snap_chantier(name: str, known: Sequence[str]) -> str:
    """Correct a renter name against the spellings already used on past invoices.

    The same handful of names recur across billets, so the client's own history
    is a better authority than a fresh read of someone's cursive: "La Lenard"
    is a misread H, and the invoices already say "La Henard". Snapping also
    keeps the split-by-chantier grouping from treating two spellings of one site
    as two sites.

    Only near-misses are snapped — a genuinely new name is left exactly as read.
    """
    if not name or not known:
        return name
    folded = {fold(k): k for k in known if k.strip()}
    key = fold(name)
    if not key:
        return name
    if key in folded:
        return folded[key]

    # One edit away, and only one candidate at that distance. This runs ahead
    # of the ratio match because the ratio silently resolves a tie by score:
    # with both "Terra" and "Terral" on file it picks Terra for "terra1" on
    # 0.909 vs 0.833, which is a coin flip wearing a number. Two candidates one
    # edit apart means we genuinely cannot tell, so stop here rather than fall
    # through and let the ratio guess.
    if len(key) >= MIN_SNAP_LEN:
        near = [v for k, v in folded.items() if _near1(k, key)]
        if near:
            return near[0] if len(near) == 1 else name

    close = difflib.get_close_matches(key, folded.keys(), n=1, cutoff=0.85)
    return folded[close[0]] if close else name


# What a cleaned Quebec truck plate looks like: 1-2 letters then digits. Used
# to tell a real plate from whatever else ended up in the field ("S/O", "0000",
# an hours value typed into the wrong box) before trusting it as history.
_IS_PLATE = re.compile(r"[A-Z]{1,2}\d{4,7}")


def is_plate(value: str) -> bool:
    """Whether a cleaned value really is a Quebec truck plate.

    The gate that keeps "S/O", "0000" and a stray hours value out of the fleet
    — both when snapping a read and when deciding what may enter the shop's
    known-value list.
    """
    return bool(_IS_PLATE.fullmatch(value or ""))


def clean_plate(raw: str) -> str:
    """Normalise a Quebec truck plate: 1-2 letters then 5-6 digits.

    The shape is fixed, so a letter appearing where a digit belongs is always a
    misread — 'K86424S' is 'K864245'. Fixing it here beats asking the model to
    be more careful, because the constraint is ours to enforce, not its to
    guess. Anything not matching the shape is passed through untouched rather
    than mangled.
    """
    s = re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()
    m = re.fullmatch(r"([A-Z]{1,2})([A-Z0-9]{4,7})", s)
    if not m:
        return s
    head, tail = m.group(1), m.group(2).translate(_DIGIT_LOOKALIKES)
    return head + tail if tail.isdigit() else s


def snap_plate(plate: str, known: Sequence[str]) -> str:
    """Correct a plate against the plates already billed — snap_chantier for trucks.

    A plate is a fixed shape carrying no redundancy, so a single misread digit
    ("FK68893" for "FK68873") passes every format check we can apply and reaches
    the invoice looking perfectly valid. The client's fleet is small and
    recurring, though, so its own history settles it: snap to a billed plate
    that differs in exactly one character.

    Two guards stop this from rewriting history rather than reading it:

      * a plate that is already in the fleet is returned untouched. K864245 and
        K864249 are both real trucks, and "correcting" the rare one into the
        common one would turn a right answer into a wrong one.
      * a read sitting one character from two different known plates is left
        alone, because picking between them would be a coin flip.
    """
    if not plate or not known:
        return plate
    fleet = {p for p in (clean_plate(k) for k in known) if _IS_PLATE.fullmatch(p)}
    if plate in fleet or len(plate) < MIN_SNAP_LEN:
        return plate
    # The input is NOT required to be plate-shaped. "K8642A5" is a real read —
    # an A where a 4 belongs, a letter clean_plate's lookalike map does not
    # cover — and refusing to compare it was why the one candidate a single
    # edit away never got found. The *candidates* are all plate-shaped, which
    # is the guard that matters.
    near = [p for p in fleet if _near1(p, plate)]
    return near[0] if len(near) == 1 else plate


# ── Values a person typed ────────────────────────────────────────────────
#
# Distinct from the clean_* functions above, and the difference is
# load-bearing: clean_* repairs an OCR MISREAD, so it may rewrite a letter the
# model produced (an S where a 5 belongs). tidy_* normalises what a PERSON
# typed, where a letter is a letter they meant. Applying the lookalike map to
# hand-typed input would corrupt it.
#
# These exist because cleaning used to be reachable only from the AI path,
# which is how one truck ended up in the history twice as "FK68113" (12 uses)
# and "FK 68113" (5 uses) — the space can only survive a manual entry.


def tidy_chantier(raw: str) -> str:
    """Trim, and collapse runs of whitespace. Nothing else.

    Deliberately not clean_chantier: a parenthetical the model hallucinated is
    noise, but one a person typed is a decision. Case and accents are left
    alone too — which spelling wins is settled visibly, by the known-values
    list, not silently here.
    """
    return " ".join(str(raw or "").split())


def tidy_plate(raw: str) -> str:
    """Compact a typed plate to its canonical shape — but only if it is one.

    The shape gate is what makes this safe. "FK 68113" and "FK68113" are one
    truck written two ways and should converge; "S/O" and "PAS DE PLAQUE" are
    the user saying there is no plate, and mangling those into "SO" would
    invent a truck. So separators are stripped only when what remains actually
    looks like a plate.
    """
    s = " ".join(str(raw or "").split())
    if not s:
        return ""
    compact = re.sub(r"[^A-Za-z0-9]", "", s).upper()
    return compact if _IS_PLATE.fullmatch(compact) else s


# Decoration printed around a billet number: "No. 50742", "N° 4211", "#50742".
_NUMERO_DECORATION = re.compile(r"^[#Nn°noO.:\s-]*$")

# A job/contract number, which the billet number is not. The extraction schema
# warns the model about these twice (ai_extract.py) because they sit right next
# to the real number on the ticket.
_PROJECT_NUMBER = re.compile(r"^#?\d{2}-\d{2,4}$")


def tidy_billet_number(raw: str) -> str:
    """Strip the decoration around a printed billet number, or refuse it.

    Returns a STRING, never an int: "04231" and "4231" are different billets
    and the leading zero is part of the number as printed.

    A project number ("#26-112") is rejected outright rather than salvaged. A
    wrong billet number is worse than a blank one — it is what the duplicate
    check keys on — which is the same reasoning that makes normalize_date
    refuse a month past 12 instead of swapping the fields.
    """
    s = " ".join(str(raw or "").split())
    if not s:
        return ""
    if _PROJECT_NUMBER.fullmatch(s):
        return ""
    digits = re.sub(r"\D", "", s)
    if 3 <= len(digits) <= 7 and _NUMERO_DECORATION.fullmatch(re.sub(r"\d", "", s)):
        return digits
    return s


def canonical_spelling(spellings: Sequence[tuple[str, int]]) -> str:
    """Pick the one spelling to show for a group of variants of the same value.

    Has to be deterministic, or the displayed name would drift with dictionary
    iteration order. Ranked by:

      1. most used     — the shop's own habit outvotes any rule of ours.
      2. most accents  — "L A HÉNARD" over "L A HENARD": dropping an accent is
                         a keyboard shortcut, adding one is a decision.
      3. most capitals — "EXCAVATION NORTHWIND" over "excavation northwind", "QDS"
                         over "qds". These are hand-printed in caps on the
                         tickets, and most of the frequent spellings already
                         are.
      4. alphabetical  — a backstop so the answer never depends on ordering.

    The user overrides all four by editing the value, which marks it curated
    and stops it ever being recomputed.
    """
    def rank(item: tuple[str, int]) -> tuple:
        value, count = item
        decomposed = unicodedata.normalize("NFD", value)
        accents = sum(1 for c in decomposed if unicodedata.combining(c))
        capitals = sum(1 for c in value if c.isupper())
        return (-count, -accents, -capitals, value)

    return min(spellings, key=rank)[0]


def to_number(value) -> float:
    """Parse an hours value as written on a billet.

    Two notations appear, and confusing them is expensive:

      * decimal, comma-separated   '8,25' '10,5 h' '6,5H'  -> 8.25 10.5 6.5
      * hours and MINUTES          '9h15' '6h45' '10 h 30' -> 9.25 6.75 10.5

    In the second form 'h' separates hours from minutes rather than marking a
    unit, so reading '9h15' as 9.15 — or as 915 — silently mis-bills the
    client; some bulk-hauling suppliers write every billet this way. A decimal comma
    disambiguates: '6,5H' is six and a half hours, never six hours five.
    """
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value or "").strip()
    if not s:
        return 0.0

    # "7h Minimum" is a contractual floor, not a computed total; the number in
    # front of it is still the hours to bill, so let it fall through to the
    # plain-number path rather than trying to read "Minimum" as minutes.
    s = re.sub(r"\bminimum\b", "", s, flags=re.I).strip()

    # Hours + minutes: 'h' (or ':') BETWEEN two numbers, and no decimal comma.
    # A trailing unit letter is optional and varies: 9h30, 9h30m, 9:15, 10h00.
    if "," not in s:
        m = re.fullmatch(r"\s*(\d{1,2})\s*[hH:]\s*(\d{1,2})\s*(?:m|min|h)?\.?\s*", s)
        if m:
            hours, minutes = int(m.group(1)), int(m.group(2))
            if minutes >= 60:
                # Not a readable clock value ("12h60" — most likely a misread
                # "12h00"). Falling through would strip the 'h' and hand back
                # 1260, so refuse instead: an empty hours cell is caught by the
                # user, a 1260-hour line is not.
                return 0.0
            return round(hours + minutes / 60, 4)

    s = re.sub(r"[^\d,.\-]", "", s.replace(",", "."))
    # A stray thousands separator would otherwise parse as a decimal point.
    if s.count(".") > 1:
        head, _, tail = s.rpartition(".")
        s = head.replace(".", "") + "." + tail
    try:
        return float(s)
    except ValueError:
        return 0.0

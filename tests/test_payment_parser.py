"""Unit tests for payments.parser — payment PDF text -> structured fields.

Pure text-in, dataclass-out: no I/O, no database. Three synthetic fixtures
mirror the three real-world payment layouts encountered (see
tests/fixtures/payments/text/), and the real gitignored samples get a light
structural check on top (skipped when absent, e.g. in CI or a fresh clone)
without ever hardcoding a real name or dollar amount into this tracked file —
only counts, formats and cross-field consistency are asserted for those.

See changes/team-c.md for the full parser contract (dataclass shapes, the
emetteur/reference/date extraction rules per layout, and the totals
reconciliation rule for the "scrambled" layout).
"""

import re
from pathlib import Path

import pytest

from facturo.payments import parser

FIXTURES = Path(__file__).parent / "fixtures" / "payments" / "text"
REAL_PDF_DIR = Path(__file__).parent / "fixtures" / "payments" / "pdf"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _real_pdf_text(filename: str) -> str:
    """Extract text from a gitignored real sample the same way pdf_text will.

    Kept independent of facturo.payments.pdf_text on purpose: pdf_text is a
    separate module under test elsewhere, and this helper must keep working
    even before pdf_text exists.
    """
    pypdfium2 = pytest.importorskip("pypdfium2")
    doc = pypdfium2.PdfDocument(str(REAL_PDF_DIR / filename))
    return "\n".join(
        doc.get_page(i).get_textpage().get_text_range() for i in range(len(doc))
    )


def _skip_if_missing(filename: str) -> None:
    if not (REAL_PDF_DIR / filename).exists():
        pytest.skip(f"real sample not present: {filename} (gitignored, dev-machine only)")


ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
PLATE_SHAPE = re.compile(r"[A-Z]{1,2}[0-9]{4,7}")


# ── parse_amount: FR/EN money parsing ─────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("1 207,80 $", 1207.80),          # FR thousands space + comma decimal
    ("134,20 $", 134.20),
    ("4 000,00 $", 4000.00),
    ("312,45 $", 312.45),
    ("$2,345.67", 2345.67),           # EN thousands comma + dot decimal
    ("$0.00", 0.0),
    ("$3,679.20", 3679.20),
    ("312,45", 312.45),               # no trailing $ sign
    ("  1 000,00  $  ", 1000.00),     # surrounding whitespace
])
def test_parse_amount_reads_fr_and_en_money(raw, expected):
    assert parser.parse_amount(raw) == pytest.approx(expected, abs=0.001)


def test_parse_amount_treats_parentheses_as_negative():
    """Accounting convention: a parenthesized figure is a deduction.

    Used for the escompte line ("Escompte 5% (312,45 $)"); the sign lets the
    full-document parser take the magnitude for the escompte field while still
    letting parse_amount be tested as a plain, generic money reader.
    """
    assert parser.parse_amount("(312,45 $)") == pytest.approx(-312.45, abs=0.001)


@pytest.mark.parametrize("raw", ["", "   ", "n/a", "abc", None])
def test_parse_amount_returns_none_for_unreadable_input(raw):
    assert parser.parse_amount(raw) is None


# ── parse_header_date: FR numeric + EN month-name dates -> ISO ───────────

@pytest.mark.parametrize("raw, expected", [
    ("22-09-2026", "2026-09-22"),
    ("21-09-2026", "2026-09-21"),
    ("July 19, 2026", "2026-07-19"),
    ("August 3, 2026", "2026-08-03"),
    ("August 12, 2026", "2026-08-12"),
])
def test_parse_header_date_reads_fr_numeric_and_en_month_name(raw, expected):
    assert parser.parse_header_date(raw) == expected


@pytest.mark.parametrize("raw", ["", "not a date", "Quittance # 220-451"])
def test_parse_header_date_blanks_what_it_cannot_read(raw):
    assert parser.parse_header_date(raw) == ""


# ── Proof of payment vs. bill addressed to the company ──────────────────────────
#
# User decision (spec change): only proofs of payment are imported. A bill
# addressed TO the company is still parsed, but flagged `facture_adressee_entreprise` so the
# API can refuse it with a clear message.

def test_billet_rows_mean_a_proof_of_payment():
    doc = parser.parse(_read("quittance.txt"))
    assert doc.facture_adressee_entreprise is False


def test_billed_to_company_with_no_billets_is_flagged_as_a_bill():
    doc = parser.parse(_read("bill_labels_inline.txt"))
    assert doc.facture_adressee_entreprise is True
    doc2 = parser.parse(_read("bill_labels_scrambled.txt"))
    assert doc2.facture_adressee_entreprise is True


def test_quittance_keyword_with_no_billet_rows_is_a_proof_of_payment():
    """'Quittance' alone (no billet rows on this particular document) still
    marks a payment, even when the company is named on it."""
    text = ("01-09-2026\nEmetteur Fictif Inc.\nQuittance # 999-000\n"
            "DEMO TRANSPORT INC.\nMontant recu: 500,00 $\n")
    assert parser.parse(text).facture_adressee_entreprise is False


def test_payments_payable_wording_on_a_bill_does_not_make_it_a_payment():
    """Bills say "make all payments payable to ..." — that is not payment wording."""
    text = ("FOURNISSEUR FICTIF INC. INVOICE\nBILL TO:\nDEMO TRANSPORT INC.\n"
            "Please make all payments payable to Fournisseur Fictif Inc.\nTOTAL $10.00\n")
    assert parser.parse(text).facture_adressee_entreprise is True


def test_unrecognized_text_is_not_flagged_as_a_bill():
    """Nothing names the company as the recipient: not refused as a bill (the user can
    still add billet lines by hand)."""
    doc = parser.parse("Ceci est un texte quelconque sans structure connue.")
    assert doc.facture_adressee_entreprise is False
    assert doc.lignes == ()


def test_ba_mention_is_ignored_when_billet_rows_are_present():
    """The quittance's own noise block also names the company (the payee) — billet
    rows must still win over the bill heuristic."""
    doc = parser.parse(_read("quittance.txt"))
    assert "DEMO TRANSPORT INC." in _read("quittance.txt")  # sanity: noise present
    assert doc.facture_adressee_entreprise is False


# ── Quittance layout (paiement, FR money, billet rows, escompte) ─────────

class TestQuittanceFixture:
    @pytest.fixture(scope="class")
    @classmethod
    def doc(cls):
        return parser.parse(_read("quittance.txt"))

    def test_header_fields(self, doc):
        assert doc.emetteur == "Vrac Horizon (1234-5678 Qc inc.)"
        assert doc.reference == "220-451"
        assert doc.date == "2026-09-21"

    def test_totals(self, doc):
        assert doc.sous_total == pytest.approx(3800.00, abs=0.01)
        assert doc.tps == pytest.approx(190.00, abs=0.01)
        assert doc.tvq == pytest.approx(379.05, abs=0.01)
        assert doc.escompte == pytest.approx(200.00, abs=0.01)
        assert doc.total == pytest.approx(4369.05, abs=0.01)

    def test_totals_reconcile(self, doc):
        assert doc.sous_total + doc.tps + doc.tvq == pytest.approx(doc.total, abs=0.02)

    def test_four_billet_lines_extracted(self, doc):
        assert len(doc.lignes) == 4

    def test_first_line_plain_numero_no_noise_number_confusion(self, doc):
        """'Ch. Du 4' is address-shaped noise, but its number IS this row's
        real quantity (it directly precedes the price/$ pair) — mirrors the
        real quittance's 'Ch. Du 9' row exactly."""
        ligne = doc.lignes[0]
        assert ligne.numero_billet == "50210"
        assert ligne.numero_candidates == ("50210",)
        assert ligne.date_billet == "2026-09-12"
        assert ligne.plaque == "G123456"
        assert ligne.quantite == pytest.approx(4.0)
        assert ligne.prix == pytest.approx(250.00)
        assert ligne.montant == pytest.approx(1000.00)

    def test_wrapped_billet_number_yields_both_candidates(self, doc):
        ligne = doc.lignes[1]
        assert ligne.numero_billet == "50211"
        assert ligne.numero_candidates == ("50211", "502113")
        assert ligne.date_billet == "2026-09-12"
        assert ligne.plaque == "G123456"
        assert ligne.quantite == pytest.approx(5.0)
        assert ligne.prix == pytest.approx(200.00)
        assert ligne.montant == pytest.approx(1000.00)

    def test_decimal_quantity_and_leading_noise_number_ignored(self, doc):
        """'12 roues' precedes the qty/price/ext numbers on this row; the
        leading noise '12' must not be picked up as the quantity."""
        ligne = doc.lignes[2]
        assert ligne.numero_billet == "50212"
        assert ligne.date_billet == "2026-09-13"
        assert ligne.plaque == "LE99999"
        assert ligne.quantite == pytest.approx(8.5)
        assert ligne.prix == pytest.approx(100.00)
        assert ligne.montant == pytest.approx(850.00)

    def test_fourth_line(self, doc):
        ligne = doc.lignes[3]
        assert ligne.numero_billet == "50213"
        assert ligne.date_billet == "2026-09-14"
        assert ligne.plaque == "LE99999"
        assert ligne.quantite == pytest.approx(10.0)
        assert ligne.prix == pytest.approx(115.00)
        assert ligne.montant == pytest.approx(1150.00)

    def test_no_ligne_carries_a_client_or_chantier_field(self, doc):
        """The matcher never keys on client/chantier text, so the parser
        does not even expose it on a ligne — only the matching keys do."""
        for ligne in doc.lignes:
            assert not hasattr(ligne, "client")
            assert not hasattr(ligne, "chantier")


# ── Bill layouts (refused on import, but still parsed so the refusal can
#    name the document; also exercises the generic header/totals rules) ────

# ── Bill layout: labels inline with their values, EN money ───────────────

class TestBillLabelsInlineFixture:
    @pytest.fixture(scope="class")
    @classmethod
    def doc(cls):
        return parser.parse(_read("bill_labels_inline.txt"))

    def test_header_fields(self, doc):
        assert doc.emetteur == "1234-5678 QUEBEC INC."
        assert doc.reference == "260803-07"
        assert doc.date == "2026-08-03"

    def test_totals(self, doc):
        assert doc.sous_total == pytest.approx(2600.00, abs=0.01)
        assert doc.tps == pytest.approx(130.00, abs=0.01)
        assert doc.tvq == pytest.approx(259.35, abs=0.01)
        assert doc.total == pytest.approx(2989.35, abs=0.01)
        assert doc.escompte is None

    def test_no_billet_lines(self, doc):
        assert doc.lignes == ()


# ── Bill layout: amounts before labels, disconnected header fields ───────

class TestBillLabelsScrambledFixture:
    @pytest.fixture(scope="class")
    @classmethod
    def doc(cls):
        return parser.parse(_read("bill_labels_scrambled.txt"))

    def test_header_fields(self, doc):
        assert doc.emetteur == "99887766 CANADA INC./ FAUXCORP INC."
        assert doc.reference == "INV-FAUX-20260812-003"
        assert doc.date == "2026-08-12"

    def test_totals_found_by_consistency_not_label_adjacency(self, doc):
        """None of these values sits next to its label in the source text —
        only the arithmetic (subtotal + tps + tvq == total) picks them out."""
        assert doc.sous_total == pytest.approx(3200.00, abs=0.01)
        assert doc.tps == pytest.approx(160.00, abs=0.01)
        assert doc.tvq == pytest.approx(319.20, abs=0.01)
        assert doc.total == pytest.approx(3679.20, abs=0.01)

    def test_no_billet_lines(self, doc):
        assert doc.lignes == ()


# ── Real samples (gitignored; skipped when absent) ────────────────────────
#
# No literal business name, invoice number or dollar figure from these files
# is ever written into this tracked test — only structure: row counts, ISO
# date/plate shapes, and cross-field arithmetic consistency, computed at run
# time from whatever the real PDF's text layer actually contains.

class TestRealQuittance:
    FILE = "With Billet.PDF"

    @pytest.fixture(scope="class")
    @classmethod
    def doc(cls):
        _skip_if_missing(cls.FILE)
        return parser.parse(_real_pdf_text(cls.FILE))

    def test_is_a_proof_of_payment(self, doc):
        assert doc.facture_adressee_entreprise is False

    def test_has_a_non_empty_reference_and_emitter(self, doc):
        assert doc.emetteur.strip() != ""
        assert doc.reference.strip() != ""
        assert ISO_DATE.fullmatch(doc.date)

    def test_ten_billet_rows(self, doc):
        """Verified directly against the sample's text layer: 10 lines match
        the `<numero> <dd-mm-yyyy> <plaque>` billet-row shape."""
        assert len(doc.lignes) == 10

    def test_two_rows_have_a_wrapped_numero_with_two_candidates(self, doc):
        wrapped = [ligne for ligne in doc.lignes if len(ligne.numero_candidates) > 1]
        assert len(wrapped) == 2
        for ligne in wrapped:
            assert ligne.numero_billet in ligne.numero_candidates
            assert all(c.isdigit() for c in ligne.numero_candidates)
            # the wrap is a lone trailing digit joined onto the printed number
            joined = max(ligne.numero_candidates, key=len)
            unjoined = min(ligne.numero_candidates, key=len)
            assert joined.startswith(unjoined)
            assert len(joined) == len(unjoined) + 1

    def test_every_ligne_has_well_formed_date_and_plate(self, doc):
        for ligne in doc.lignes:
            assert ISO_DATE.fullmatch(ligne.date_billet)
            assert PLATE_SHAPE.fullmatch(ligne.plaque)
            assert ligne.quantite is not None and ligne.quantite > 0
            assert ligne.prix is not None and ligne.prix > 0
            assert ligne.montant is not None and ligne.montant > 0

    def test_totals_reconcile(self, doc):
        assert doc.sous_total is not None and doc.tps is not None
        assert doc.tvq is not None and doc.total is not None
        assert doc.sous_total + doc.tps + doc.tvq == pytest.approx(doc.total, abs=0.02)

    def test_escompte_present_and_accounts_for_the_gap_to_line_total(self, doc):
        """The quittance takes a 5% early-payment discount: sous_total plus
        the escompte should land close to the sum of the line montants
        (never asserted as an exact figure, since real-world per-line
        rounding means it will not match to the cent)."""
        assert doc.escompte is not None and doc.escompte > 0
        line_sum = sum(ligne.montant for ligne in doc.lignes)
        assert doc.sous_total + doc.escompte == pytest.approx(line_sum, rel=0.01)


def _real_bill_filenames() -> list[str]:
    """Real bills addressed to the company (refused on import), discovered by extension casing
    (lowercase ".pdf") rather than a hardcoded filename: the actual filenames
    on disk are literally the real documents' own invoice numbers, which must
    never be written into this tracked file (see the "never copy... amounts"
    rule) — the quittance sample uses ".PDF" and is excluded by this glob.
    """
    if not REAL_PDF_DIR.exists():
        return []
    return sorted(p.name for p in REAL_PDF_DIR.glob("*.pdf"))


@pytest.mark.parametrize("filename", _real_bill_filenames() or [None])
class TestRealBillsToCompany:
    @pytest.fixture
    def doc(self, filename):
        if filename is None:
            pytest.skip("real samples not present (gitignored, dev-machine only)")
        return parser.parse(_real_pdf_text(filename))

    def test_is_flagged_as_a_bill_to_company(self, doc):
        assert doc.facture_adressee_entreprise is True

    def test_no_billet_lines(self, doc):
        assert doc.lignes == ()

    def test_has_a_non_empty_reference_emitter_and_iso_date(self, doc):
        assert doc.emetteur.strip() != ""
        assert doc.reference.strip() != ""
        assert ISO_DATE.fullmatch(doc.date)

    def test_totals_reconcile(self, doc):
        assert doc.sous_total is not None and doc.tps is not None
        assert doc.tvq is not None and doc.total is not None
        assert doc.sous_total + doc.tps + doc.tvq == pytest.approx(doc.total, abs=0.02)


def test_many_bare_amounts_are_reconciled_quickly():
    """The consistency search was O(n^4): a few hundred bare amounts took minutes."""
    import time

    noise = [f"$ {1 + i * 0.07:.2f}" for i in range(400)]  # distinct, all small
    totals_tail = ["$ 1,000.00", "$ 50.00", "$ 99.75", "$ 1,149.75"]
    started = time.monotonic()
    found = parser._totals_by_consistency(noise + totals_tail)
    assert time.monotonic() - started < 2.0
    assert found == {"sous_total": 1000.0, "tps": 50.0, "tvq": 99.75, "total": 1149.75}

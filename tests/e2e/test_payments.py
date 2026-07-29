"""Playwright E2E tests for the Paiements tab.

Runs against the real live app (see tests/e2e/conftest.py): a session-scoped
server seeded with one client ("CLIENT TEST INC") and one invoice, billet
numero_billet="900001", date_billet="2026-09-01", plaque="L 123456",
quantite=8. These tests build small, real, synthetic PDFs on disk (via
tests/helpers/pdf_writer.make_text_pdf — no real sample file, no external PDF
library) and upload them through the actual file input, so the whole pipeline
(pdf_text -> parser -> matcher -> store -> API -> UI) runs for real.

Tests are ordered and share the session server on purpose (same pattern as
test_smoke.py's history-lists-seeded-invoice test): each test's setup is
whatever came before it in this file.

User decision (spec change): only proofs of payment are imported; a bill
addressed to the company is refused with a French message and nothing is stored.

DOM CONTRACT locked down by this file (see changes/team-c.md for the full
write-up):
  #payments-search                                          — free-text search
  #btn-import-payment, #payment-file-input (hidden, multiple, accept=.pdf)
  #payments-list, .payment-row[data-id]
  #payment-detail                                           — detail panel
  .ligne-row[data-ligne-id], .ligne-status.status-lie|status-a-verifier|status-doublon
  .btn-link-ligne[data-ligne-id] -> #ligne-link-picker
      #ligne-link-facture-select (option value = facture_id)
      #ligne-link-billet-select  (option value = billet_index)
      #ligne-link-confirm
  .billet-payment-badge[data-paiement-id]                   — on the invoice form
"""

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

from tests.helpers.pdf_writer import make_text_pdf  # noqa: E402

QUITTANCE_MATCH_SEEDED = "\n".join([
    "01-09-2026",
    "Import E2E Inc. (0000-0000 Qc inc.)",
    "1 rue Test",
    "Ville, QC H0H 0H0",
    "Quittance # 900-001",
    "BILLET DATE IMMAT CLIENT / CHANTIER / NOTES QTE PRIX EXT",
    "CLIENT E2E INC. / Chantier A 8 120,00 $ 960,00 $",
    "900001 01-09-2026 l123456",
    "TOTAL: 960,00 $",
])

BILL_RECUE = "\n".join([
    "9999-0000 QUEBEC INC. INVOICE",
    "DATE: September 2, 2026",
    "INVOICE #: E2E-002",
    "BILL TO:",
    "DEMO TRANSPORT INC.",
    "1 rue Fictive",
    "Montreal, QC H0H 0H0",
    "DESCRIPTION AMOUNT",
    "Service Test $500.00",
    "SUBTOTAL $500.00",
    "TPS 000000000RT0001 $25.00",
    "TVQ 0000000000TQ0001 $49.88",
    "TOTAL $574.88",
])

UNMATCHED_BILLET = "\n".join([
    "03-09-2026",
    "Import E2E Inc. (0000-0000 Qc inc.)",
    "Quittance # 900-002",
    "AUTRE CLIENT INC. / Note 3 50,00 $ 150,00 $",
    "111222 03-09-2026 z000000",
    "TOTAL: 150,00 $",
])


def _real_errors(page):
    return [e for e in page.errors if "fonts.g" not in e and "net::ERR" not in e]


def _open_payments(page):
    page.click('.nav-btn[data-page="payments"]')
    page.wait_for_selector(".page")


def _upload(page, tmp_path, text, filename):
    pdf_path = tmp_path / filename
    pdf_path.write_bytes(make_text_pdf(text.split("\n")))
    page.set_input_files("#payment-file-input", str(pdf_path))
    page.wait_for_selector("#payment-detail")


def test_payments_tab_has_import_control_and_empty_state(page):
    _open_payments(page)
    assert page.locator(".pay-seg-btn").count() == 0  # no category switch any more
    assert page.locator("#btn-import-payment").is_visible()
    assert _real_errors(page) == []


def test_import_matches_the_seeded_invoice_and_marks_it_paid(page, tmp_path):
    _open_payments(page)
    _upload(page, tmp_path, QUITTANCE_MATCH_SEEDED, "quittance-e2e.pdf")

    detail = page.locator("#payment-detail")
    assert detail.get_by_text("900-001").first.is_visible()
    [ligne_row] = page.locator(".ligne-row").all()
    assert ligne_row.locator(".ligne-status.status-lie").is_visible()
    assert _real_errors(page) == []


def test_list_search_filters_payments(page):
    """Depends on the import above: one payment listed, found by its reference."""
    _open_payments(page)
    page.wait_for_selector("#payments-search")
    assert page.locator("#payments-list").get_by_text("900-001").first.is_visible()
    page.fill("#payments-search", "zzz-nothing-matches")
    assert page.locator(".payment-row:visible").count() == 0
    page.fill("#payments-search", "900-001")
    assert page.locator(".payment-row:visible").count() == 1
    assert _real_errors(page) == []


def test_bill_addressed_to_company_is_refused_with_a_clear_message(page, tmp_path):
    _open_payments(page)
    page.wait_for_selector("#payments-list")
    pdf_path = tmp_path / "bill-e2e.pdf"
    pdf_path.write_bytes(make_text_pdf(BILL_RECUE.split("\n")))
    page.set_input_files("#payment-file-input", str(pdf_path))

    error = page.locator(".toast-error", has_text="pas une preuve de paiement")
    error.wait_for()
    assert "bill-e2e.pdf" in (error.text_content() or "")
    page.wait_for_selector("#payments-list")
    assert page.locator("#payments-list").get_by_text("E2E-002").count() == 0
    # Chromium logs the expected 422 response itself; any other error still fails.
    assert [e for e in _real_errors(page) if "status of 422" not in e] == []


def test_unmatched_ligne_can_be_linked_manually(live_server, page, tmp_path):
    # A second, dedicated invoice for this scenario — seeded directly through
    # the API (this test is about the manual-link UI, not invoice creation).
    client = httpx.post(f"{live_server}/api/clients", json={
        "ref": "E2E2", "prefix": "e2e", "nom": "CLIENT MANUEL INC", "adresse": "2 rue Test",
    }).json()
    httpx.post(f"{live_server}/api/factures/generate", json={
        "client_id": client["id"], "date": "2026-09-03",
        "billets": [{"date_billet": "2026-09-03", "chantier": "Chantier B", "plaque": "M999999",
                     "numero_billet": "e2e-manual-1", "quantite": 3, "taux": 100}],
    })
    factures = httpx.get(f"{live_server}/api/factures", params={"client_id": client["id"]}).json()
    facture_id = factures[0]["id"]

    _open_payments(page)
    _upload(page, tmp_path, UNMATCHED_BILLET, "unmatched-e2e.pdf")

    ligne_row = page.locator(".ligne-row").first
    assert ligne_row.locator(".ligne-status.status-a-verifier").is_visible()

    ligne_row.locator(".btn-link-ligne").click()
    page.wait_for_selector("#ligne-link-picker")
    page.select_option("#ligne-link-facture-select", value=str(facture_id))
    page.select_option("#ligne-link-billet-select", value="0")
    page.click("#ligne-link-confirm")

    page.wait_for_selector(".ligne-row .ligne-status.status-lie")
    updated = httpx.get(f"{live_server}/api/factures/{facture_id}").json()
    assert updated["paye"] == 1
    assert _real_errors(page) == []


def test_billet_payment_badge_shows_on_invoice_form_and_links_back(page):
    """Depends on test_import_matches_the_seeded_invoice_and_marks_it_paid
    having already linked the seeded invoice's single billet."""
    page.click('.nav-btn[data-page="history"]')
    page.wait_for_selector(".page")
    row = page.locator("tr", has_text="CLIENT TEST INC")
    row.get_by_text("Modifier").click()
    page.wait_for_selector(".billet-card")

    badge = page.locator(".billet-payment-badge").first
    assert badge.is_visible()
    assert "900-001" in (badge.text_content() or "") or "Payé" in (badge.text_content() or "")

    badge.click()
    page.wait_for_selector("#payment-detail")
    assert page.locator("#payment-detail").get_by_text("900-001").first.is_visible()
    assert _real_errors(page) == []


def test_link_picker_traps_focus_closes_on_escape_and_restores_focus(page, tmp_path):
    """Keyboard contract of the manual-link dialog (review follow-up)."""
    text = "\n".join([
        "04-09-2026",
        "Import E2E Inc. (0000-0000 Qc inc.)",
        "Quittance # 900-003",
        "AUTRE CLIENT INC. / Note 2 50,00 $ 100,00 $",
        "333444 04-09-2026 y000000",
        "TOTAL: 100,00 $",
    ])
    _open_payments(page)
    _upload(page, tmp_path, text, "keyboard-e2e.pdf")

    trigger = page.locator(".btn-link-ligne").first
    trigger.focus()
    page.keyboard.press("Enter")
    page.wait_for_selector("#ligne-link-picker")

    inside = "document.getElementById('ligne-link-picker').contains(document.activeElement)"
    for _ in range(8):  # more presses than focusable elements: must wrap, never escape
        page.keyboard.press("Tab")
        assert page.evaluate(inside)
    for _ in range(8):
        page.keyboard.press("Shift+Tab")
        assert page.evaluate(inside)

    page.keyboard.press("Escape")
    assert page.locator("#ligne-link-picker").count() == 0
    assert page.evaluate("document.activeElement.classList.contains('btn-link-ligne')")
    assert _real_errors(page) == []

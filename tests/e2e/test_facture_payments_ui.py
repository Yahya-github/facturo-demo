"""E2E for the restyled invoice form and Paiements page (Phase 2b-2)."""

import base64
import re

import pytest

pytest.importorskip("playwright.sync_api")

from tests.helpers.pdf_writer import make_text_pdf  # noqa: E402


def _errors(page):
    return [e for e in page.errors if "fonts.g" not in e and "net::ERR" not in e and "status of 422" not in e]


def _digits(text):
    return re.sub(r"\D", "", text)


def _open_new_invoice(page):
    page.click('.nav-btn[data-page="facture"]')
    page.wait_for_selector(".fac-page")
    page.select_option("#fac-client", index=1)


def test_live_summary_follows_quantity_and_rate(page):
    _open_new_invoice(page)
    page.fill('.billet-input[data-idx="0"][data-field="quantite"]', "10")
    page.fill('.billet-input[data-idx="0"][data-field="taux"]', "100")
    # 1000 + TPS 50 + TVQ 99.75 = 1149.75 (the total counts up, so wait for it)
    page.wait_for_function("_digits => document.querySelector('[data-fac-total]').textContent.replace(/\\D/g,'') === _digits", arg="114975")
    assert _digits(page.locator("[data-fac-total-mini]").inner_text()) == "114975"
    page.fill('.billet-input[data-idx="0"][data-field="quantite"]', "20")
    page.wait_for_function("() => document.querySelector('[data-fac-total]').textContent.replace(/\\D/g,'') === '229950'")
    assert _errors(page) == []


def test_billet_and_invoice_discounts_are_collapsible(page):
    _open_new_invoice(page)
    page.fill('.billet-input[data-idx="0"][data-field="quantite"]', "10")
    page.fill('.billet-input[data-idx="0"][data-field="taux"]', "100")
    box = page.locator("#b0-remise")
    assert "is-open" not in (box.get_attribute("class") or "")
    page.click(".discount-toggle >> nth=0")
    assert "is-open" in box.get_attribute("class")
    page.fill('.billet-input[data-idx="0"][data-field="remise_pct"]', "10")
    page.wait_for_function("() => document.querySelector('[data-fac-total]').textContent.replace(/\\D/g,'') === '103478'")
    page.click(".discount-toggle-invoice")
    page.fill("#inv-remise-pct", "10")
    page.wait_for_function("() => document.querySelector('[data-fac-total]').textContent.replace(/\\D/g,'') === '93130'")
    page.click(".discount-remove >> nth=0")
    assert "is-open" not in box.get_attribute("class")
    assert _errors(page) == []


def test_action_bar_stays_in_view_on_a_long_form(page):
    _open_new_invoice(page)
    for _ in range(4):
        page.click(".fac-section-actions button >> nth=1")
    bar = page.locator(".fac-actionbar")
    page.evaluate("window.scrollTo(0, 0)")
    box = bar.bounding_box()
    assert box["y"] + box["height"] <= 900
    assert page.locator("#btn-generate").is_visible()


def test_delete_asks_confirmation_and_cancel_keeps_the_invoice(page):
    page.click('.nav-btn[data-page="history"]')
    page.wait_for_selector("tr[data-facture-id]")
    page.locator("tr[data-facture-id]").first.get_by_text("Modifier").click()
    page.wait_for_selector("#btn-delete-facture")
    page.click("#btn-delete-facture")
    dialog = page.locator('.modal-overlay[role="alertdialog"]')
    dialog.wait_for()
    dialog.get_by_role("button", name="Annuler").click()
    dialog.wait_for(state="detached")
    assert page.locator("#btn-delete-facture").is_visible()
    assert _errors(page) == []


def test_chantier_combobox_selects_with_the_keyboard(page):
    _open_new_invoice(page)
    field = page.locator('.billet-input[data-idx="0"][data-field="chantier"]')
    field.click()
    field.fill("chant")
    panel = page.locator(".ac-panel")
    panel.wait_for(state="visible")
    assert page.locator(".ac-row").count() >= 1
    page.keyboard.press("Enter")
    assert field.input_value().lower().startswith("chantier")
    assert page.locator(".ac-panel").is_hidden()
    assert _errors(page) == []


def test_payments_dropzone_highlights_on_drag_and_imports_a_dropped_pdf(page):
    page.click('.nav-btn[data-page="payments"]')
    page.wait_for_selector("#pay-dropzone")
    zone = page.locator("#pay-dropzone")
    zone.dispatch_event("dragover")
    assert "is-dragover" in zone.get_attribute("class")
    zone.dispatch_event("dragleave")
    assert "is-dragover" not in zone.get_attribute("class")

    lines = ["05-09-2026", "Import E2E Inc. (0000-0000 Qc inc.)", "Quittance # 900-777",
             "AUTRE CLIENT INC. / Note 2 50,00 $ 100,00 $", "555666 05-09-2026 x000000", "TOTAL: 100,00 $"]
    b64 = base64.b64encode(make_text_pdf(lines)).decode()
    page.evaluate(
        """b64 => {
          const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
          const dt = new DataTransfer();
          dt.items.add(new File([bytes], 'drop-e2e.pdf', { type: 'application/pdf' }));
          document.getElementById('pay-dropzone').dispatchEvent(
            new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
        }""", b64)
    page.wait_for_selector("#payment-detail")
    assert page.locator("#payment-detail").get_by_text("900-777").first.is_visible()
    assert page.locator(".progress[role=progressbar]").count() >= 1
    assert _errors(page) == []

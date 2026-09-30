"""English default and live language switching on Accueil, Historique, Factures
scannees, Paiements and the command palette.

Uses `page_en` (fresh browser, no stored language) and the shared live server.
"""

import re

import pytest

RAW_KEY = re.compile(r"^[a-z]+(\.[a-z0-9_]+)+$")

VISIBLE_TEXT_NODES = """() => {
  const out = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement;
    if (!el || ['SCRIPT', 'STYLE', 'TEMPLATE'].includes(el.tagName)) continue;
    const text = n.textContent.trim();
    if (text && el.getClientRects().length) out.push(text);
  }
  return out;
}"""


@pytest.fixture(autouse=True)
def _fast_timeouts(page_en):
    page_en.set_default_timeout(5000)


def _go(page, name):
    page.click(f'.nav-btn[data-page="{name}"]')
    page.wait_for_selector(".page")


def _h2(page):
    return page.locator("#main-content h2").first


def _no_raw_keys(page):
    leaked = [t for t in page.evaluate(VISIBLE_TEXT_NODES) if RAW_KEY.match(t)]
    assert leaked == []


def _no_errors(page):
    errors = [e for e in page.errors if "fonts.g" not in e and "net::ERR" not in e]
    assert errors == []


def _switch(page, code):
    page.click(f'#lang-toggle [data-lang-set="{code}"]')
    page.wait_for_function(f"document.documentElement.lang.startsWith('{code}')")


def test_default_language_is_english(page_en):
    assert page_en.evaluate("document.documentElement.lang").startswith("en")
    assert _h2(page_en).inner_text() == "Home"
    assert page_en.get_by_role("button", name="Create an invoice").first.is_visible()
    assert page_en.get_by_text("Latest invoices").is_visible()
    _no_raw_keys(page_en)
    _no_errors(page_en)


def test_history_in_english_then_french_without_reload(page_en):
    _go(page_en, "history")
    assert _h2(page_en).inner_text() == "History"
    assert page_en.locator("th", has_text="Invoice no.").is_visible()
    assert page_en.locator("label", has_text="Search").first.is_visible()
    _no_raw_keys(page_en)
    page_en.evaluate("window.__same_document = true")
    _switch(page_en, "fr")
    assert _h2(page_en).inner_text() == "Historique"
    assert page_en.locator("th", has_text="N° Facture").is_visible()
    assert page_en.evaluate("window.__same_document") is True  # no reload
    assert page_en.evaluate("document.documentElement.lang").startswith("fr")
    _no_raw_keys(page_en)
    _switch(page_en, "en")
    assert _h2(page_en).inner_text() == "History"
    assert page_en.evaluate("document.documentElement.lang").startswith("en")
    _no_errors(page_en)


def test_home_rerenders_in_french_and_back(page_en):
    _switch(page_en, "fr")
    assert _h2(page_en).inner_text() == "Accueil"
    assert page_en.get_by_text("Dernières factures").is_visible()
    _no_raw_keys(page_en)
    _switch(page_en, "en")
    assert _h2(page_en).inner_text() == "Home"
    _no_errors(page_en)


def test_scans_page_in_both_languages(page_en):
    _go(page_en, "scans")
    assert _h2(page_en).inner_text() == "Scanned invoices"
    assert page_en.get_by_text("No documents yet").first.is_visible()
    _no_raw_keys(page_en)
    _switch(page_en, "fr")
    assert _h2(page_en).inner_text() == "Factures scannées"
    assert page_en.get_by_text("Aucun document pour le moment").first.is_visible()
    _no_raw_keys(page_en)
    _switch(page_en, "en")
    assert _h2(page_en).inner_text() == "Scanned invoices"
    _no_errors(page_en)


def test_payments_page_in_both_languages(page_en):
    _go(page_en, "payments")
    page_en.wait_for_selector("#pay-dropzone")
    assert _h2(page_en).inner_text() == "Payments"
    assert page_en.get_by_text("Drag receipt PDFs here").is_visible()
    assert page_en.locator("#btn-import-payment").inner_text().strip() == "Import PDFs"
    _no_raw_keys(page_en)
    _switch(page_en, "fr")
    assert _h2(page_en).inner_text() == "Paiements"
    assert page_en.get_by_text("Glissez des quittances PDF ici").is_visible()
    assert "Importer des PDF" in page_en.locator("#btn-import-payment").inner_text()
    _no_raw_keys(page_en)
    _switch(page_en, "en")
    assert _h2(page_en).inner_text() == "Payments"
    _no_errors(page_en)


def test_command_palette_follows_language(page_en):
    page_en.keyboard.press("Control+k")
    assert page_en.locator(".command-overlay").is_visible()
    assert page_en.locator(".command-heading", has_text="Navigation").is_visible()
    assert page_en.locator(".command-item", has_text="Scanned invoices").first.is_visible()
    assert page_en.locator(".command-input").get_attribute("placeholder").startswith("Search for")
    _no_raw_keys(page_en)
    # A switch while the palette is open refreshes it in place.
    page_en.evaluate("ui.i18n.setLang('fr')")
    assert page_en.locator(".command-item", has_text="Factures scannées").first.is_visible()
    assert page_en.locator(".command-heading", has_text="Actions").is_visible()
    assert page_en.locator(".command-input").get_attribute("placeholder").startswith("Rechercher")
    _no_raw_keys(page_en)
    page_en.keyboard.press("Escape")
    page_en.wait_for_selector(".command-overlay", state="detached")
    # Search results get their group title from the language too.
    page_en.keyboard.press("Control+k")
    page_en.keyboard.type("CLIENT TEST")
    assert page_en.locator(".command-heading", has_text="Recherche").is_visible()
    page_en.keyboard.press("Escape")
    _switch(page_en, "en")
    page_en.keyboard.press("Control+k")
    page_en.keyboard.type("CLIENT TEST")
    assert page_en.locator(".command-heading", has_text="Search").is_visible()
    page_en.keyboard.press("Escape")
    _no_errors(page_en)

"""English default on Clients, New invoice and Settings, and live language switching.

Uses `page_en` (a fresh browser with no stored language, so the app's default).
"""

import re

import pytest

RAW_KEY = re.compile(r"^[a-z]+(\.[a-z0-9_]+)+$")


@pytest.fixture(autouse=True)
def _fast_timeouts(page_en):
    page_en.set_default_timeout(5000)


def _go(page, name):
    page.evaluate(f"navigate('{name}')")
    page.wait_for_selector(".page")


def _raw_keys(page):
    """Visible text nodes (and common attributes) that look like an untranslated key."""
    return page.evaluate(
        """() => {
          const re = /^[a-z]+(\\.[a-z0-9_]+)+$/;
          const out = [];
          const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          while (walker.nextNode()) {
            const n = walker.currentNode;
            const p = n.parentElement;
            if (!p || ['SCRIPT', 'STYLE'].includes(p.tagName)) continue;
            const text = n.textContent.trim();
            if (re.test(text)) out.push(text);
          }
          document.querySelectorAll('[placeholder],[aria-label],[title],[data-tip]').forEach(el => {
            ['placeholder', 'aria-label', 'title', 'data-tip'].forEach(a => {
              const v = (el.getAttribute(a) || '').trim();
              if (re.test(v)) out.push(a + '=' + v);
            });
          });
          return out;
        }"""
    )


def _clean(page):
    assert _raw_keys(page) == []
    errors = [e for e in page.errors if "fonts.g" not in e and "net::ERR" not in e]
    assert errors == []


def test_clients_page_is_english_and_complete(page_en):
    _go(page_en, "clients")
    assert page_en.locator(".clients h2").inner_text() == "Clients"
    body = page_en.locator(".clients").inner_text()
    assert "Add a client" in body
    assert "Next no." in body and "Billed" in body
    _clean(page_en)
    page_en.click(".clients .page-head-actions button")
    dialog = page_en.locator(".modal-overlay")
    dialog.wait_for()
    text = dialog.inner_text()
    assert "New client" in text and "Company name" in text and "Invoice prefix" in text
    _clean(page_en)
    page_en.click("#cm-save")  # empty form: inline errors in English
    assert "Enter the company name" in page_en.locator(".modal-overlay").inner_text()
    page_en.click("#cm-cancel")


def test_facture_page_discount_and_ai_dialog_are_english(page_en):
    _go(page_en, "facture")
    page = page_en
    assert page.locator(".fac-page h2").inner_text() == "New invoice"
    text = page.locator(".fac-page").inner_text()
    for expected in ("Information", "Add a ticket", "Add with AI", "Total due", "Generate"):
        assert expected in text, expected
    page.fill("#b0-quantite", "2")
    page.fill("#b0-taux", "100")
    page.click("#b0-remise-toggle, .discount-toggle")
    assert "Discount" in page.locator(".billet-foot").inner_text()
    assert "GST (5%)" in page.locator("#fac-summary").inner_text()
    _clean(page)
    page.click("text=Add with AI")
    dialog = page.locator(".ai-dialog")
    dialog.wait_for()
    assert "Add a ticket with AI" in dialog.inner_text()
    assert "Describe the ticket" in dialog.inner_text()
    _clean(page)
    page.click("#ai-quickadd-submit")  # nothing given: the English toast, no model call
    page.wait_for_selector(".toast-error")
    assert "Choose a photo or enter a description" in page.locator(".toast-error").first.inner_text()
    page.keyboard.press("Escape")


@pytest.mark.parametrize("tab,expected", [
    ("general", ["Company logo", "Updates", "Installed version"]),
    ("sync", ["Multi-device synchronization", "GitHub repository URL"]),
    ("ai", ["Artificial intelligence"]),
    ("known", ["Known worksites and plates", "Worksites"]),
    ("danger", ["Reset the database"]),
])
def test_settings_tabs_are_english(page_en, tab, expected):
    _go(page_en, "settings")
    page_en.click(f'[data-tab="{tab}"]')
    panel = page_en.locator(f'[data-tab-panel="{tab}"]')
    panel.wait_for(state="visible")
    text = panel.inner_text()
    for needle in expected:
        assert needle in text, needle
    _clean(page_en)


def test_language_switch_rerenders_without_reload(page_en):
    page = page_en
    _go(page, "settings")
    page.evaluate("window.__marker = 'kept'")
    assert "Updates" in page.locator("#update-card h3").inner_text()
    page.click('#lang-select [data-lang-set="fr"]')
    page.wait_for_function("document.querySelector('#update-card h3').innerText.includes('Mises à jour')")
    assert "Paramètres" in page.locator(".settings h2").inner_text()
    assert page.evaluate("window.__marker") == "kept"  # no reload happened
    _clean(page)
    page.click('#lang-select [data-lang-set="en"]')
    page.wait_for_function("document.querySelector('#update-card h3').innerText.includes('Updates')")
    assert page.locator(".settings h2").inner_text() == "Settings"
    _clean(page)

"""Every sidebar tab renders without a JavaScript error."""

import pytest

TABS = [
    ("home", None),
    ("clients", "Clients"),
    ("facture", None),
    ("history", "Historique"),
    ("scans", "Factures scannées"),
    ("payments", "Paiements"),
    ("settings", "Paramètres"),
]


@pytest.mark.parametrize("tab,heading", TABS)
def test_tab_renders(page, tab, heading):
    page.click(f'.nav-btn[data-page="{tab}"]')
    page.wait_for_selector(".page")
    if heading:
        assert page.locator("h2", has_text=heading).first.is_visible()
    # Fonts are fetched from Google; offline runs log a network error for them.
    errors = [e for e in page.errors if "fonts.g" not in e and "net::ERR" not in e]
    assert errors == []


def test_history_lists_seeded_invoice(page):
    page.click('.nav-btn[data-page="history"]')
    assert page.locator("td", has_text="CLIENT TEST INC").first.is_visible()

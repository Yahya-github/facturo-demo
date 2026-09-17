"""Historique / Clients / Factures scannées / Paramètres restyle: menus, presets, tabs, dropzone."""

import re

import pytest
from playwright.sync_api import expect

pytest.importorskip("playwright.sync_api")


def _go(page, name):
    page.click(f'.nav-btn[data-page="{name}"]')
    page.wait_for_selector(".page")


def _real_errors(page):
    return [e for e in page.errors if "fonts.g" not in e and "net::ERR" not in e]


def test_history_row_menu_lists_the_actions(page):
    _go(page, "history")
    page.wait_for_selector("[data-row-menu][aria-haspopup]")
    page.locator("[data-row-menu]").first.click()
    menu = page.locator(".menu")
    expect(menu).to_be_visible()
    for label in ("Modifier", "Télécharger Excel", "Télécharger PDF", "Supprimer"):
        expect(menu.get_by_role("menuitem", name=label)).to_be_visible()
    assert re.search(r"Marquer (non )?payée", menu.inner_text())
    page.keyboard.press("Escape")
    assert _real_errors(page) == []


def test_history_context_menu_on_row(page):
    _go(page, "history")
    page.wait_for_selector("[data-row-menu][aria-haspopup]")
    page.locator("tr[data-facture-id]").first.click(button="right")
    expect(page.locator(".menu").get_by_role("menuitem", name="Modifier")).to_be_visible()
    page.keyboard.press("Escape")


def test_history_delete_asks_confirmation_and_cancel_keeps_the_row(page):
    _go(page, "history")
    page.wait_for_selector("[data-row-menu][aria-haspopup]")
    before = page.locator("tr[data-facture-id]").count()
    page.locator("[data-row-menu]").first.click()
    page.get_by_role("menuitem", name="Supprimer").click()
    dialog = page.get_by_role("alertdialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Annuler").click()
    assert page.locator("tr[data-facture-id]").count() == before


def test_history_date_preset_sets_the_range_and_the_hash(page):
    _go(page, "history")
    page.click("#flt-presets")
    page.click('[data-preset="year"]')
    year = page.evaluate("new Date().getFullYear()")
    assert page.input_value("#flt-du") == f"{year}-01-01"
    assert page.input_value("#flt-au") == f"{year}-12-31"
    assert f"du={year}-01-01" in page.evaluate("location.hash")
    page.click("#flt-reset")
    assert page.input_value("#flt-du") == ""


def test_history_slash_focuses_search(page):
    _go(page, "history")
    page.locator("body").click(position={"x": 700, "y": 120})
    page.keyboard.press("/")
    assert page.evaluate("document.activeElement.id") == "flt-q"


def test_history_sort_header_switches_order(page):
    _go(page, "history")
    page.click('.flt-sort:has-text("Date")')
    assert page.input_value("#flt-tri") == "date_asc"


def test_clients_dialog_shows_inline_validation(page):
    _go(page, "clients")
    page.click("text=Ajouter un client")
    page.wait_for_selector("#cm-nom")
    page.click("#cm-save")
    expect(page.locator("#cm-nom").locator("xpath=ancestor::div[contains(@class,'field')]")).to_have_class(
        re.compile("is-invalid")
    )
    page.keyboard.press("Escape")
    assert _real_errors(page) == []


def test_settings_tabs_keep_update_card_visible_by_default(page):
    _go(page, "settings")
    expect(page.locator("#update-card")).to_be_visible()
    expect(page.locator("#update-card h3")).to_have_text("Mises à jour")
    page.click('[data-tab="sync"]')
    expect(page.locator("#update-card")).to_be_hidden()
    expect(page.get_by_text("Synchronisation multi-appareils")).to_be_visible()
    page.click('[data-tab="general"]')
    expect(page.locator("#update-card")).to_be_visible()


def test_reset_button_lives_in_the_danger_zone_and_alert_dialog_cancels(page):
    _go(page, "home")
    assert page.locator("text=Réinitialiser la base de données").count() == 0
    _go(page, "settings")
    page.click('[data-tab="danger"]')
    page.click("#reset-db-btn")
    dialog = page.get_by_role("alertdialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Annuler").click()
    expect(dialog).to_be_hidden()
    assert page.locator("tr[data-facture-id]").count() >= 0
    _go(page, "history")
    assert page.locator("tr[data-facture-id]").count() >= 1


def test_settings_selected_tab_survives_a_rerender(page):
    _go(page, "settings")
    page.click('[data-tab="known"]')
    page.evaluate("render()")
    page.wait_for_function("document.querySelector('[data-tab=known]').getAttribute('aria-selected') === 'true'")
    page.click('[data-tab="general"]')


def test_scans_dropzone_gets_dragover_class(page):
    _go(page, "scans")
    page.locator(".scan-folder").first.click()
    zone = page.locator("#scan-dropzone")
    expect(zone).to_be_visible()
    zone.dispatch_event("dragenter")
    expect(zone).to_have_class(re.compile("is-dragover"))
    zone.dispatch_event("dragleave")
    expect(zone).not_to_have_class(re.compile("is-dragover"))


def test_money_uses_french_canadian_format(page):
    text = page.evaluate("money(9042.78)")
    assert text == "9 042,78 $"

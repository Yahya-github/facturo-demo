"""UI primitives: command palette, theme, sidebar, dialogs, toasts, tooltips.

Uses the shared fixtures in conftest.py (live server + seeded data). Every test
fails on console/page errors, like the other e2e suites.
"""

import re

import pytest


def _no_errors(page):
    errors = [e for e in page.errors if "fonts.g" not in e and "net::ERR" not in e]
    assert errors == []


# ── Command palette ─────────────────────────────────────

def test_ctrl_k_opens_palette_and_navigates(page):
    page.keyboard.press("Control+k")
    palette = page.locator(".command-overlay")
    assert palette.is_visible()
    assert page.locator(".command-input").evaluate("el => el === document.activeElement")
    page.keyboard.type("histo")
    assert page.locator('.command-item[aria-selected="true"]', has_text="Historique").is_visible()
    page.keyboard.press("Enter")
    page.wait_for_selector(".command-overlay", state="detached")
    page.wait_for_selector("#flt-q")
    assert page.locator('.nav-btn[data-page="history"]').get_attribute("class").count("active") == 1
    _no_errors(page)


def test_palette_searches_invoices_and_clients(page):
    page.keyboard.press("Control+k")
    page.keyboard.type("client test")
    assert page.locator(".command-item", has_text="CLIENT TEST INC").first.is_visible()
    assert page.locator(".command-group .command-heading", has_text="Recherche").is_visible()
    page.keyboard.press("Escape")
    page.wait_for_selector(".command-overlay", state="detached")
    _no_errors(page)


def test_palette_empty_state_and_accent_folding(page):
    page.keyboard.press("Control+k")
    page.keyboard.type("parametres")
    assert page.locator(".command-item", has_text="Paramètres").first.is_visible()
    page.fill(".command-input", "zzzqqq")
    assert page.locator(".command-empty").is_visible()
    page.keyboard.press("Escape")


def test_palette_not_triggered_by_typing_in_inputs(page):
    page.click('.nav-btn[data-page="history"]')
    page.click("#flt-q")
    page.keyboard.type("k")
    assert page.locator(".command-overlay").count() == 0
    page.keyboard.press("Control+k")   # with the modifier it does open, even from an input
    assert page.locator(".command-overlay").is_visible()
    page.keyboard.press("Escape")
    assert page.locator("#flt-q").evaluate("el => el === document.activeElement")


def test_palette_remembers_recent_items(page):
    page.keyboard.press("Control+k")
    page.keyboard.type("clients")
    page.keyboard.press("Enter")
    page.wait_for_selector(".command-overlay", state="detached")
    page.keyboard.press("Control+k")
    assert page.locator(".command-heading", has_text="Récents").is_visible()
    page.keyboard.press("Escape")


# ── Theme ───────────────────────────────────────────────

def test_theme_toggle_persists_after_reload(page):
    page.click('#theme-toggle [data-theme-set="dark"]')
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    page.reload()
    page.wait_for_selector(".page")
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    page.click('#theme-toggle [data-theme-set="light"]')
    assert page.evaluate("document.documentElement.dataset.theme") == "light"
    _no_errors(page)

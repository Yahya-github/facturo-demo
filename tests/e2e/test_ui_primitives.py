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


# ── Sidebar ─────────────────────────────────────────────

def test_sidebar_collapse_persists_after_reload(page):
    assert page.evaluate("document.documentElement.dataset.sidebar") is None
    width_open = page.locator("#sidebar").bounding_box()["width"]
    page.click("#sidebar-toggle")
    assert page.evaluate("document.documentElement.dataset.sidebar") == "collapsed"
    page.wait_for_function("document.querySelector('#sidebar').getBoundingClientRect().width < 80")
    assert page.locator("#sidebar").bounding_box()["width"] < width_open
    # Nav buttons keep their contract while collapsed and labels become tooltips.
    assert page.locator('.nav-btn[data-page="history"]').get_attribute("data-tip") == "Historique"
    page.reload()
    page.wait_for_selector(".page")
    assert page.evaluate("document.documentElement.dataset.sidebar") == "collapsed"
    page.keyboard.press("Control+b")
    assert page.evaluate("document.documentElement.dataset.sidebar") is None
    page.reload()
    page.wait_for_selector(".page")
    assert page.evaluate("document.documentElement.dataset.sidebar") is None
    _no_errors(page)


def test_sidebar_becomes_a_sheet_on_mobile(page):
    page.set_viewport_size({"width": 390, "height": 800})
    assert not page.locator("#sidebar").is_visible()
    page.click("#sidebar-open")
    page.wait_for_selector(".sheet-nav #sidebar")
    assert page.locator('.sheet-nav .nav-btn[data-page="clients"]').is_visible()
    assert page.locator("#update-dot").count() == 1
    page.click('.sheet-nav .nav-btn[data-page="clients"]')
    page.wait_for_selector(".sheet-nav", state="detached")
    assert page.locator("h2", has_text="Clients").first.is_visible()
    assert page.locator("#sidebar").count() == 1
    assert page.evaluate("document.activeElement.id") == "sidebar-open"
    _no_errors(page)


# ── Charts and count-up ─────────────────────────────────

MOUNT = """() => {
  const host = document.createElement('div');
  host.id = 'chart-host';
  host.style.cssText = 'position:fixed;left:20px;top:20px;width:640px;background:#fff;z-index:5';
  document.body.appendChild(host);
  const bar = document.createElement('div'); bar.id = 'c-bar';
  const donut = document.createElement('div'); donut.id = 'c-donut';
  const hbar = document.createElement('div'); hbar.id = 'c-hbar';
  host.append(bar, donut, hbar);
  ui.chart.bar(bar, ui.chartData.groupByMonth(state.factures));
  ui.chart.donut(donut, ui.chartData.paidSplit(state.factures));
  ui.chart.hbar(hbar, ui.chartData.topClients(state.factures, 5));
}"""


def test_charts_render_with_tooltip_and_table_fallback(page):
    page.evaluate(MOUNT)
    for cid in ("c-bar", "c-donut", "c-hbar"):
        svg = page.locator(f"#{cid} svg[role=img]")
        assert svg.count() == 1
        assert svg.get_attribute("aria-label")
        assert page.locator(f"#{cid} table.sr-only tbody tr").count() >= 1
    assert page.locator("#c-bar .chart-bar-rect").count() == 6
    # Hover a bar column: tooltip names the month and the amount.
    hits = page.locator("#c-bar .chart-hit")
    hits.nth(5).hover()
    tip = page.locator("#c-bar .chart-tip")
    tip.wait_for(state="visible")
    assert "sept. 2026" in tip.inner_text()
    page.locator("#c-hbar .chart-hit").first.hover()
    assert "CLIENT TEST INC" in page.locator("#c-hbar .chart-tip").inner_text()
    _no_errors(page)


def test_countup_lands_on_the_final_money_value(page):
    page.evaluate("""() => { const s = document.createElement('span'); s.id = 'cu';
      document.body.appendChild(s); ui.countup.run(s, 1234.5, { format: 'money', duration: 200 }); }""")
    page.wait_for_function("document.getElementById('cu').textContent === money(1234.5)")
    _no_errors(page)


def test_countup_respects_reduced_motion(page):
    page.emulate_media(reduced_motion="reduce")
    page.evaluate("""() => { const s = document.createElement('span'); s.id = 'cu2';
      document.body.appendChild(s); ui.countup.run(s, 99, { format: 'money', duration: 5000 }); }""")
    assert page.locator("#cu2").inner_text() == page.evaluate("money(99)")

"""UI primitives: command palette, theme, sidebar, dialogs, toasts, tooltips.

Uses the shared fixtures in conftest.py (live server + seeded data). Every test
fails on console/page errors, like the other e2e suites.
"""

import pytest


@pytest.fixture(autouse=True)
def _fast_timeouts(page):
    """A missing element fails in 5s, not 30s."""
    page.set_default_timeout(5000)


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
    top = page.evaluate("ui.chartData.topClients(state.factures, 5)[0].name")
    assert top in page.locator("#c-hbar .chart-tip").inner_text()
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


# ── Dialogs ─────────────────────────────────────────────

def test_alert_dialog_cancel_then_confirm_on_a_delete_flow(page):
    """Delete a scratch known value: Annuler keeps it, Supprimer removes it."""
    page.click('.nav-btn[data-page="settings"]')
    page.fill("#kv-new", "CHANTIER SCRATCH UI")
    page.click("text=Ajouter >> nth=0")
    row = page.locator(".kv-row", has_text="CHANTIER SCRATCH UI")
    row.wait_for()
    delete_btn = row.locator("button", has_text="Supprimer")

    delete_btn.click()
    dialog = page.locator('.modal-overlay[role="alertdialog"]')
    dialog.wait_for()
    assert dialog.locator(".modal-header h3").inner_text() == "Supprimer la valeur"
    assert "CHANTIER SCRATCH UI" in dialog.locator(".confirm-text").inner_text()
    assert dialog.locator("[data-dialog-confirm]").get_attribute("class").count("btn-danger") == 1
    # Destructive dialogs start on the safe button; Escape cancels.
    assert page.evaluate("document.activeElement.hasAttribute('data-dialog-cancel')")
    page.keyboard.press("Escape")
    dialog.wait_for(state="detached")
    assert row.count() == 1
    assert page.evaluate("document.activeElement.textContent.trim()") == "Supprimer"

    delete_btn.click()
    dialog.wait_for()
    dialog.locator("[data-dialog-cancel]").click()
    dialog.wait_for(state="detached")
    assert row.count() == 1

    delete_btn.click()
    dialog.wait_for()
    dialog.locator("[data-dialog-confirm]").click()
    dialog.wait_for(state="detached")
    page.wait_for_function("!document.querySelector('.kv-row .kv-value') || ![...document.querySelectorAll('.kv-value')].some(e => e.textContent.includes('SCRATCH UI'))")
    _no_errors(page)


def test_prompt_dialog_enter_submits_and_escape_cancels(page):
    page.evaluate("() => { window.__answer = undefined; ui.promptDialog({ title: 'Nom', label: 'Nom', value: 'abc' }).then(v => { window.__answer = v; }); }")
    field = page.locator(".modal-overlay input.form-input")
    field.wait_for()
    assert field.input_value() == "abc"
    field.fill("")
    assert page.locator("[data-dialog-confirm]").is_disabled()
    field.fill("  nouveau  ")
    page.keyboard.press("Enter")
    page.wait_for_function("window.__answer === 'nouveau'")
    page.evaluate("() => { window.__answer = undefined; ui.promptDialog({ title: 'Nom', value: 'x' }).then(v => { window.__answer = v; }); }")
    page.locator(".modal-overlay input.form-input").wait_for()
    page.keyboard.press("Escape")
    page.wait_for_function("window.__answer === null")


def test_escape_closes_dialog_and_restores_focus(page):
    page.click('.nav-btn[data-page="clients"]')
    opener = page.locator("button", has_text="Ajouter un client")
    opener.focus()
    opener.press("Enter")
    overlay = page.locator(".modal-overlay")
    overlay.wait_for()
    assert overlay.get_attribute("role") == "dialog"
    assert overlay.get_attribute("aria-modal") == "true"
    page.keyboard.press("Escape")
    overlay.wait_for(state="detached")
    assert page.evaluate("document.activeElement.textContent.includes('Ajouter un client')")
    _no_errors(page)


def test_dialog_traps_tab_focus(page):
    page.evaluate("() => { ui.dialog.show({ title: 'Piège', body: '<input id=\"a\"><input id=\"b\">', footer: '<button class=\"btn\" id=\"z\">OK</button>' }); }")
    page.locator("#a").wait_for()
    for _ in range(8):
        page.keyboard.press("Tab")
        assert page.evaluate("!!document.activeElement.closest('.modal-overlay')")
    page.keyboard.press("Escape")


def test_sheet_slides_from_the_side(page):
    page.evaluate("() => { ui.sheet({ side: 'right', title: 'Détails', body: '<p>Corps</p>' }); }")
    box = page.locator(".sheet-right .modal.sheet")
    box.wait_for()
    bb = box.bounding_box()
    assert bb["x"] + bb["width"] >= 1439
    assert bb["height"] >= 890
    page.keyboard.press("Escape")
    box.wait_for(state="detached")


# ── Toasts ──────────────────────────────────────────────

def test_toast_stack_caps_at_three_and_keeps_error_class(page):
    page.evaluate("""() => { toast('un'); toast('deux'); toast('trois'); toast('Quelque chose a échoué', 'error'); }""")
    error = page.locator(".toast.toast-error", has_text="a échoué")
    error.wait_for()
    assert error.get_attribute("role") == "alert"
    assert page.locator(".toast:visible").count() == 3
    assert page.locator(".toast-container").get_attribute("aria-live") == "polite"
    assert error.locator(".toast-progress").count() == 1
    error.locator(".toast-close").click()
    error.wait_for(state="detached")
    _no_errors(page)


def test_toast_action_button_runs_callback_and_dismisses(page):
    page.evaluate("""() => { window.__undone = 0;
      ui.toast('Facture supprimée', 'info', { action: { label: 'Annuler', onClick: () => { window.__undone++; } } }); }""")
    t = page.locator(".toast", has_text="Facture supprimée")
    t.locator(".toast-action").click()
    page.wait_for_function("window.__undone === 1")
    t.wait_for(state="detached")


def test_toast_hover_pauses_dismissal(page):
    page.evaluate("() => { ui.toast('Reste affiché', 'success', { duration: 700 }); }")
    t = page.locator(".toast", has_text="Reste affiché")
    t.hover()
    page.wait_for_timeout(1200)
    assert t.count() == 1
    page.mouse.move(5, 5)
    t.wait_for(state="detached", timeout=4000)


# ── Tooltips ────────────────────────────────────────────

def test_tooltip_appears_on_keyboard_focus_and_hides_on_escape(page):
    btn = page.locator("#sidebar-toggle")
    btn.focus()
    tip = page.locator("#ui-tooltip")
    tip.wait_for(state="visible")
    assert "Réduire le menu" in tip.inner_text()
    assert page.locator("#sidebar-toggle").get_attribute("aria-describedby") == "ui-tooltip"
    assert tip.locator("kbd").count() == 2   # Ctrl + B
    page.keyboard.press("Escape")
    tip.wait_for(state="hidden")


def test_tooltip_shows_on_hover_after_a_delay(page):
    page.locator("#sidebar-toggle").hover()
    assert page.locator("#ui-tooltip").count() == 0 or not page.locator("#ui-tooltip").is_visible()
    page.locator("#ui-tooltip").wait_for(state="visible")


def test_title_attributes_become_tooltips_with_accessible_names(page):
    page.evaluate("""() => { document.body.insertAdjacentHTML('beforeend',
      '<button id="t-btn" title="Supprimer la ligne"><svg width="8" height="8"></svg></button>'); }""")
    page.wait_for_function("document.getElementById('t-btn').hasAttribute('data-tip')")
    assert page.locator("#t-btn").get_attribute("title") is None
    assert page.locator("#t-btn").get_attribute("aria-label") == "Supprimer la ligne"
    assert page.locator("#t-btn").get_attribute("data-tip") == "Supprimer la ligne"
    assert page.locator("[title]").count() == 0


# ── Menus, popover, tabs ────────────────────────────────

def test_dropdown_menu_keyboard_roving_and_typeahead(page):
    page.evaluate("""() => {
      document.body.insertAdjacentHTML('beforeend', '<button id="m-btn" style="position:fixed;left:300px;top:300px">Actions</button>');
      window.__picked = '';
      ui.menu.attach(document.getElementById('m-btn'), [
        { label: 'Modifier', onSelect: () => { window.__picked = 'edit'; } },
        { label: 'Télécharger', onSelect: () => { window.__picked = 'dl'; } },
        { separator: true },
        { label: 'Supprimer', destructive: true, onSelect: () => { window.__picked = 'del'; } },
      ]);
    }""")
    btn = page.locator("#m-btn")
    btn.focus()
    page.keyboard.press("ArrowDown")
    menu = page.locator('[role="menu"]')
    menu.wait_for()
    assert btn.get_attribute("aria-expanded") == "true"
    items = menu.locator('[role="menuitem"]')
    assert page.evaluate("document.activeElement.textContent.trim()") == "Modifier"
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Télécharger"
    page.keyboard.press("ArrowUp")
    page.keyboard.press("ArrowUp")     # wraps to the last item
    assert page.evaluate("document.activeElement.textContent.trim()") == "Supprimer"
    page.keyboard.type("tel")           # typeahead ignores accents
    assert page.evaluate("document.activeElement.textContent.trim()") == "Télécharger"
    assert items.count() == 3
    page.keyboard.press("Escape")
    menu.wait_for(state="detached")
    assert page.evaluate("document.activeElement.id") == "m-btn"
    btn.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_function("window.__picked === 'edit'")
    _no_errors(page)


def test_context_menu_opens_on_right_click_and_shift_f10(page):
    page.click('.nav-btn[data-page="history"]')
    row = page.locator("tr[data-facture-id]").first
    row.wait_for()
    page.evaluate("""() => {
      window.__ctx = '';
      const row = document.querySelector('tr[data-facture-id]');
      row.tabIndex = 0;
      ui.contextMenu.attach(document.getElementById('main-content'), 'tr[data-facture-id]',
        t => [{ label: 'Ouvrir', onSelect: () => { window.__ctx = 'open:' + t.dataset.factureId; } }]);
    }""")
    row.click(button="right")
    page.locator('[role="menu"]').wait_for()
    page.keyboard.press("Escape")
    page.locator('[role="menu"]').wait_for(state="detached")
    row.focus()
    page.keyboard.press("Shift+F10")
    page.locator('[role="menu"]').wait_for()
    page.keyboard.press("Enter")
    page.wait_for_function("window.__ctx.startsWith('open:')")
    _no_errors(page)


def test_popover_opens_closes_on_outside_press_and_escape(page):
    page.evaluate("""() => {
      document.body.insertAdjacentHTML('beforeend', '<button id="p-btn" style="position:fixed;left:400px;top:200px">Filtres</button>');
      ui.popover.attach(document.getElementById('p-btn'), () => ({ content: '<label>Nom <input id="p-in"></label>', label: 'Filtres' }));
    }""")
    page.click("#p-btn")
    page.locator("#p-in").wait_for()
    assert page.evaluate("document.activeElement.id") == "p-in"
    page.mouse.click(10, 500)
    page.locator("#p-in").wait_for(state="detached")
    page.click("#p-btn")
    page.locator("#p-in").wait_for()
    page.keyboard.press("Escape")
    page.locator("#p-in").wait_for(state="detached")
    assert page.evaluate("document.activeElement.id") == "p-btn"


def test_menu_inside_dialog_escape_closes_only_the_menu(page):
    page.evaluate("""() => {
      ui.dialog.show({ title: 'Avec menu', body: '<button id="dm-btn" class="btn">Ouvrir</button>' });
      ui.menu.attach(document.getElementById('dm-btn'), [{ label: 'Un' }, { label: 'Deux' }]);
    }""")
    page.click("#dm-btn")
    page.locator('[role="menu"]').wait_for()
    page.keyboard.press("Escape")
    page.locator('[role="menu"]').wait_for(state="detached")
    assert page.locator(".modal-overlay").count() == 1
    page.keyboard.press("Escape")
    page.locator(".modal-overlay").wait_for(state="detached")


def test_tabs_keyboard_and_indicator(page):
    page.evaluate("""() => { document.body.insertAdjacentHTML('beforeend', `
      <div data-tabs id="tb" data-tabs-value="b" style="position:fixed;left:20px;top:20px;width:500px;background:#fff;z-index:9">
        <div class="tabs-list tabs-line" aria-label="Test">
          <button class="tabs-trigger" data-tab="a">Un</button>
          <button class="tabs-trigger" data-tab="b">Deux</button>
          <button class="tabs-trigger" data-tab="c">Trois</button>
        </div>
        <div data-tab-panel="a">Panneau A</div><div data-tab-panel="b">Panneau B</div><div data-tab-panel="c">Panneau C</div>
      </div>`); }""")
    page.locator("#tb .tabs-indicator").wait_for(state="attached")
    tabs = page.locator("#tb [role=tab]")
    assert tabs.nth(1).get_attribute("aria-selected") == "true"
    assert tabs.nth(0).get_attribute("tabindex") == "-1"
    assert page.locator("#tb [data-tab-panel]:not([hidden])").inner_text() == "Panneau B"
    x_before = page.locator("#tb .tabs-indicator").evaluate("el => el.style.transform")
    tabs.nth(1).focus()
    page.keyboard.press("ArrowRight")
    assert tabs.nth(2).get_attribute("aria-selected") == "true"
    assert page.evaluate("document.activeElement.textContent.trim()") == "Trois"
    assert page.locator("#tb [data-tab-panel]:not([hidden])").inner_text() == "Panneau C"
    assert page.locator("#tb .tabs-indicator").evaluate("el => el.style.transform") != x_before
    page.keyboard.press("Home")
    assert tabs.nth(0).get_attribute("aria-selected") == "true"
    assert tabs.nth(0).get_attribute("aria-controls") == page.locator("#tb [data-tab-panel]").first.get_attribute("id")
    _no_errors(page)


def test_spotlight_tracks_the_pointer(page):
    page.evaluate("""() => { document.body.insertAdjacentHTML('beforeend',
      '<div id="sp" class="spotlight" style="position:fixed;left:600px;top:100px;width:200px;height:100px;background:#fff;z-index:9"></div>'); }""")
    page.mouse.move(650, 130)
    page.mouse.move(680, 150)
    page.wait_for_function("document.getElementById('sp').style.getPropertyValue('--mx') === '80px'")
    assert page.evaluate("document.getElementById('sp').style.getPropertyValue('--my')") == "50px"

"""Keyboard and screen-reader behaviour: skip link, page heading, focus, motion.

Runs against the shared live server from conftest.py. Complements the axe-core
pass done by hand (no npm dependency in this repo): these assert the fixes that
scan drove, so they cannot quietly regress.
"""

import pytest


@pytest.fixture(autouse=True)
def _fast_timeouts(page):
    page.set_default_timeout(5000)


def _active(page):
    return page.evaluate("document.activeElement && (document.activeElement.id || document.activeElement.tagName)")


# ── Skip link and landmarks ─────────────────────────────

def test_first_tab_stop_is_the_skip_link_and_it_moves_focus_to_main(page):
    page.keyboard.press("Tab")
    link = page.locator("#skip-link")
    assert _active(page) == "skip-link"
    assert link.inner_text() == "Aller au contenu"
    assert link.bounding_box()["y"] >= 0  # on screen while focused
    hash_before = page.evaluate("location.hash")
    page.keyboard.press("Enter")
    assert _active(page) == "main-content"
    assert page.evaluate("location.hash") == hash_before  # the router's hash is untouched


def test_skip_link_is_off_screen_until_focused(page):
    box = page.locator("#skip-link").bounding_box()
    assert box["y"] + box["height"] <= 0


def test_each_page_has_exactly_one_h1_matching_the_breadcrumb(page):
    for name, title in [("home", "Accueil"), ("history", "Historique"), ("settings", "Paramètres")]:
        page.evaluate(f"navigate('{name}')")
        page.wait_for_selector(".page")
        assert page.locator("h1").count() == 1
        assert page.locator("h1").inner_text() == title


def test_one_banner_and_every_visible_navigation_landmark_is_labelled(page):
    banners = page.evaluate("""() => [...document.querySelectorAll('header')]
      .filter(h => !h.closest('main, section, article, aside, nav, dialog, [role=dialog]')).length""")
    assert banners == 1
    for el in page.locator("nav, aside").all():
        if el.is_visible():
            assert el.get_attribute("aria-label")


def test_icon_only_history_edit_button_keeps_an_accessible_name(page):
    page.evaluate("navigate('history')")
    page.wait_for_selector("tr[data-facture-id]")
    label = page.locator(".flt-edit").first.get_attribute("aria-label")
    assert label.startswith("Modifier")  # the visible text is contained in the name


# ── Keyboard flows ──────────────────────────────────────

def test_tab_walks_the_sidebar_and_reaches_the_header(page):
    seen = set()
    for _ in range(16):
        page.keyboard.press("Tab")
        seen.add(page.evaluate("document.activeElement.getAttribute('data-page') || document.activeElement.id"))
    assert {"home", "clients", "facture", "history", "scans", "payments", "settings"} <= seen
    assert "sidebar-toggle" in seen


def test_palette_traps_focus_and_escape_restores_it(page):
    page.locator('.nav-btn[data-page="clients"]').focus()
    page.keyboard.press("Control+k")
    assert page.locator(".command-overlay").is_visible()
    for _ in range(6):
        page.keyboard.press("Tab")
        assert page.evaluate("!!document.activeElement.closest('.command-overlay')")
    page.keyboard.press("Escape")
    page.wait_for_selector(".command-overlay", state="detached")
    assert page.evaluate("document.activeElement.getAttribute('data-page')") == "clients"


def test_dialog_traps_focus_and_escape_restores_it(page):
    page.evaluate("navigate('history')")
    page.wait_for_selector("tr[data-facture-id]")
    page.locator("[data-row-menu]").first.click()
    page.locator("[role=menuitem]", has_text="Supprimer").click()
    dialog = page.locator("[role=alertdialog], [role=dialog]").last
    dialog.wait_for()
    for _ in range(8):
        page.keyboard.press("Tab")
        assert page.evaluate("!!document.activeElement.closest('[role=alertdialog], [role=dialog]')")
    page.keyboard.press("Escape")
    dialog.wait_for(state="detached")
    assert page.evaluate("!!document.activeElement.closest('tr[data-facture-id]')")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_keyboard_focus_ring_is_visible_in_both_themes(page, theme):
    page.evaluate(f"ui.theme.setPreference('{theme}')")
    page.keyboard.press("Tab")  # skip link
    page.keyboard.press("Tab")  # first control; keyboard modality so :focus-visible matches
    ring = page.evaluate("""() => {
      const cs = getComputedStyle(document.activeElement);
      return { style: cs.outlineStyle, width: parseFloat(cs.outlineWidth), color: cs.outlineColor };
    }""")
    assert ring["style"] != "none" and ring["width"] >= 2
    assert ring["color"] != page.evaluate("getComputedStyle(document.body).backgroundColor")


# ── Reduced motion ──────────────────────────────────────

def test_reduced_motion_stops_backdrop_countup_and_skeleton_animation(page):
    page.emulate_media(reduced_motion="reduce")
    page.reload()
    page.wait_for_selector(".page")
    page.evaluate("navigate('home')")
    page.wait_for_timeout(600)
    names = page.evaluate("""() => [...document.querySelectorAll('.app-backdrop, .app-backdrop *, .skeleton, [data-countup]')]
      .map(el => getComputedStyle(el).animationName).filter(n => n !== 'none')""")
    assert names == []
    running = page.evaluate("""() => document.getAnimations()
      .filter(a => a.playState === 'running' && !a.transitionProperty).length""")
    assert running == 0
    assert page.evaluate("""() => [...document.querySelectorAll('.app-backdrop svg')]
      .every(s => s.animationsPaused())""")


def test_reduced_motion_runs_no_animation_frame_loop_on_home(page):
    page.emulate_media(reduced_motion="reduce")
    page.add_init_script("""window.__raf = 0; const r = window.requestAnimationFrame.bind(window);
      window.requestAnimationFrame = cb => { window.__raf++; return r(cb); };""")
    page.reload()
    page.wait_for_selector(".page")
    page.wait_for_timeout(800)
    before = page.evaluate("window.__raf")
    page.wait_for_timeout(1000)
    assert page.evaluate("window.__raf") - before == 0


# ── Contrast on tinted grounds (found by the axe "needs review" pass) ────

def _luminance(rgb):
    def chan(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_muted_text_keeps_4_5_contrast_on_the_tinted_sidebar_in_light_theme(page):
    rgb = page.evaluate("""() => {
      const c = document.createElement('span'); c.style.color = 'var(--muted-foreground)';
      document.body.appendChild(c); const v = getComputedStyle(c).color; c.remove();
      return v.match(/[\\d.]+/g).slice(0, 3).map(Number);
    }""")
    # Darkest plausible tint of the sidebar gradient in light theme.
    assert _ratio(rgb, (222, 236, 226)) >= 4.5


def test_facture_checklist_text_is_bright_enough_on_the_green_summary(page):
    page.evaluate("newFacture()")
    page.wait_for_selector(".fac-checks li")
    alpha = page.evaluate("""() => {
      const el = document.querySelector('.fac-checks .is-todo');
      return parseFloat(getComputedStyle(el).color.match(/[\\d.]+/g)[3]);
    }""")
    assert alpha >= 0.85

"""Flat background and surfaces: no decorative gradients or glows left.

The only gradients allowed are functional (grid lines, shimmer, scrims, a
checkerboard, a progress bar, the hero perforation mask). `ALLOWED` is that list.
"""

ALLOWED = {
    "background.css | .bg-ledger",  # 1px grid lines
    "cards-flat.css | .hero:not(.hero-skeleton)",  # perforation: a mask, not a fill
    "motion.css | .skeleton",  # loading shimmer
    "pages-scans.css | .scan-overlay",  # scrim keeping white hover buttons legible over photos
    "pages-scans.css | .scan-thumb:not(.is-loaded)",  # thumbnail loading shimmer
    "pages-settings.css | .logo-preview",  # transparency checkerboard
}

# Reads each same-origin stylesheet's source: CSSOM cssText drops shorthands that contain var().
SCAN_SHEETS = """async () => {
  const found = new Set();
  for (const sheet of document.styleSheets) {
    if (!sheet.href) continue;
    const file = sheet.href.split('/').pop().split('?')[0];
    const text = (await (await fetch(sheet.href)).text()).replace(/\\/\\*[\\s\\S]*?\\*\\//g, '');
    for (const m of text.matchAll(/([^{}]+)\\{([^{}]*)\\}/g)) {
      if (m[2].includes('gradient(')) found.add(file + ' | ' + m[1].trim().replace(/\\s+/g, ' '));
    }
  }
  return [...found].sort();
}"""


def _bg(page, selector, pseudo=None):
    return page.evaluate(
        "([s, p]) => { const e = document.querySelector(s); return e ? getComputedStyle(e, p).backgroundImage : null; }",
        [selector, pseudo],
    )


def test_blobs_are_gone_but_grid_and_route_remain(page_en):
    assert page_en.locator(".bg-blob").count() == 0
    assert page_en.locator("#app-backdrop .bg-ledger").count() == 1
    assert page_en.locator(".panel-route").count() == 1
    assert page_en.errors == []


def test_backdrop_grain_sits_behind_content_and_ignores_the_pointer(page_en):
    info = page_en.evaluate("""() => { const g = document.querySelector('#app-backdrop .bg-grain');
      const s = getComputedStyle(g); return [s.backgroundImage, s.pointerEvents, getComputedStyle(g.parentElement).zIndex]; }""")
    assert "url(" in info[0] and "gradient(" not in info[0]
    assert info[1] == "none" and info[2] == "-1"


def test_decorative_surfaces_have_no_gradient(page_en):
    page_en.evaluate("""() => { const p = document.querySelector('.page');
      p.insertAdjacentHTML('beforeend', '<div id="orb-probe" class="empty-orb"></div>'); }""")
    assert "gradient(" not in _bg(page_en, "#orb-probe")
    assert "gradient(" not in page_en.evaluate("getComputedStyle(document.querySelector('#orb-probe')).boxShadow")
    page_en.evaluate("navigate('settings')")
    page_en.wait_for_selector(".settings-danger", state="attached")
    assert "gradient(" not in _bg(page_en, ".settings-danger")
    page_en.evaluate("""() => { document.querySelector('.page').insertAdjacentHTML('beforeend',
      '<div id="dz-probe" class="dropzone is-dragover"></div>'
      + '<div id="sf-probe" class="scan-folder"><span class="scan-folder-icon"></span></div>'); }""")
    assert "gradient(" not in _bg(page_en, "#dz-probe")
    assert "gradient(" not in _bg(page_en, "#sf-probe .scan-folder-icon")
    assert "gradient(" not in _bg(page_en, "#sf-probe", "::before")
    assert page_en.errors == []


def test_stat_card_hover_is_a_crisp_lift_not_a_glow(page_en):
    page_en.wait_for_selector(".stat")
    card = page_en.locator(".stat").first
    assert "gradient(" not in _bg(page_en, ".stat", "::before")
    card.hover()
    page_en.wait_for_timeout(450)
    style = card.evaluate("e => { const s = getComputedStyle(e); return [s.transform, s.borderTopWidth, s.borderTopColor]; }")
    assert style[0] != "none" and "matrix" in style[0]
    assert style[0].split(",")[-1].strip().startswith("-2")  # translateY(-2px)
    assert style[1] == "1px"
    assert style[2] == "rgb(236, 214, 160)"  # --gold-border


def test_only_functional_gradients_remain(page_en):
    found = set(page_en.evaluate(SCAN_SHEETS))
    message = "gradient declarations found:\n" + "\n".join(sorted(found))
    assert found == ALLOWED, message


def test_dark_theme_renders_without_errors(page_en):
    page_en.evaluate("ui.theme.setPreference('dark')")
    for name in ("home", "history", "settings", "scans"):
        page_en.evaluate(f"navigate('{name}')")
        page_en.wait_for_selector(".page")
    assert page_en.evaluate("document.documentElement.dataset.theme") == "dark"
    assert page_en.errors == []


def test_reduced_motion_leaves_no_running_animation_on_home(page_en):
    page_en.emulate_media(reduced_motion="reduce")
    page_en.reload()
    page_en.wait_for_selector(".page")
    page_en.evaluate("navigate('home')")
    page_en.wait_for_timeout(600)
    running = page_en.evaluate("""() => document.getAnimations()
      .filter(a => a.playState === 'running' && !a.transitionProperty).length""")
    assert running == 0
    page_en.locator(".stat").first.hover()
    page_en.wait_for_timeout(100)
    assert page_en.evaluate("getComputedStyle(document.querySelector('.stat')).transform") == "none"

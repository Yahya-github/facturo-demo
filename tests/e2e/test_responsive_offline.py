"""No horizontal overflow at four viewport sizes, and a fully offline first paint.

The app runs on a machine that may have no internet at all, so fonts and icons
must come from the local server: every non-localhost request is aborted here
and the page must still render with zero failed requests.
"""

from urllib.parse import urlparse

import pytest

from tests.helpers.pdf_writer import make_text_pdf

PAGES = ["home", "facture", "history", "clients", "scans", "payments", "settings"]
VIEWPORTS = [(1440, 900), (1024, 768), (768, 1024), (390, 844)]


@pytest.fixture(autouse=True)
def _fast_timeouts(page):
    page.set_default_timeout(5000)


def _overflow(page):
    return page.evaluate("[document.scrollingElement.scrollWidth, innerWidth]")


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_no_horizontal_overflow_on_any_page(page, width, height):
    page.set_viewport_size({"width": width, "height": height})
    for name in PAGES:
        page.evaluate(f"navigate('{name}')")
        page.wait_for_selector(".page")
        page.wait_for_timeout(300)
        scroll_w, inner_w = _overflow(page)
        assert scroll_w <= inner_w, f"{name} at {width}px scrolls sideways ({scroll_w} > {inner_w})"


@pytest.mark.parametrize("width", [768, 390])
def test_payment_detail_fits_small_screens(page, tmp_path, width):
    pdf = tmp_path / "quittance-responsive.pdf"
    pdf.write_bytes(make_text_pdf([
        "01-09-2026", "Import Responsive Inc.", "1 rue Test", "Ville, QC H0H 0H0",
        "Quittance # 901-777", "BILLET DATE IMMAT CLIENT / CHANTIER / NOTES QTE PRIX EXT",
        "CLIENT E2E INC. / Chantier A 8 120,00 $ 960,00 $", "900001 01-09-2026 l123456",
        "TOTAL: 960,00 $",
    ]))
    page.set_viewport_size({"width": width, "height": 900})
    page.evaluate("openPayments()")
    page.wait_for_selector("#payment-file-input", state="attached")
    page.set_input_files("#payment-file-input", str(pdf))
    page.wait_for_selector("#payment-detail")
    scroll_w, inner_w = _overflow(page)
    assert scroll_w <= inner_w


def test_app_renders_offline_with_local_fonts_and_icons(page):
    blocked, failed = [], []

    def only_localhost(route):
        if urlparse(route.request.url).hostname in ("127.0.0.1", "localhost"):
            route.continue_()
        else:
            blocked.append(route.request.url)
            route.abort()

    page.context.route("**/*", only_localhost)
    page.on("requestfailed", lambda r: failed.append(r.url))
    page.reload()
    page.wait_for_selector(".page")
    for name in PAGES:
        page.evaluate(f"navigate('{name}')")
        page.wait_for_selector(".page")

    fonts = page.evaluate("""Promise.all([
      document.fonts.load('400 16px Geist'), document.fonts.load('600 16px Geist'),
      document.fonts.load('400 14px "Geist Mono"'),
    ]).then(() => [document.fonts.check('16px Geist'), document.fonts.check('600 16px Geist'),
                   document.fonts.check('14px "Geist Mono"')])""")
    assert fonts == [True, True, True]
    assert page.evaluate("[...document.querySelectorAll('i[data-icon]')].filter(i => !i.querySelector('svg')).length") == 0
    assert page.locator(".nav-btn svg").count() == 7
    assert blocked == []
    assert failed == []
    assert [e for e in page.errors if "ERR_" in e] == []

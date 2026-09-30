"""Flat brand cards: no colour gradients, a decorative DRAFT/READY stamp, no overflow."""

import pytest

from tests.helpers.pdf_writer import make_text_pdf


def _bg(page, selector):
    return page.evaluate(
        "s => { const e = document.querySelector(s); return e ? getComputedStyle(e).backgroundImage : null; }",
        selector,
    )


def _open_new_invoice(pg):
    pg.evaluate("newFacture()")
    pg.wait_for_selector(".fac-checks li")


def _assert_no_colour_gradient(value, label):
    assert value is not None, f"{label} not found"
    assert "gradient(" not in value, f"{label} still has a gradient: {value[:120]}"


def test_home_hero_and_ribbon_are_flat(page_en):
    page_en.wait_for_selector(".hero:not(.hero-skeleton)")
    _assert_no_colour_gradient(_bg(page_en, ".hero"), ".hero")
    page_en.evaluate("navigate('history')")
    page_en.wait_for_selector(".flt-summary")
    _assert_no_colour_gradient(_bg(page_en, ".flt-summary"), ".flt-summary")
    assert page_en.evaluate(
        "() => getComputedStyle(document.querySelector('.flt-summary-item.is-owed') || document.body).backgroundImage"
    ).count("gradient(") == 0
    assert page_en.errors == []


def test_hero_perforation_is_a_mask_not_a_background(page_en):
    page_en.wait_for_selector(".hero:not(.hero-skeleton)")
    mask = page_en.evaluate("getComputedStyle(document.querySelector('.hero')).maskImage")
    assert "radial-gradient" in mask


def test_invoice_summary_is_flat(page_en):
    _open_new_invoice(page_en)
    _assert_no_colour_gradient(_bg(page_en, ".fac-summary"), ".fac-summary")
    assert "url(" in _bg(page_en, ".fac-summary")  # the grain layer


def test_payment_ledger_is_flat_without_stamp(page_en, tmp_path):
    text = "\n".join([
        "01-09-2026", "Flat E2E Inc. (0000-0000 Qc inc.)", "1 rue Test", "Ville, QC H0H 0H0",
        "Quittance # 900-777",
        "BILLET DATE IMMAT CLIENT / CHANTIER / NOTES QTE PRIX EXT",
        "CLIENT E2E INC. / Chantier A 8 120,00 $ 960,00 $",
        "900001 01-09-2026 l123456", "TOTAL: 960,00 $",
    ])
    pdf = tmp_path / "flat.pdf"
    pdf.write_bytes(make_text_pdf(text.split("\n")))
    page_en.click('.nav-btn[data-page="payments"]')
    page_en.wait_for_selector("#payment-file-input", state="attached")
    page_en.set_input_files("#payment-file-input", str(pdf))
    page_en.wait_for_selector(".pay-ledger")
    _assert_no_colour_gradient(_bg(page_en, ".pay-ledger"), ".pay-ledger")
    assert "url(" in _bg(page_en, ".pay-ledger")
    assert page_en.locator(".pay-ledger .fac-stamp").count() == 0
    assert page_en.locator(".pay-ledger .fac-stamp-row").count() == 0
    assert page_en.errors == []


@pytest.mark.parametrize("fixture,draft,ready", [("page_en", "DRAFT", "READY"), ("page", "BROUILLON", "PRÊT")])
def test_stamp_flips_from_draft_to_ready(fixture, draft, ready, request):
    pg = request.getfixturevalue(fixture)
    _open_new_invoice(pg)
    stamp = pg.locator(".fac-summary .fac-stamp")
    assert stamp.inner_text().strip().upper() == draft
    assert stamp.get_attribute("aria-hidden") == "true"
    pg.select_option("#fac-client", index=1)
    pg.fill('.billet-input[data-idx="0"][data-field="quantite"]', "10")
    pg.fill('.billet-input[data-idx="0"][data-field="taux"]', "100")
    pg.wait_for_function("() => document.querySelectorAll('.fac-checks li.is-ok').length >= 1")
    statuses = pg.eval_on_selector_all(".fac-checks li", "els => els.map(e => e.className)")
    if all(c == "is-ok" for c in statuses):
        pg.wait_for_selector(".fac-stamp.is-ready")
        assert pg.locator(".fac-summary .fac-stamp").inner_text().strip().upper() == ready
    else:
        pytest.fail(f"checklist not complete: {statuses}")
    assert pg.errors == []


def test_stamp_is_static_and_clear_of_the_total(page_en):
    _open_new_invoice(page_en)
    page_en.select_option("#fac-client", index=1)
    page_en.fill('.billet-input[data-idx="0"][data-field="quantite"]', "10")
    page_en.fill('.billet-input[data-idx="0"][data-field="taux"]', "100")
    page_en.wait_for_selector(".fac-stamp.is-ready")
    info = page_en.evaluate(
        """() => {
          const s = document.querySelector('.fac-stamp');
          const st = getComputedStyle(s);
          const a = s.getBoundingClientRect();
          const b = document.querySelector('[data-fac-total]').getBoundingClientRect();
          return {anim: st.animationName, trans: st.transitionDuration,
                  hit: !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom)};
        }"""
    )
    assert info["anim"] == "none"
    assert set(info["trans"].split(", ")) <= {"0s"}
    assert not info["hit"]


@pytest.mark.parametrize("fixture", ["page_en", "page"])
def test_no_horizontal_overflow_at_390(fixture, request):
    pg = request.getfixturevalue(fixture)
    pg.set_viewport_size({"width": 390, "height": 844})
    for script, selector in [("navigate('home')", ".hero"), ("newFacture()", ".fac-summary")]:
        pg.evaluate(script)
        pg.wait_for_selector(selector)
        pg.wait_for_timeout(300)
        over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert over <= 0, f"{script}: {over}px overflow"
        if selector == ".fac-summary":
            stamp = pg.locator(".fac-stamp").bounding_box()
            assert stamp["x"] >= 0 and stamp["x"] + stamp["width"] <= 390
    assert pg.errors == []

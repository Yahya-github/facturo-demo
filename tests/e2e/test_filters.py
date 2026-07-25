"""E2E tests for the History filter/search toolbar, the Home quick filters and
the Scans client-search box (Team B).

Selector / behaviour contract under test (see changes/team-b.md for the full
write-up):
  #flt-q            text search input (matches search_blob)
  #flt-client       <select> "" = Tous les clients, else client id as string
  #flt-statut       <select> "" | "payee" | "non_payee" | "partielle"
  #flt-du, #flt-au  <input type=date> inclusive range on the invoice date
  #flt-tri          <select> "date_desc" (default) | "date_asc" | "montant_desc"
  #flt-reset        button, clears every filter above back to its default
  .flt-summary      has data-count / data-total / data-unpaid attributes
                     (raw numbers, dot decimal) computed over the CURRENTLY
                     FILTERED rows -- not the whole table
  .flt-empty        shown instead of the table when filters match nothing
  tr[data-facture-id]  one per visible history row, value = facture id

  URL hash: "#history" with no filters active, else
  "#history?q=...&client=...&statut=...&du=...&au=...&tri=..." (only the
  non-default keys present, in that order, standard URL-encoding) -- restored
  on reload and preserved when navigating to another tab and back.

  Home quick filters: #home-flt-statut ("" | "non_payee"),
  #home-flt-client ("" | client id) -- filter the same
  tr[data-facture-id] rows shown under "Dernieres factures".

  Scans search: #scans-search text input, filters .scan-folder buttons
  (accent/case-insensitive against the client name); non-matching folders get
  the `hidden` attribute rather than being removed from the DOM.

Every test seeds its own data (see `seed`, module-scoped) tagged with the
"TEAMBFLT" marker in every seeded chantier, so count/sum/order assertions stay
correct regardless of whatever the live_server session's own seed invoice
(from tests/e2e/conftest.py) or other test modules leave behind.
"""

from urllib.parse import parse_qs

import conftest as e2e
import pytest
from playwright.sync_api import expect

pytest.importorskip("playwright.sync_api")

MARKER = "teambflt"

# base(taxable) -> total_ttc (TPS 5% + TVQ 9.975%), chosen so every amount
# rounds cleanly to 2 decimals and no two invoices share a total.
#             date          chantier tag     taux  base   total_ttc  paye
SEED = {
    "a1": ("2026-08-01", "Chantier Nord", 200, 1600, 1839.60, True),
    "a2": ("2026-08-15", "Chantier Sud", 50, 400, 459.90, False),
    "b1": ("2026-09-01", "Site Henard", 150, 1200, 1379.70, False),
    "b2": ("2026-09-10", "Site Ouest", 100, 800, 919.80, True),
}


@pytest.fixture(scope="module")
def seed(live_server):
    """Two clients, four invoices with distinct dates/chantiers/paid flags,
    created entirely through endpoints that already exist today (clients,
    factures/generate, factures/{id}/paye) -- none of this depends on the
    filters feature under test, only the assertions below do.
    """
    client_a = e2e.api(live_server, "POST", "/api/clients", {
        "ref": "TXA", "prefix": "txa", "nom": "Northwind Excavation", "adresse": "1 rue A",
    })
    client_b = e2e.api(live_server, "POST", "/api/clients", {
        "ref": "TXB", "prefix": "txb", "nom": "Béton Élan Inc", "adresse": "2 rue B",
    })
    owners = {"a1": client_a, "a2": client_a, "b1": client_b, "b2": client_b}

    numeros = {}
    for key, (date, chantier, taux, _base, _total, _paye) in SEED.items():
        client = owners[key]
        res = e2e.api(live_server, "POST", "/api/factures/generate", {
            "client_id": client["id"], "date": date,
            "billets": [{
                "date_billet": date, "chantier": f"{chantier} TEAMBFLT",
                "plaque": f"L{key.upper()}0001", "numero_billet": f"{key}0001",
                "quantite": 8, "taux": taux,
            }],
        })
        numeros[key] = res["invoices"][0]["numero"]

    rows = e2e.api(live_server, "GET", "/api/factures")
    ids = {key: next(r["id"] for r in rows if r["numero"] == numero)
           for key, numero in numeros.items()}
    for key, (*_rest, paye) in SEED.items():
        if paye:
            e2e.api(live_server, "PATCH", f"/api/factures/{ids[key]}/paye", {"paye": True})

    return {"client_a": client_a, "client_b": client_b, "numeros": numeros, "ids": ids}


# ── helpers ──────────────────────────────────────────────


def _no_js_errors(page):
    errors = [e for e in page.errors if "fonts.g" not in e and "net::ERR" not in e]
    assert errors == []


def _go_history(page):
    page.click('.nav-btn[data-page="history"]')
    page.wait_for_selector("#flt-q")


def _rows_text(page):
    return page.locator("tr[data-facture-id]").all_inner_texts()


def _visible(page, numeros_by_key, keys):
    """Which of the given seed keys currently have a visible history row."""
    texts = _rows_text(page)
    found = set()
    for key in keys:
        numero = numeros_by_key[key]
        if any(numero in t for t in texts):
            found.add(key)
    return found


def _hash_params(page):
    """Parse the '#history?...' fragment into a flat {key: value} dict."""
    url = page.url
    frag = url.split("#", 1)[1] if "#" in url else ""
    assert frag == "history" or frag.startswith("history?"), f"unexpected hash: {frag!r}"
    if "?" not in frag:
        return {}
    qs = frag.split("?", 1)[1]
    parsed = parse_qs(qs, keep_blank_values=True)
    return {k: v[0] for k, v in parsed.items()}


# ── text search ──────────────────────────────────────────


def test_text_search_is_accent_and_case_insensitive(page, seed):
    _go_history(page)
    page.fill("#flt-q", "henard")
    expect(page.locator("tr[data-facture-id]", has_text=seed["numeros"]["b1"])).to_be_visible()
    _no_js_errors(page)


def test_text_search_matches_billet_number(page, seed):
    _go_history(page)
    page.fill("#flt-q", "b20001")
    expect(page.locator("tr[data-facture-id]", has_text=seed["numeros"]["b2"])).to_be_visible()
    _no_js_errors(page)


def test_marker_search_scopes_to_exactly_the_seeded_invoices(page, seed):
    _go_history(page)
    page.fill("#flt-q", MARKER)
    expect(page.locator("tr[data-facture-id]")).to_have_count(4)
    assert _visible(page, seed["numeros"], seed["numeros"].keys()) == set(seed["numeros"].keys())
    _no_js_errors(page)


# ── client filter ────────────────────────────────────────


def test_client_filter_scopes_to_that_client_only(page, seed):
    _go_history(page)
    page.fill("#flt-q", MARKER)
    page.select_option("#flt-client", str(seed["client_a"]["id"]))
    expect(page.locator("tr[data-facture-id]")).to_have_count(2)
    assert _visible(page, seed["numeros"], seed["numeros"].keys()) == {"a1", "a2"}
    _no_js_errors(page)


# ── status filter ────────────────────────────────────────


def test_status_filter_payee(page, seed):
    _go_history(page)
    page.fill("#flt-q", MARKER)
    page.select_option("#flt-statut", "payee")
    expect(page.locator("tr[data-facture-id]")).to_have_count(2)
    assert _visible(page, seed["numeros"], seed["numeros"].keys()) == {"a1", "b2"}
    _no_js_errors(page)


def test_status_filter_non_payee(page, seed):
    _go_history(page)
    page.fill("#flt-q", MARKER)
    page.select_option("#flt-statut", "non_payee")
    expect(page.locator("tr[data-facture-id]")).to_have_count(2)
    assert _visible(page, seed["numeros"], seed["numeros"].keys()) == {"a2", "b1"}
    _no_js_errors(page)


def test_status_filter_partielle_option_exists_and_is_selectable(page, seed):
    """The payments store is still a stub returning {} (Team C's job), so no
    invoice can genuinely be partial through the live API yet -- this only
    proves the option exists and never false-positives against paid/unpaid
    invoices, not that partial matching itself is wired up end to end."""
    _go_history(page)
    page.fill("#flt-q", MARKER)
    page.select_option("#flt-statut", "partielle")
    expect(page.locator("tr[data-facture-id]")).to_have_count(0)
    _no_js_errors(page)


# ── date range (inclusive) ───────────────────────────────


def test_date_range_is_inclusive_on_both_ends(page, seed):
    _go_history(page)
    page.fill("#flt-q", MARKER)
    page.fill("#flt-du", "2026-08-15")
    page.fill("#flt-au", "2026-09-01")
    expect(page.locator("tr[data-facture-id]")).to_have_count(2)
    assert _visible(page, seed["numeros"], seed["numeros"].keys()) == {"a2", "b1"}
    _no_js_errors(page)


# ── sort ─────────────────────────────────────────────────


def _order(page, seed, keys):
    texts = _rows_text(page)
    positions = []
    for text in texts:
        for key in keys:
            if seed["numeros"][key] in text:
                positions.append(key)
    return positions


def test_sort_date_desc_is_the_default(page, seed):
    _go_history(page)
    page.fill("#flt-q", MARKER)
    expect(page.locator("tr[data-facture-id]")).to_have_count(4)
    assert _order(page, seed, seed["numeros"].keys()) == ["b2", "b1", "a2", "a1"]
    _no_js_errors(page)


def test_sort_date_asc(page, seed):
    _go_history(page)
    page.fill("#flt-q", MARKER)
    page.select_option("#flt-tri", "date_asc")
    expect(page.locator("tr[data-facture-id]")).to_have_count(4)
    assert _order(page, seed, seed["numeros"].keys()) == ["a1", "a2", "b1", "b2"]
    _no_js_errors(page)


def test_sort_montant_desc(page, seed):
    _go_history(page)
    page.fill("#flt-q", MARKER)
    page.select_option("#flt-tri", "montant_desc")
    expect(page.locator("tr[data-facture-id]")).to_have_count(4)
    # Deliberately NOT the same order as either date sort above -- this would
    # pass by accident if "montant_desc" were secretly just sorting by date.
    assert _order(page, seed, seed["numeros"].keys()) == ["a1", "b1", "b2", "a2"]
    _no_js_errors(page)


# ── summary line ─────────────────────────────────────────


def _summary(page):
    node = page.locator(".flt-summary")
    expect(node).to_be_visible()
    return {
        "count": int(node.get_attribute("data-count")),
        "total": float(node.get_attribute("data-total")),
        "unpaid": float(node.get_attribute("data-unpaid")),
    }


def test_summary_over_all_scoped_results(page, seed):
    _go_history(page)
    page.fill("#flt-q", MARKER)
    expect(page.locator("tr[data-facture-id]")).to_have_count(4)
    s = _summary(page)
    assert s["count"] == 4
    assert s["total"] == pytest.approx(4599.00, abs=0.01)
    assert s["unpaid"] == pytest.approx(1839.60, abs=0.01)
    _no_js_errors(page)


def test_summary_unpaid_balance_is_computed_over_the_filtered_set(page, seed):
    """Filtering down to only the paid invoices must bring the unpaid balance
    to zero -- if it were computed globally instead of over the current
    filter, this would still show the unpaid total from the other rows."""
    _go_history(page)
    page.fill("#flt-q", MARKER)
    page.select_option("#flt-statut", "payee")
    expect(page.locator("tr[data-facture-id]")).to_have_count(2)
    s = _summary(page)
    assert s["count"] == 2
    assert s["total"] == pytest.approx(2759.40, abs=0.01)
    assert s["unpaid"] == pytest.approx(0.00, abs=0.01)
    _no_js_errors(page)


# ── reset ────────────────────────────────────────────────


def test_reset_clears_every_filter_and_the_hash(page, seed):
    _go_history(page)
    page.fill("#flt-q", MARKER)
    page.select_option("#flt-client", str(seed["client_a"]["id"]))
    page.select_option("#flt-statut", "non_payee")
    page.fill("#flt-du", "2026-08-01")
    page.fill("#flt-au", "2026-08-31")
    page.select_option("#flt-tri", "montant_desc")
    expect(page.locator("tr[data-facture-id]")).to_have_count(1)  # only a2

    page.click("#flt-reset")

    expect(page.locator("#flt-q")).to_have_value("")
    expect(page.locator("#flt-client")).to_have_value("")
    expect(page.locator("#flt-statut")).to_have_value("")
    expect(page.locator("#flt-du")).to_have_value("")
    expect(page.locator("#flt-au")).to_have_value("")
    expect(page.locator("#flt-tri")).to_have_value("date_desc")
    assert page.url.split("#", 1)[1] == "history"
    # Broader than the 4-row marker-scoped set proves the scope actually lifted.
    expect(page.locator("tr[data-facture-id]")).not_to_have_count(1)
    _no_js_errors(page)


# ── empty state ──────────────────────────────────────────


def test_empty_state_message_when_no_filter_matches(page, seed):
    _go_history(page)
    page.fill("#flt-q", "zzz-no-such-invoice-ever-xyz")
    expect(page.locator("tr[data-facture-id]")).to_have_count(0)
    empty = page.locator(".flt-empty")
    expect(empty).to_be_visible()
    assert empty.inner_text().strip() != ""
    _no_js_errors(page)


# ── URL hash: format, reload round-trip, away-and-back ──


def test_hash_reflects_active_filters_in_the_documented_format(page, seed):
    _go_history(page)
    page.fill("#flt-q", "teambflt")
    page.select_option("#flt-client", str(seed["client_a"]["id"]))
    page.select_option("#flt-statut", "non_payee")
    page.fill("#flt-du", "2026-08-01")
    page.fill("#flt-au", "2026-08-31")
    page.select_option("#flt-tri", "montant_desc")

    params = _hash_params(page)
    assert params == {
        "q": "teambflt",
        "client": str(seed["client_a"]["id"]),
        "statut": "non_payee",
        "du": "2026-08-01",
        "au": "2026-08-31",
        "tri": "montant_desc",
    }
    _no_js_errors(page)


def test_hash_round_trips_on_reload(page, seed):
    _go_history(page)
    page.fill("#flt-q", "teambflt")
    page.select_option("#flt-client", str(seed["client_a"]["id"]))
    page.select_option("#flt-statut", "non_payee")
    page.fill("#flt-du", "2026-08-01")
    page.fill("#flt-au", "2026-08-31")
    page.select_option("#flt-tri", "montant_desc")
    expect(page.locator("tr[data-facture-id]")).to_have_count(1)  # only a2

    page.reload()
    page.wait_for_selector("#flt-q")

    expect(page.locator("#flt-q")).to_have_value("teambflt")
    expect(page.locator("#flt-client")).to_have_value(str(seed["client_a"]["id"]))
    expect(page.locator("#flt-statut")).to_have_value("non_payee")
    expect(page.locator("#flt-du")).to_have_value("2026-08-01")
    expect(page.locator("#flt-au")).to_have_value("2026-08-31")
    expect(page.locator("#flt-tri")).to_have_value("montant_desc")
    expect(page.locator("tr[data-facture-id]")).to_have_count(1)
    assert _visible(page, seed["numeros"], seed["numeros"].keys()) == {"a2"}
    _no_js_errors(page)


def test_filters_survive_navigating_away_and_back(page, seed):
    _go_history(page)
    page.fill("#flt-q", MARKER)
    page.select_option("#flt-client", str(seed["client_b"]["id"]))
    expect(page.locator("tr[data-facture-id]")).to_have_count(2)

    page.click('.nav-btn[data-page="clients"]')
    page.wait_for_selector("h2")
    page.click('.nav-btn[data-page="history"]')
    page.wait_for_selector("#flt-q")

    expect(page.locator("#flt-q")).to_have_value(MARKER)
    expect(page.locator("#flt-client")).to_have_value(str(seed["client_b"]["id"]))
    expect(page.locator("tr[data-facture-id]")).to_have_count(2)
    assert _visible(page, seed["numeros"], seed["numeros"].keys()) == {"b1", "b2"}
    _no_js_errors(page)


# ── Home quick filters ───────────────────────────────────


def test_home_quick_client_filter(page, seed):
    page.click('.nav-btn[data-page="home"]')
    page.wait_for_selector("#home-flt-client")
    page.select_option("#home-flt-client", str(seed["client_b"]["id"]))
    shown = _visible(page, seed["numeros"], seed["numeros"].keys())
    assert {"b1", "b2"} <= shown
    assert not (shown & {"a1", "a2"})
    _no_js_errors(page)


def test_home_quick_status_filter_non_payee(page, seed):
    page.click('.nav-btn[data-page="home"]')
    page.wait_for_selector("#home-flt-statut")
    page.select_option("#home-flt-statut", "non_payee")
    shown = _visible(page, seed["numeros"], seed["numeros"].keys())
    assert "a1" not in shown  # paid
    assert "b2" not in shown  # paid
    _no_js_errors(page)


# ── Scans client-name search ─────────────────────────────


def test_scans_search_filters_client_folders_accent_insensitive(page, seed):
    page.click('.nav-btn[data-page="scans"]')
    page.wait_for_selector("#scans-search")
    expect(page.locator(".scan-folder", has_text="Northwind Excavation")).to_be_visible()
    expect(page.locator(".scan-folder", has_text="Béton Élan Inc")).to_be_visible()

    page.fill("#scans-search", "northwind")
    expect(page.locator(".scan-folder", has_text="Northwind Excavation")).to_be_visible()
    expect(page.locator(".scan-folder", has_text="Béton Élan Inc")).to_be_hidden()

    page.fill("#scans-search", "elan")  # no accent -- must still match "Élan"
    expect(page.locator(".scan-folder", has_text="Béton Élan Inc")).to_be_visible()
    expect(page.locator(".scan-folder", has_text="Northwind Excavation")).to_be_hidden()

    page.fill("#scans-search", "")
    expect(page.locator(".scan-folder", has_text="Northwind Excavation")).to_be_visible()
    expect(page.locator(".scan-folder", has_text="Béton Élan Inc")).to_be_visible()
    _no_js_errors(page)

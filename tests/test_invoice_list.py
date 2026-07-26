"""Tests for GET /api/factures: the filters/search summary fields (Team B).

Every test runs against a throwaway database (see `fresh_db`), never the real
one -- same isolation pattern as tests/test_known_values.py.

Interface under test (see changes/team-b.md for the full contract):
  * total_ht / total_ttc      -- Totals.base_taxable / Totals.total, rounded 2
  * nb_billets / nb_billets_payes
  * statut_paiement           -- "payee" | "partielle" | "non_payee"
  * search_blob               -- folded text for client-side search

These tests deliberately compute expected totals by calling the real
`invoice_totals()` rather than hard-coding discount math, so they stay valid
while Team A rewrites the internals of invoicing/discounts.py -- only the
signature and the Totals fields (sous_total/remise/base_taxable/tps/tvq/total)
are relied upon.
"""

import json

import pytest
from fastapi.testclient import TestClient

from facturo.core import billet_fields
from facturo.core import database as db
from facturo.invoicing.discounts import invoice_totals
from facturo.payments import store
from facturo.server import app


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """An isolated, empty database for this test only."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _make_client(nom="Client Test", ref="CT", prefix="ct"):
    return db.create_client(ref, prefix, nom, "1 rue Test")


def _billet(**over):
    b = {
        "date_billet": "2026-09-01", "chantier": "Chantier X", "plaque": "L123456",
        "numero_billet": "50001", "quantite": 8, "taux": 100,
        "description": "", "desc_libre": False,
    }
    b.update(over)
    return b


def _make_facture(client_id, numero, date, billets, remise_type="", remise_valeur=0.0, paye=False):
    row = db.save_facture(
        client_id, numero, date, f"{numero}.xlsx",
        billets_json=json.dumps(billets),
        remise_type=remise_type, remise_valeur=remise_valeur,
    )
    if paye:
        db.set_facture_paye(row["id"], True)
        row = db.get_facture(row["id"])
    return row


def _get_row(http_client, facture_id):
    rows = http_client.get("/api/factures").json()
    return next(r for r in rows if r["id"] == facture_id)


# ── total_ht / total_ttc ─────────────────────────────────


def test_list_includes_new_summary_fields_no_discount(fresh_db, client):
    c = _make_client()
    billets = [
        _billet(numero_billet="70001", taux=100, quantite=8),
        _billet(numero_billet="70002", taux=50, quantite=4, chantier="Chantier Y", plaque="M654321"),
    ]
    facture = _make_facture(c["id"], "num001", "2026-09-01", billets)

    resp = client.get("/api/factures")
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["id"] == facture["id"])

    expected = invoice_totals(billets, facture)
    assert row["total_ht"] == round(expected.base_taxable, 2)
    assert row["total_ttc"] == round(expected.total, 2)
    assert row["nb_billets"] == 2
    assert row["nb_billets_payes"] == 0
    assert row["statut_paiement"] == "non_payee"
    # Existing fields must still be there -- this is additive, not a replacement.
    assert row["numero"] == "num001"
    assert row["client_nom"] == c["nom"]
    assert row["paye"] == 0


def test_list_totals_match_invoice_totals_with_percent_discount(fresh_db, client):
    c = _make_client()
    billets = [_billet(numero_billet="70003", taux=200, quantite=8)]
    facture = _make_facture(c["id"], "num002", "2026-09-01", billets,
                             remise_type="percent", remise_valeur=10)

    row = _get_row(client, facture["id"])
    expected = invoice_totals(billets, facture)
    assert row["total_ht"] == round(expected.base_taxable, 2)
    assert row["total_ttc"] == round(expected.total, 2)

    # Sanity: the discount actually reduced the total vs. an undiscounted run
    # over the same billets, so this test would fail if the endpoint ignored
    # the invoice's discount fields.
    undiscounted = invoice_totals(billets, {**facture, "remise_type": "", "remise_valeur": 0})
    assert expected.total < undiscounted.total


def test_totals_rounded_to_two_decimals(fresh_db, client):
    c = _make_client()
    billets = [_billet(numero_billet="99001", quantite=8.333, taux=33.33)]
    facture = _make_facture(c["id"], "round001", "2026-09-01", billets)

    row = _get_row(client, facture["id"])
    expected = invoice_totals(billets, facture)
    assert row["total_ht"] == round(expected.base_taxable, 2)
    assert row["total_ttc"] == round(expected.total, 2)
    assert row["total_ht"] == round(row["total_ht"], 2)
    assert row["total_ttc"] == round(row["total_ttc"], 2)


# ── statut_paiement ──────────────────────────────────────


def test_statut_paiement_payee_overrides_billet_coverage(fresh_db, client):
    """`paye` wins outright, even when the payments store reports nothing paid."""
    c = _make_client()
    facture = _make_facture(c["id"], "num003", "2026-09-01", [_billet(numero_billet="70004")], paye=True)

    row = _get_row(client, facture["id"])
    assert row["statut_paiement"] == "payee"
    assert row["paye"] == 1
    assert row["nb_billets_payes"] == 0


def test_statut_paiement_partielle_from_paid_billets(fresh_db, client, monkeypatch):
    c = _make_client()
    billets = [_billet(numero_billet="70005"), _billet(numero_billet="70006"), _billet(numero_billet="70007")]
    facture = _make_facture(c["id"], "num004", "2026-09-01", billets)
    fid = facture["id"]

    monkeypatch.setattr(
        store, "paid_billets",
        lambda: {(fid, 0): {"paiement_id": 1, "reference": "Q1", "categorie": "paiement"}},
    )

    row = _get_row(client, fid)
    assert row["nb_billets"] == 3
    assert row["nb_billets_payes"] == 1
    assert row["statut_paiement"] == "partielle"


def test_statut_paiement_non_payee_by_default(fresh_db, client):
    c = _make_client()
    facture = _make_facture(c["id"], "num004b", "2026-09-01", [_billet(numero_billet="70004b")])
    row = _get_row(client, facture["id"])
    assert row["nb_billets_payes"] == 0
    assert row["statut_paiement"] == "non_payee"


def test_statut_paiement_full_billet_coverage_without_paye_flag_is_non_payee(fresh_db, client, monkeypatch):
    """Deliberate reading of the spec, spelled out because it looks surprising.

    "partielle" is defined as `0 < nb_billets_payes < nb_billets`, so full
    coverage (nb_billets_payes == nb_billets) does NOT fall into "partielle" --
    and it does not retroactively become "payee" either, since only the `paye`
    column drives that branch. A payment that covers every billet is expected
    to also flip `paye`/`paye_auto` (Team C's job, via paye_auto); until that
    happens the invoice reads "non_payee". This test locks that interpretation
    in so the endpoint isn't "fixed" to silently invent a payee status.
    """
    c = _make_client()
    billets = [_billet(numero_billet="70008"), _billet(numero_billet="70009")]
    facture = _make_facture(c["id"], "num005", "2026-09-01", billets)
    fid = facture["id"]

    monkeypatch.setattr(store, "paid_billets", lambda: {
        (fid, 0): {"paiement_id": 2, "reference": "Q2"},
        (fid, 1): {"paiement_id": 2, "reference": "Q2"},
    })

    row = _get_row(client, fid)
    assert row["nb_billets_payes"] == 2
    assert row["nb_billets"] == 2
    assert row["statut_paiement"] == "non_payee"


# ── search_blob ──────────────────────────────────────────


def test_search_blob_folds_accents_and_case(fresh_db, client):
    c = _make_client(nom="Constructions Hénard Inc", ref="HEN", prefix="hen")
    billets = [_billet(numero_billet="80001", chantier="Chantier Hénard Nord", plaque="K864249")]
    facture = _make_facture(c["id"], "heb001", "2026-09-01", billets)

    row = _get_row(client, facture["id"])
    blob = row["search_blob"]
    assert blob == blob.lower()
    assert billet_fields.fold("Hénard") in blob
    assert billet_fields.fold("K864249") in blob
    assert billet_fields.fold("80001") in blob
    assert billet_fields.fold("heb001") in blob


def test_search_blob_includes_free_description(fresh_db, client):
    c = _make_client()
    billets = [_billet(numero_billet="", chantier="", plaque="", desc_libre=True,
                        description="Deneigement stationnement Ouest")]
    facture = _make_facture(c["id"], "desc001", "2026-09-01", billets)

    row = _get_row(client, facture["id"])
    assert billet_fields.fold("Deneigement") in row["search_blob"]


def test_search_blob_covers_every_billet_not_just_the_first(fresh_db, client):
    c = _make_client()
    billets = [
        _billet(numero_billet="81001", chantier="Alpha", plaque="L100001"),
        _billet(numero_billet="81002", chantier="Bravo", plaque="L100002"),
    ]
    facture = _make_facture(c["id"], "multi001", "2026-09-01", billets)

    blob = _get_row(client, facture["id"])["search_blob"]
    for token in ("81001", "81002", "Alpha", "Bravo", "L100001", "L100002"):
        assert billet_fields.fold(token) in blob


# ── client_id filter ─────────────────────────────────────


def test_client_id_filter_scopes_results(fresh_db, client):
    c1 = _make_client(nom="Client Un", ref="U1", prefix="u1")
    c2 = _make_client(nom="Client Deux", ref="U2", prefix="u2")
    f1 = _make_facture(c1["id"], "u1001", "2026-09-01", [_billet(numero_billet="90001")])
    f2 = _make_facture(c2["id"], "u2001", "2026-09-01", [_billet(numero_billet="90002")])

    rows = client.get("/api/factures", params={"client_id": c1["id"]}).json()
    ids = {r["id"] for r in rows}
    assert f1["id"] in ids
    assert f2["id"] not in ids

    row = next(r for r in rows if r["id"] == f1["id"])
    assert "total_ttc" in row
    assert "search_blob" in row


# ── performance: no N+1 ──────────────────────────────────


def test_store_functions_called_once_per_request(fresh_db, client, monkeypatch):
    c = _make_client()
    for i in range(6):
        _make_facture(c["id"], f"n1p{i:03d}", "2026-09-01", [_billet(numero_billet=f"9{i:04d}")])

    calls = {"billets": 0}

    def _paid_billets():
        calls["billets"] += 1
        return {}

    monkeypatch.setattr(store, "paid_billets", _paid_billets)

    resp = client.get("/api/factures")
    assert len(resp.json()) >= 6
    assert calls["billets"] == 1, "paid_billets() must be called once per request, not once per invoice"


# ── edge cases ───────────────────────────────────────────


def test_no_billets_gives_zero_counts_and_totals(fresh_db, client):
    c = _make_client()
    facture = db.save_facture(c["id"], "empty001", "2026-09-01", "empty001.xlsx", billets_json=None)

    row = _get_row(client, facture["id"])
    assert row["nb_billets"] == 0
    assert row["nb_billets_payes"] == 0
    assert row["statut_paiement"] == "non_payee"
    assert row["total_ht"] == 0.0
    assert row["total_ttc"] == 0.0


def test_empty_billets_list_gives_zero_counts_and_totals(fresh_db, client):
    c = _make_client()
    facture = db.save_facture(c["id"], "empty002", "2026-09-01", "empty002.xlsx", billets_json="[]")

    row = _get_row(client, facture["id"])
    assert row["nb_billets"] == 0
    assert row["total_ht"] == 0.0
    assert row["total_ttc"] == 0.0


def test_malformed_billets_json_does_not_crash(fresh_db, client):
    c = _make_client()
    facture = db.save_facture(c["id"], "bad001", "2026-09-01", "bad001.xlsx", billets_json="{not json")

    resp = client.get("/api/factures")
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["id"] == facture["id"])
    assert row["nb_billets"] == 0
    assert row["total_ht"] == 0.0


def test_billet_breaking_totals_math_does_not_crash(fresh_db, client):
    """Well-formed JSON whose values make invoice_totals raise must not 500 the list."""
    c = _make_client()
    bad = [{"quantite": "abc", "taux": None}, "not a dict"]
    facture = db.save_facture(c["id"], "bad002", "2026-09-01", "bad002.xlsx", billets_json=json.dumps(bad))

    resp = client.get("/api/factures")
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["id"] == facture["id"])
    assert row["total_ht"] == 0.0
    assert row["total_ttc"] == 0.0

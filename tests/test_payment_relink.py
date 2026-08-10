"""Payment links survive invoice edits (PUT /api/factures/{id}).

Links are positional (facture_id, billet_index) into billets_json, so an edit
that reorders, inserts, removes or splits billets must re-seat every link on
the billet it actually paid — or drop it — and recompute the paid state.
Regression for the DB review finding: after a reorder, an unpaid billet showed
as paid and the paid one as unpaid.
"""

import io

import pytest
from fastapi.testclient import TestClient

from facturo.api import payments as payments_api
from facturo.core import database as db
from facturo.payments import pdf_text
from facturo.server import app

A = {"numero_billet": "61001", "date_billet": "2026-09-10", "plaque": "R111111", "quantite": 4}
B = {"numero_billet": "61002", "date_billet": "2026-09-11", "plaque": "R111111", "quantite": 5}
C = {"numero_billet": "61003", "date_billet": "2026-09-12", "plaque": "R222222", "quantite": 6}
X = {"numero_billet": "61009", "date_billet": "2026-09-13", "plaque": "R333333", "quantite": 7}


def _billet(spec, chantier="Chantier A"):
    return {**spec, "chantier": chantier, "taux": 100}


def _quittance(*specs):
    lines = ["15-09-2026", "Emetteur Relink Inc.", "Quittance # 610-001"]
    for s in specs:
        d = s["date_billet"].split("-")
        lines += [f"CLIENT R / Note {s['quantite']} 100,00 $ {s['quantite'] * 100},00 $",
                  f"{s['numero_billet']} {d[2]}-{d[1]}-{d[0]} {s['plaque'].lower()}"]
    return "\n".join(lines + ["TOTAL: 1,00 $"])


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(payments_api, "PAYMENTS_DIR", tmp_path / "paiements")
    with TestClient(app) as c:
        yield c


def _setup(api, monkeypatch, billets, paid_specs, split=False):
    cid = api.post("/api/clients", json={
        "ref": "REL", "prefix": "rel", "nom": "CLIENT RELINK", "adresse": "1 rue R",
        "separer_chantiers": split,
    }).json()["id"]
    api.post("/api/factures/generate", json={
        "client_id": cid, "date": "2026-09-14", "billets": [_billet(b) for b in billets]})
    fid = api.get("/api/factures", params={"client_id": cid}).json()[0]["id"]
    monkeypatch.setattr(pdf_text, "extract_text", lambda raw: _quittance(*paid_specs))
    paiement = api.post("/api/paiements", files={
        "file": ("q.pdf", io.BytesIO(b"%PDF-1.4\nfake\n"), "application/pdf")}).json()
    assert all(ligne["statut"] == "lie" for ligne in paiement["lignes"])
    return cid, fid, paiement


def _edit(api, cid, fid, billets):
    resp = api.put(f"/api/factures/{fid}", json={
        "client_id": cid, "date": "2026-09-14", "billets": billets})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _paid_numeros(api, fid):
    """numero_billet of each billet position, or None when that billet is unpaid."""
    billets = api.get(f"/api/factures/{fid}").json()["billets"]
    state = api.get(f"/api/factures/{fid}/paiements").json()["billets"]
    return [b["numero_billet"] if s["paye"] else None for b, s in zip(billets, state, strict=True)]


def _flags(fid):
    f = db.get_facture(fid)
    return f["paye"], f["paye_auto"]


def test_rotating_billets_keeps_each_link_on_its_own_billet(api, monkeypatch):
    cid, fid, _ = _setup(api, monkeypatch, [A, B, C], [A, B])
    assert _paid_numeros(api, fid) == ["61001", "61002", None]
    _edit(api, cid, fid, [_billet(C), _billet(A), _billet(B)])
    assert _paid_numeros(api, fid) == [None, "61001", "61002"]
    assert _flags(fid) == (0, 0)


def test_swapping_two_linked_billets_never_trips_the_unique_index(api, monkeypatch):
    cid, fid, _ = _setup(api, monkeypatch, [A, B], [A, B])
    assert _flags(fid) == (1, 1)
    _edit(api, cid, fid, [_billet(B), _billet(A)])
    assert _paid_numeros(api, fid) == ["61002", "61001"]
    assert _flags(fid) == (1, 1)


def test_inserting_a_billet_before_shifts_the_links(api, monkeypatch):
    cid, fid, _ = _setup(api, monkeypatch, [A, B], [A, B])
    _edit(api, cid, fid, [_billet(X), _billet(A), _billet(B)])
    assert _paid_numeros(api, fid) == [None, "61001", "61002"]
    assert _flags(fid) == (0, 0)  # the new billet is not paid: auto-paid reverts


def test_deleting_a_linked_billet_unlinks_its_ligne(api, monkeypatch):
    cid, fid, paiement = _setup(api, monkeypatch, [A, B, C], [A, B, C])
    assert _flags(fid) == (1, 1)
    _edit(api, cid, fid, [_billet(A), _billet(C)])
    assert _paid_numeros(api, fid) == ["61001", "61003"]
    assert _flags(fid) == (1, 1)  # every remaining billet is still covered
    lignes = {lg["numero_billet"]: lg for lg in api.get(f"/api/paiements/{paiement['id']}").json()["lignes"]}
    assert lignes["61002"]["statut"] == "non_lie"
    assert lignes["61002"]["methode"] == ""


def test_replacing_a_paid_billet_reverts_auto_paid(api, monkeypatch):
    cid, fid, _ = _setup(api, monkeypatch, [A, B], [A, B])
    _edit(api, cid, fid, [_billet(A), _billet(X)])
    assert _paid_numeros(api, fid) == ["61001", None]
    assert _flags(fid) == (0, 0)


def test_editing_billets_completes_coverage_and_marks_paid(api, monkeypatch):
    """Removing the only unpaid billet now recomputes auto-paid too."""
    cid, fid, _ = _setup(api, monkeypatch, [A, B, X], [A, B])
    assert _flags(fid) == (0, 0)
    _edit(api, cid, fid, [_billet(A), _billet(B)])
    assert _flags(fid) == (1, 1)


def test_split_by_chantier_moves_the_link_to_the_new_invoice(api, monkeypatch):
    cid, fid, _ = _setup(api, monkeypatch, [A, B], [A, B], split=True)
    assert _flags(fid) == (1, 1)
    result = _edit(api, cid, fid, [_billet(A), _billet(B, chantier="Chantier B")])
    assert result["split"] is True
    new_numero = result["invoices"][1]["numero"]
    new_fid = next(f["id"] for f in api.get("/api/factures", params={"client_id": cid}).json()
                   if f["numero"] == new_numero)
    assert _paid_numeros(api, fid) == ["61001"]
    assert _paid_numeros(api, new_fid) == ["61002"]
    assert _flags(fid) == (1, 1)
    assert _flags(new_fid) == (1, 1)


def test_manual_link_follows_its_billet_through_a_reorder(api, monkeypatch):
    """A manual link exists because the payment's own data did not match, so
    it can only follow the billet by the billet's previous identity."""
    cid, fid, paiement = _setup(api, monkeypatch, [A, B], [A])
    extra = api.post(f"/api/paiements/{paiement['id']}/lignes", json={"numero_billet": "99999"}).json()
    assert extra["statut"] == "non_lie"
    linked = api.put(f"/api/paiements/lignes/{extra['id']}", json={"facture_id": fid, "billet_index": 1})
    assert linked.json()["methode"] == "manuel"
    _edit(api, cid, fid, [_billet(X), _billet(B), _billet(A)])
    assert _paid_numeros(api, fid) == [None, "61002", "61001"]
    after = next(lg for lg in api.get(f"/api/paiements/{paiement['id']}").json()["lignes"]
                 if lg["id"] == extra["id"])
    assert (after["statut"], after["methode"], after["billet_index"]) == ("lie", "manuel", 1)


def test_relink_is_a_noop_without_ids_or_links(api):
    from facturo.payments import store
    store.relink_after_invoice_edit(None, [])
    store.relink_after_invoice_edit(None, [12345])  # no such invoice, no lignes

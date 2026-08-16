"""An invoice is a legal document: no request may destroy one silently.

Covers two silent-failure findings on /api/factures:

* Unreadable billets (corrupt billets_json AND no readable xlsx) used to come
  back as ``billets: []``; the editor then showed one blank billet and saving
  regenerated the xlsx under the SAME filename, wiping the real invoice. The
  API now flags ``billets_unreadable`` and PUT refuses (409) unless the client
  sends ``forcer_ecrasement: true``.
* A database failure after the xlsx was written used to leave an orphan file
  (or an overwritten one) and a bare 500. Files written by the failed request
  are now undone, the edit's billets update and payment relink share one
  transaction, and the 500 is in French and names what was created.
"""

import json
import logging
import sqlite3

import pytest
from fastapi.testclient import TestClient

from facturo.core import database as db
from facturo.invoicing import excel_generator as gen
from facturo.payments import store as payment_store
from facturo.server import app


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(gen, "OUTPUT_DIR", tmp_path / "output")
    db.init_db()
    with TestClient(app) as c:
        yield c


def _client(api, split=False, prefix="sec"):
    return api.post("/api/clients", json={
        "ref": "SEC", "prefix": prefix, "nom": "CLIENT SECURITE", "adresse": "1 rue S",
        "separer_chantiers": split,
    }).json()["id"]


def _billet(numero, chantier="Chantier A", qty=4):
    return {"date_billet": "2026-09-10", "chantier": chantier, "plaque": "S111111",
            "numero_billet": numero, "quantite": qty, "taux": 100}


def _generate(api, cid, billets):
    resp = api.post("/api/factures/generate",
                    json={"client_id": cid, "date": "2026-09-14", "billets": billets})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _only_facture(api, cid):
    [f] = api.get("/api/factures", params={"client_id": cid}).json()
    return db.get_facture(f["id"])


def _corrupt_billets_json(fid, value="{not json"):
    conn = sqlite3.connect(str(db.DB_PATH))
    conn.execute("UPDATE factures SET billets_json = ? WHERE id = ?", (value, fid))
    conn.commit()
    conn.close()


def _output_files():
    return sorted(p.name for p in gen.OUTPUT_DIR.iterdir()) if gen.OUTPUT_DIR.exists() else []


def _boom(*args, **kwargs):
    raise sqlite3.OperationalError("database is locked")


# ── Finding 1: unreadable billets are reported, never silently blank ─────


def test_get_flags_unreadable_billets_when_json_and_xlsx_both_fail(api, caplog):
    cid = _client(api)
    _generate(api, cid, [_billet("70001")])
    f = _only_facture(api, cid)
    _corrupt_billets_json(f["id"])
    (gen.OUTPUT_DIR / f["fichier"]).write_bytes(b"not an xlsx at all")

    with caplog.at_level(logging.ERROR):
        body = api.get(f"/api/factures/{f['id']}").json()

    assert body["billets"] == []
    assert body["billets_unreadable"] is True
    assert body["billets_unreadable_reason"]
    assert f"facture {f['id']}" in caplog.text
    assert f["fichier"] in caplog.text


def test_get_flags_unreadable_billets_when_json_is_corrupt_and_xlsx_missing(api):
    cid = _client(api)
    _generate(api, cid, [_billet("70002")])
    f = _only_facture(api, cid)
    _corrupt_billets_json(f["id"], '{"not": "a list"}')
    (gen.OUTPUT_DIR / f["fichier"]).unlink()

    body = api.get(f"/api/factures/{f['id']}").json()
    assert body["billets"] == [] and body["billets_unreadable"] is True


def test_get_recovers_from_xlsx_when_only_the_json_is_corrupt(api):
    cid = _client(api)
    _generate(api, cid, [_billet("70003")])
    f = _only_facture(api, cid)
    _corrupt_billets_json(f["id"])

    body = api.get(f"/api/factures/{f['id']}").json()
    assert len(body["billets"]) == 1
    assert body["billets_unreadable"] is False


def test_get_readable_invoice_is_not_flagged(api):
    cid = _client(api)
    _generate(api, cid, [_billet("70004")])
    body = api.get(f"/api/factures/{_only_facture(api, cid)['id']}").json()
    assert body["billets_unreadable"] is False
    assert body["billets_unreadable_reason"] == ""


def test_put_refuses_to_overwrite_an_invoice_with_unreadable_billets(api):
    cid = _client(api)
    _generate(api, cid, [_billet("70005")])
    f = _only_facture(api, cid)
    _corrupt_billets_json(f["id"])
    xlsx = gen.OUTPUT_DIR / f["fichier"]
    xlsx.write_bytes(b"the real invoice, unreadable by us but not by Excel")

    resp = api.put(f"/api/factures/{f['id']}", json={
        "client_id": cid, "date": "2026-09-14", "billets": [_billet("99999")]})

    assert resp.status_code == 409
    assert "billets" in resp.json()["detail"]
    assert xlsx.read_bytes() == b"the real invoice, unreadable by us but not by Excel"
    assert db.get_facture(f["id"])["billets_json"] == "{not json"


def test_put_overwrites_unreadable_billets_only_with_explicit_confirmation(api):
    cid = _client(api)
    _generate(api, cid, [_billet("70006")])
    f = _only_facture(api, cid)
    _corrupt_billets_json(f["id"])
    (gen.OUTPUT_DIR / f["fichier"]).write_bytes(b"garbage")

    resp = api.put(f"/api/factures/{f['id']}", json={
        "client_id": cid, "date": "2026-09-14", "billets": [_billet("99998")],
        "forcer_ecrasement": True})

    assert resp.status_code == 200, resp.text
    assert json.loads(db.get_facture(f["id"])["billets_json"])[0]["numero_billet"] == "99998"


# ── Finding 2: a DB failure leaves no orphan and no overwritten file ─────


def test_generate_db_failure_removes_the_written_xlsx(api, monkeypatch):
    cid = _client(api)
    monkeypatch.setattr(db, "save_facture", _boom)

    resp = api.post("/api/factures/generate",
                    json={"client_id": cid, "date": "2026-09-14", "billets": [_billet("71001")]})

    assert resp.status_code == 500
    assert "enregistr" in resp.json()["detail"]
    assert "database is locked" not in resp.json()["detail"]
    assert _output_files() == []
    assert api.get("/api/factures", params={"client_id": cid}).json() == []


def test_generate_db_failure_restores_a_pre_existing_file_of_the_same_name(api, monkeypatch):
    cid = _client(api)
    client = db.get_client(cid)
    name = gen.invoice_filename(client, "sec001", "2026-09-14")
    gen.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (gen.OUTPUT_DIR / name).write_bytes(b"someone else's invoice")
    monkeypatch.setattr(db, "save_facture", _boom)

    resp = api.post("/api/factures/generate",
                    json={"client_id": cid, "date": "2026-09-14", "billets": [_billet("71002")]})

    assert resp.status_code == 500
    assert (gen.OUTPUT_DIR / name).read_bytes() == b"someone else's invoice"


def test_split_generate_failure_reports_the_invoices_already_created(api, monkeypatch):
    cid = _client(api, split=True)
    real_save = db.save_facture
    calls = []

    def save_then_fail(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise sqlite3.OperationalError("disk I/O error")
        return real_save(*args, **kwargs)

    monkeypatch.setattr(db, "save_facture", save_then_fail)
    resp = api.post("/api/factures/generate", json={
        "client_id": cid, "date": "2026-09-14",
        "billets": [_billet("71003", "Chantier A"), _billet("71004", "Chantier B")]})

    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert "sec001" in detail and "sec002" in detail
    assert [f["numero"] for f in api.get("/api/factures", params={"client_id": cid}).json()] == ["sec001"]
    assert len(_output_files()) == 1


def test_update_relink_failure_rolls_back_the_billets_and_restores_the_file(api, monkeypatch):
    cid = _client(api)
    _generate(api, cid, [_billet("72001")])
    f = _only_facture(api, cid)
    xlsx = gen.OUTPUT_DIR / f["fichier"]
    original = xlsx.read_bytes()
    monkeypatch.setattr(payment_store, "relink_after_invoice_edit", _boom)

    resp = api.put(f"/api/factures/{f['id']}", json={
        "client_id": cid, "date": "2026-09-14", "billets": [_billet("72002"), _billet("72003")]})

    assert resp.status_code == 500
    assert "enregistr" in resp.json()["detail"]
    assert db.get_facture(f["id"])["billets_json"] == f["billets_json"]
    assert xlsx.read_bytes() == original


def test_update_db_failure_keeps_the_old_file_when_renaming(api, monkeypatch):
    cid = _client(api)
    _generate(api, cid, [_billet("72004")])
    f = _only_facture(api, cid)
    monkeypatch.setattr(db, "update_facture", _boom)

    resp = api.put(f"/api/factures/{f['id']}", json={
        "client_id": cid, "numero": "sec050", "date": "2026-09-14", "billets": [_billet("72005")]})

    assert resp.status_code == 500
    assert _output_files() == [f["fichier"]]
    assert db.get_facture(f["id"])["numero"] == f["numero"]


def test_split_update_failure_leaves_no_extra_invoice_or_file(api, monkeypatch):
    cid = _client(api, split=True)
    _generate(api, cid, [_billet("72006", "Chantier A")])
    f = _only_facture(api, cid)
    monkeypatch.setattr(payment_store, "relink_after_invoice_edit", _boom)

    resp = api.put(f"/api/factures/{f['id']}", json={
        "client_id": cid, "date": "2026-09-14",
        "billets": [_billet("72006", "Chantier A"), _billet("72007", "Chantier B")]})

    assert resp.status_code == 500
    assert len(api.get("/api/factures", params={"client_id": cid}).json()) == 1
    assert _output_files() == [f["fichier"]]


def test_update_success_still_relinks_inside_the_same_transaction(api, monkeypatch):
    cid = _client(api)
    _generate(api, cid, [_billet("72008")])
    f = _only_facture(api, cid)
    seen = []
    real = payment_store.relink_after_invoice_edit

    def spy(conn, ids, previous=None):
        seen.append(conn)
        # The new billets are visible on the relink's connection before commit.
        row = conn.execute("SELECT billets_json FROM factures WHERE id = ?", (f["id"],)).fetchone()
        assert "72009" in row[0]
        return real(conn, ids, previous)

    monkeypatch.setattr(payment_store, "relink_after_invoice_edit", spy)
    resp = api.put(f"/api/factures/{f['id']}", json={
        "client_id": cid, "date": "2026-09-14", "billets": [_billet("72009")]})

    assert resp.status_code == 200, resp.text
    assert seen and seen[0] is not None


# ── Delete: the database row first, the files only once it is gone ──────


def test_delete_db_failure_keeps_the_files_and_answers_in_french(api, monkeypatch):
    cid = _client(api)
    _generate(api, cid, [_billet("74001")])
    f = _only_facture(api, cid)
    monkeypatch.setattr(db, "delete_facture", _boom)

    resp = api.delete(f"/api/factures/{f['id']}")

    assert resp.status_code == 500
    assert "supprim" in resp.json()["detail"].lower()
    assert _output_files() == [f["fichier"]]


def test_delete_file_that_cannot_be_removed_is_logged(api, caplog):
    cid = _client(api)
    _generate(api, cid, [_billet("74002")])
    f = _only_facture(api, cid)
    xlsx = gen.OUTPUT_DIR / f["fichier"]
    xlsx.unlink()
    xlsx.mkdir()  # a directory: unlink() raises
    (xlsx / "x").write_bytes(b"")

    with caplog.at_level(logging.WARNING):
        resp = api.delete(f"/api/factures/{f['id']}")

    assert resp.status_code == 200
    assert f["fichier"] in caplog.text
    assert db.get_facture(f["id"]) is None


# ── No file generation (soffice, disk I/O) while holding BEGIN IMMEDIATE ──


def _db_write_locked() -> bool:
    probe = sqlite3.connect(str(db.DB_PATH), timeout=0)
    try:
        probe.execute("BEGIN IMMEDIATE")
        probe.rollback()
        return False
    except sqlite3.OperationalError:
        return True
    finally:
        probe.close()


def test_split_update_generates_every_file_before_the_transaction(api, monkeypatch):
    cid = _client(api, split=True)
    _generate(api, cid, [_billet("73001", "Chantier A")])
    f = _only_facture(api, cid)
    locked_during_generation = []
    real = gen.generate_invoice

    def spy(*args, **kwargs):
        locked_during_generation.append(_db_write_locked())
        return real(*args, **kwargs)

    monkeypatch.setattr(gen, "generate_invoice", spy)
    resp = api.put(f"/api/factures/{f['id']}", json={
        "client_id": cid, "date": "2026-09-14", "numero": "sec010",
        "billets": [_billet("73001", "Chantier A"), _billet("73002", "Chantier B"),
                    _billet("73003", "Chantier C")]})

    assert resp.status_code == 200, resp.text
    assert locked_during_generation == [False, False, False]
    # Extra chantiers are numbered after the (renamed) invoice, never colliding.
    assert [inv["numero"] for inv in resp.json()["invoices"]] == ["sec010", "sec011", "sec012"]
    rows = api.get("/api/factures", params={"client_id": cid}).json()
    assert sorted(r["numero"] for r in rows) == ["sec010", "sec011", "sec012"]
    assert len(_output_files()) == 3


def test_split_update_extra_generation_failure_undoes_every_file(api, monkeypatch):
    cid = _client(api, split=True)
    _generate(api, cid, [_billet("73004", "Chantier A")])
    f = _only_facture(api, cid)
    original = (gen.OUTPUT_DIR / f["fichier"]).read_bytes()
    real = gen.generate_invoice
    calls = {"n": 0}

    def fail_third(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("soffice crashed")
        return real(*args, **kwargs)

    monkeypatch.setattr(gen, "generate_invoice", fail_third)
    resp = api.put(f"/api/factures/{f['id']}", json={
        "client_id": cid, "date": "2026-09-14",
        "billets": [_billet("73004", "Chantier A"), _billet("73005", "Chantier B"),
                    _billet("73006", "Chantier C")]})

    assert resp.status_code == 500
    assert _output_files() == [f["fichier"]]
    assert (gen.OUTPUT_DIR / f["fichier"]).read_bytes() == original
    assert len(api.get("/api/factures", params={"client_id": cid}).json()) == 1

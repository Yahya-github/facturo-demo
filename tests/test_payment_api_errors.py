"""Error paths and edge cases of the /api/paiements surface and pdf_text.

Complements tests/test_payment_api.py (the contract tests): not-found ids,
link conflicts, invalid picks, file serving, and the real text-extraction path
through a synthetic PDF built by tests/helpers/pdf_writer.py.
"""

import io

import pytest
from fastapi.testclient import TestClient

from facturo.api import payments as payments_api
from facturo.core import database as db
from facturo.payments import pdf_text
from facturo.server import app
from tests.helpers.pdf_writer import make_blank_pdf, make_text_pdf

QUITTANCE_LINES = [
    "05-09-2026",
    "Emetteur Erreurs Inc.",
    "Quittance # 700-001",
    "CLIENT ERREURS / Note 2 100,00 $ 200,00 $",
    "40001 05-09-2026 k111111",
    "CLIENT ERREURS / Note 3 100,00 $ 300,00 $",
    "40002 05-09-2026 k111111",
    "TOTAL: 500,00 $",
]


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(payments_api, "PAYMENTS_DIR", tmp_path / "paiements")
    with TestClient(app) as c:
        yield c


def _facture(api, billets, prefix="err"):
    cid = api.post("/api/clients", json={
        "ref": "ERR", "prefix": prefix, "nom": f"CLIENT {prefix}", "adresse": "1 rue Test",
    }).json()["id"]
    api.post("/api/factures/generate", json={"client_id": cid, "date": "2026-09-06", "billets": billets})
    return api.get("/api/factures", params={"client_id": cid}).json()[0]["id"]


def _billet(numero, qty):
    return {"date_billet": "2026-09-05", "chantier": "C", "plaque": "K111111",
            "numero_billet": numero, "quantite": qty, "taux": 100}


def _import(api, lines=QUITTANCE_LINES, name="q.pdf", **kw):
    return api.post("/api/paiements", files={
        "file": (name, io.BytesIO(make_text_pdf(lines)), "application/pdf")}, **kw)


# ── pdf_text on real bytes ───────────────────────────────────────────────

def test_extract_text_reads_a_real_text_pdf():
    assert "Quittance # 700-001" in pdf_text.extract_text(make_text_pdf(QUITTANCE_LINES))


def test_extract_text_rejects_a_pdf_without_text():
    with pytest.raises(pdf_text.PaymentParseError, match="texte lisible"):
        pdf_text.extract_text(make_blank_pdf())


def _password_protected_pdf() -> bytes:
    """A text PDF whose trailer declares standard encryption with keys that no
    empty password satisfies — pdfium refuses it with a password error."""
    raw = make_text_pdf(["secret"])
    encrypt = (b"/Encrypt << /Filter /Standard /V 1 /R 2 /O <" + b"11" * 32 + b"> /U <"
               + b"22" * 32 + b"> /P -4 >> /ID [<" + b"33" * 16 + b"> <" + b"33" * 16 + b">] ")
    return raw.replace(b"<< /Size", b"<< " + encrypt + b"/Size")


def test_extract_text_explains_a_password_protected_pdf():
    with pytest.raises(pdf_text.PaymentParseError, match="mot de passe"):
        pdf_text.extract_text(_password_protected_pdf())


def test_password_protected_upload_is_400_with_the_explanation(api):
    resp = api.post("/api/paiements", files={
        "file": ("p.pdf", io.BytesIO(_password_protected_pdf()), "application/pdf")})
    assert resp.status_code == 400
    assert "mot de passe" in resp.json()["detail"]


def test_extract_text_rejects_garbage_bytes():
    with pytest.raises(pdf_text.PaymentParseError, match="PDF lisible"):
        pdf_text.extract_text(b"%PDF-1.4 but not really")


# ── Upload validation ─────────────────────────────────────────────────────

def test_empty_upload_is_rejected(api):
    resp = api.post("/api/paiements", files={"file": ("e.pdf", io.BytesIO(b""), "application/pdf")})
    assert resp.status_code == 400


def test_failed_db_insert_removes_the_stored_file(api, tmp_path, monkeypatch):
    from facturo.payments import store

    def _boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(store, "create_paiement", _boom)
    with pytest.raises(RuntimeError):
        _import(api)
    folder = tmp_path / "paiements"
    assert not folder.exists() or list(folder.iterdir()) == []


def test_uploaded_file_is_served_back_as_pdf(api):
    paiement = _import(api).json()
    resp = api.get(f"/api/paiements/file/{paiement['fichier']}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-")


def test_well_formed_but_missing_stored_name_is_404(api):
    assert api.get(f"/api/paiements/file/{'a' * 32}.pdf").status_code == 404


# ── Not-found ids ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("method, path, body", [
    ("GET", "/api/paiements/999", None),
    ("PUT", "/api/paiements/999", {"notes": "x"}),
    ("DELETE", "/api/paiements/999", None),
    ("POST", "/api/paiements/999/lignes", {"numero_billet": "1"}),
    ("PUT", "/api/paiements/lignes/999", {"facture_id": None}),
    ("DELETE", "/api/paiements/lignes/999", None),
    ("GET", "/api/factures/999/paiements", None),
])
def test_unknown_ids_are_404(api, method, path, body):
    assert api.request(method, path, json=body).status_code == 404


def test_blank_manual_numero_is_rejected(api):
    paiement = _import(api).json()
    resp = api.post(f"/api/paiements/{paiement['id']}/lignes", json={"numero_billet": "   "})
    assert resp.status_code == 400


# ── Linking rules ─────────────────────────────────────────────────────────

def test_link_requires_a_billet_index_and_an_existing_billet(api):
    fid = _facture(api, [_billet("40001", 2)])
    paiement = _import(api).json()
    unmatched = next(ligne for ligne in paiement["lignes"] if ligne["statut"] != "lie")
    url = f"/api/paiements/lignes/{unmatched['id']}"
    assert api.put(url, json={"facture_id": fid}).status_code == 400
    assert api.put(url, json={"facture_id": fid, "billet_index": 5}).status_code == 400


def test_linking_a_billet_held_by_another_ligne_is_409(api):
    fid = _facture(api, [_billet("40001", 2)])
    paiement = _import(api).json()
    linked, other = paiement["lignes"]
    assert linked["statut"] == "lie"
    resp = api.put(f"/api/paiements/lignes/{other['id']}", json={"facture_id": fid, "billet_index": 0})
    assert resp.status_code == 409
    assert str(paiement["id"]) in resp.json()["detail"]


def test_unlinked_match_is_offered_as_a_candidate_not_relinked(api):
    fid = _facture(api, [_billet("40001", 2)])
    paiement = _import(api).json()
    linked = paiement["lignes"][0]
    after = api.put(f"/api/paiements/lignes/{linked['id']}", json={"facture_id": None}).json()
    assert after["statut"] == "non_lie"
    assert after["candidats"][0]["facture_id"] == fid
    assert after["candidats"][0]["raison"] == "numero"


def test_list_summary_flags_unmatched_payments_a_verifier(api):
    _facture(api, [_billet("40001", 2)])
    _import(api)
    [summary] = api.get("/api/paiements").json()
    assert summary["statut_global"] == "a_verifier"
    assert (summary["nb_lignes"], summary["nb_lignes_liees"]) == (2, 1)


def test_put_clears_a_text_field_to_empty_string(api):
    paiement = _import(api).json()
    resp = api.put(f"/api/paiements/{paiement['id']}", json={"notes": None, "date": "2026-09-07"})
    assert resp.status_code == 200
    assert resp.json()["notes"] == ""
    assert resp.json()["date"] == "2026-09-07"


def test_put_rejects_a_malformed_date(api):
    paiement = _import(api).json()
    assert api.put(f"/api/paiements/{paiement['id']}", json={"date": "07/09/2026"}).status_code == 422


def test_numero_that_tidies_to_nothing_is_refused_in_french(api):
    paiement = _import(api).json()
    resp = api.post(f"/api/paiements/{paiement['id']}/lignes", json={"numero_billet": "#26-112"},
                    headers={"X-Lang": "fr"})
    assert resp.status_code == 422
    assert "billet" in resp.json()["detail"].lower()
    assert len(api.get(f"/api/paiements/{paiement['id']}").json()["lignes"]) == 2


def test_failed_pdf_write_leaves_no_partial_file(api, tmp_path, monkeypatch):
    import pathlib

    real_write = pathlib.Path.write_bytes

    def half_write(self, data):
        real_write(self, data[: len(data) // 2])
        raise OSError("disk full")

    monkeypatch.setattr(pathlib.Path, "write_bytes", half_write)
    resp = _import(api, headers={"X-Lang": "fr"})

    assert resp.status_code == 500
    assert "enregistr" in resp.json()["detail"].lower()
    folder = tmp_path / "paiements"
    assert not folder.exists() or list(folder.iterdir()) == []


def test_reset_also_removes_payment_pdfs(api, tmp_path):
    _import(api)
    folder = tmp_path / "paiements"
    assert list(folder.iterdir())

    assert api.post("/api/reset").json() == {"ok": True}

    assert list(folder.iterdir()) == []
    assert api.get("/api/paiements").json() == []


def test_deleting_the_invoice_clears_stale_link_details(api):
    fid = _facture(api, [_billet("40001", 2)])
    paiement = _import(api).json()
    api.delete(f"/api/factures/{fid}")
    with db.transaction() as conn:
        rows = conn.execute("SELECT facture_id, billet_index, methode FROM paiement_lignes "
                            "WHERE paiement_id = ?", (paiement["id"],)).fetchall()
    assert rows and all(tuple(r) == (None, None, "") for r in rows)


def test_deleting_the_invoice_unlinks_its_lignes(api):
    fid = _facture(api, [_billet("40001", 2)])
    paiement = _import(api).json()
    api.delete(f"/api/factures/{fid}")
    after = api.get(f"/api/paiements/{paiement['id']}").json()
    assert all(ligne["statut"] == "non_lie" for ligne in after["lignes"])

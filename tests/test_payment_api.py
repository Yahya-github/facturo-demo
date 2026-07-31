"""Integration tests for the /api/paiements surface (Team C — Paiements tab).

Every test gets its own throwaway sqlite file and paiements folder (same
isolation pattern as tests/test_known_values.py), so payments never touch the
developer's real data. PDF text extraction is monkeypatched at
`facturo.payments.pdf_text.extract_text` for almost every test — the upload
still has to look like a real PDF (magic bytes + size), but what it "contains"
is whatever canned text the test hands back, which keeps these tests fast and
independent of any real PDF-rendering quirks.

See changes/team-c.md for the full endpoint/JSON contract this locks down.
"""

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from facturo.api import payments as payments_api
from facturo.core import database as db
from facturo.payments import pdf_text
from facturo.server import app

FIXTURES = Path(__file__).parent / "fixtures" / "payments" / "text"
QUITTANCE_TEXT = (FIXTURES / "quittance.txt").read_text(encoding="utf-8")
BILL_INLINE_TEXT = (FIXTURES / "bill_labels_inline.txt").read_text(encoding="utf-8")
BILL_SCRAMBLED_TEXT = (FIXTURES / "bill_labels_scrambled.txt").read_text(encoding="utf-8")
REAL_PDF_DIR = Path(__file__).parent / "fixtures" / "payments" / "pdf"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(payments_api, "PAYMENTS_DIR", tmp_path / "paiements")
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fake_pdf_bytes():
    """Bytes that pass the "is this a PDF" gate; content is irrelevant once
    pdf_text.extract_text is monkeypatched."""
    return b"%PDF-1.4\n%fake for upload validation only\n"


def _use_text(monkeypatch, text_or_list):
    """Monkeypatch pdf_text.extract_text to return canned text.

    Accepts either one string (every upload gets it) or a list (one upload
    gets each entry in order) — for doublon/multi-upload tests.
    """
    if isinstance(text_or_list, str):
        monkeypatch.setattr(pdf_text, "extract_text", lambda raw: text_or_list)
    else:
        queue = list(text_or_list)
        monkeypatch.setattr(pdf_text, "extract_text", lambda raw: queue.pop(0))


def _make_client(api, nom="CLIENT PAIEMENTS TEST", prefix="pmt"):
    resp = api.post("/api/clients", json={
        "ref": "PMT", "prefix": prefix, "nom": nom, "adresse": "1 rue Test",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _make_facture(api, client_id, billets, numero=None):
    resp = api.post("/api/factures/generate", json={
        "client_id": client_id, "numero": numero, "date": "2026-09-20", "billets": billets,
    })
    assert resp.status_code == 200, resp.text
    invoices = resp.json()["invoices"]
    # Look the freshly created invoice up by its generated number to get its id.
    listing = api.get("/api/factures", params={"client_id": client_id}).json()
    match = next(f for f in listing if f["numero"] == invoices[0]["numero"])
    return match["id"]


def _billet(numero, date, plaque, quantite, taux):
    return {
        "date_billet": date, "chantier": "Chantier Test", "plaque": plaque,
        "numero_billet": numero, "quantite": quantite, "taux": taux,
    }


QUITTANCE_BILLETS = [
    _billet("50210", "2026-09-12", "G123456", 4, 250),
    _billet("50211", "2026-09-12", "G123456", 5, 200),
    _billet("50212", "2026-09-13", "LE99999", 8.5, 100),
    _billet("50213", "2026-09-14", "LE99999", 10, 115),
]


def _upload(api, fake_pdf_bytes, filename="paiement.pdf"):
    return api.post(
        "/api/paiements",
        files={"file": (filename, io.BytesIO(fake_pdf_bytes), "application/pdf")},
    )


# ── Upload -> parse -> match -> auto-paid ─────────────────────────────────

class TestUploadAndMatch:
    def test_upload_creates_paiement_with_four_matched_lignes(
        self, client, fake_pdf_bytes, monkeypatch,
    ):
        _use_text(monkeypatch, QUITTANCE_TEXT)
        cid = _make_client(client)
        _make_facture(client, cid, QUITTANCE_BILLETS)

        resp = _upload(client, fake_pdf_bytes)
        assert resp.status_code in (200, 201), resp.text
        data = resp.json()

        assert data["reference"] == "220-451"
        assert data["total"] == pytest.approx(4369.05, abs=0.01)
        assert len(data["lignes"]) == 4
        assert all(ligne["statut"] == "lie" for ligne in data["lignes"])
        assert {ligne["numero_billet"] for ligne in data["lignes"]} == \
            {"50210", "50211", "50212", "50213"}

    def test_full_coverage_marks_the_invoice_auto_paid(
        self, client, fake_pdf_bytes, monkeypatch,
    ):
        _use_text(monkeypatch, QUITTANCE_TEXT)
        cid = _make_client(client)
        fid = _make_facture(client, cid, QUITTANCE_BILLETS)

        _upload(client, fake_pdf_bytes)

        facture = db.get_facture(fid)
        assert facture["paye"] == 1
        assert facture["paye_auto"] == 1

    def test_partial_coverage_does_not_mark_the_invoice_paid(
        self, client, fake_pdf_bytes, monkeypatch,
    ):
        _use_text(monkeypatch, QUITTANCE_TEXT)
        cid = _make_client(client)
        billets = QUITTANCE_BILLETS + [_billet("99999", "2026-01-01", "Z000000", 1, 50)]
        fid = _make_facture(client, cid, billets)

        resp = _upload(client, fake_pdf_bytes)
        assert len(resp.json()["lignes"]) == 4  # only what the PDF actually lists

        facture = db.get_facture(fid)
        assert facture["paye"] == 0


# ── Delete: revert only what was auto-set ─────────────────────────────────

class TestDeleteReverts:
    def test_delete_reverts_auto_paid_status_and_removes_the_file(
        self, client, fake_pdf_bytes, monkeypatch, tmp_path,
    ):
        _use_text(monkeypatch, QUITTANCE_TEXT)
        cid = _make_client(client)
        fid = _make_facture(client, cid, QUITTANCE_BILLETS)
        paiement = _upload(client, fake_pdf_bytes).json()
        stored_file = tmp_path / "paiements" / paiement["fichier"]
        assert stored_file.exists()

        resp = client.delete(f"/api/paiements/{paiement['id']}")
        assert resp.status_code == 200, resp.text

        assert db.get_facture(fid)["paye"] == 0
        assert not stored_file.exists()

    def test_manual_paye_true_survives_deleting_the_payment(
        self, client, fake_pdf_bytes, monkeypatch,
    ):
        """A user-set paye is never touched by payment bookkeeping — set
        manually here, then a matching payment is uploaded and deleted."""
        _use_text(monkeypatch, QUITTANCE_TEXT)
        cid = _make_client(client)
        fid = _make_facture(client, cid, QUITTANCE_BILLETS)
        client.patch(f"/api/factures/{fid}/paye", json={"paye": True})
        assert db.get_facture(fid)["paye_auto"] == 0

        paiement = _upload(client, fake_pdf_bytes).json()
        client.delete(f"/api/paiements/{paiement['id']}")

        assert db.get_facture(fid)["paye"] == 1  # still the user's decision


# ── Manual toggle is never overridden by the payments engine ─────────────

class TestManualToggleRespected:
    def test_proof_covering_every_billet_overrides_unpaid(
        self, client, fake_pdf_bytes, monkeypatch,
    ):
        """Lead decision: a proof of payment covering every billet is stronger
        evidence than "non payée" (which the schema cannot tell apart from the
        untouched default), so full coverage marks the invoice auto-paid."""
        _use_text(monkeypatch, QUITTANCE_TEXT)
        cid = _make_client(client)
        fid = _make_facture(client, cid, QUITTANCE_BILLETS)
        client.patch(f"/api/factures/{fid}/paye", json={"paye": False})

        _upload(client, fake_pdf_bytes)  # covers every billet

        facture = db.get_facture(fid)
        assert facture["paye"] == 1
        assert facture["paye_auto"] == 1

    def test_manual_paid_keeps_paye_auto_zero_after_full_coverage(
        self, client, fake_pdf_bytes, monkeypatch,
    ):
        _use_text(monkeypatch, QUITTANCE_TEXT)
        cid = _make_client(client)
        fid = _make_facture(client, cid, QUITTANCE_BILLETS)
        client.patch(f"/api/factures/{fid}/paye", json={"paye": True})

        _upload(client, fake_pdf_bytes)

        facture = db.get_facture(fid)
        assert facture["paye"] == 1
        assert facture["paye_auto"] == 0  # still manually owned, not reclaimed


# ── Doublon: a billet already claimed is never silently re-linked ────────

class TestDoublon:
    SECOND_TEXT = (
        "05-05-2026\n"
        "Emetteur Doublon Inc.\n"
        "Quittance # 500-500\n"
        "CLIENT DOUBLON INC. / Note 4 250,00 $ 1 000,00 $\n"
        "50210 12-09-2026 g123456\n"
        "TOTAL: 1 000,00 $\n"
    )

    def test_second_payment_reusing_a_linked_billet_is_flagged_doublon(
        self, client, fake_pdf_bytes, monkeypatch,
    ):
        _use_text(monkeypatch, [QUITTANCE_TEXT, self.SECOND_TEXT])
        cid = _make_client(client)
        fid = _make_facture(client, cid, QUITTANCE_BILLETS)

        first = _upload(client, fake_pdf_bytes, "p1.pdf").json()
        second = _upload(client, fake_pdf_bytes, "p2.pdf").json()

        [ligne] = [entry for entry in second["lignes"] if entry["numero_billet"] == "50210"]
        assert ligne["statut"] == "doublon"
        assert ligne["doublon_paiement_id"] == first["id"]

        # the duplicate never actually holds the link
        assert db.get_facture(fid)["paye"] == 1  # still fully covered by the first payment
        client.delete(f"/api/paiements/{second['id']}")
        assert db.get_facture(fid)["paye"] == 1  # deleting the duplicate changes nothing


# ── Manual link / unlink of a single ligne ────────────────────────────────

class TestManualLinkUnlink:
    UNMATCHED_TEXT = (
        "05-05-2026\n"
        "Emetteur Ligne Test Inc.\n"
        "Quittance # 500-500\n"
        "CLIENT X / Note 1 50,00 $ 50,00 $\n"
        "00000 05-05-2026 z999999\n"
        "TOTAL: 50,00 $\n"
    )

    def test_link_then_unlink_recomputes_the_invoice_paid_state(
        self, client, fake_pdf_bytes, monkeypatch,
    ):
        _use_text(monkeypatch, self.UNMATCHED_TEXT)
        cid = _make_client(client, prefix="lnk")
        fid = _make_facture(client, cid, [_billet("77777", "2026-05-05", "M111111", 2, 80)])

        paiement = _upload(client, fake_pdf_bytes).json()
        [ligne] = paiement["lignes"]
        assert ligne["statut"] == "non_lie"
        assert db.get_facture(fid)["paye"] == 0

        link_resp = client.put(
            f"/api/paiements/lignes/{ligne['id']}",
            json={"facture_id": fid, "billet_index": 0},
        )
        assert link_resp.status_code == 200, link_resp.text
        assert link_resp.json()["statut"] == "lie"
        assert link_resp.json()["methode"] == "manuel"
        assert db.get_facture(fid)["paye"] == 1
        assert db.get_facture(fid)["paye_auto"] == 1

        unlink_resp = client.put(
            f"/api/paiements/lignes/{ligne['id']}", json={"facture_id": None},
        )
        assert unlink_resp.status_code == 200, unlink_resp.text
        assert unlink_resp.json()["statut"] == "non_lie"
        assert db.get_facture(fid)["paye"] == 0

    def test_add_manual_ligne_by_numero_auto_matches_and_completes_coverage(
        self, client, fake_pdf_bytes, monkeypatch,
    ):
        _use_text(monkeypatch, QUITTANCE_TEXT)
        cid = _make_client(client, prefix="add")
        billets = QUITTANCE_BILLETS + [_billet("99999", "2026-01-01", "Z000000", 1, 50)]
        fid = _make_facture(client, cid, billets)

        paiement = _upload(client, fake_pdf_bytes).json()
        assert db.get_facture(fid)["paye"] == 0  # 4/5 so far

        add_resp = client.post(
            f"/api/paiements/{paiement['id']}/lignes", json={"numero_billet": "99999"},
        )
        assert add_resp.status_code in (200, 201), add_resp.text
        assert add_resp.json()["statut"] == "lie"
        assert db.get_facture(fid)["paye"] == 1

    def test_delete_ligne_removes_it_and_recomputes_paid_state(
        self, client, fake_pdf_bytes, monkeypatch,
    ):
        _use_text(monkeypatch, QUITTANCE_TEXT)
        cid = _make_client(client, prefix="del")
        fid = _make_facture(client, cid, QUITTANCE_BILLETS)
        paiement = _upload(client, fake_pdf_bytes).json()
        assert db.get_facture(fid)["paye"] == 1

        ligne_id = paiement["lignes"][0]["id"]
        resp = client.delete(f"/api/paiements/lignes/{ligne_id}")
        assert resp.status_code == 200, resp.text

        assert db.get_facture(fid)["paye"] == 0


# ── Reverse endpoint + store contract shapes ──────────────────────────────

class TestReverseLookupAndStoreContract:
    def test_reverse_endpoint_reports_paid_billets_for_the_invoice(
        self, client, fake_pdf_bytes, monkeypatch,
    ):
        _use_text(monkeypatch, QUITTANCE_TEXT)
        cid = _make_client(client, prefix="rev")
        fid = _make_facture(client, cid, QUITTANCE_BILLETS)
        paiement = _upload(client, fake_pdf_bytes).json()

        resp = client.get(f"/api/factures/{fid}/paiements")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert len(data["billets"]) == 4
        assert all(b["paye"] for b in data["billets"])
        assert all(b["paiement_id"] == paiement["id"] for b in data["billets"])
        assert data["paiements"] == [{"paiement_id": paiement["id"], "reference": "220-451"}]

    def test_reverse_endpoint_lists_no_payment_for_an_unpaid_invoice(self, client):
        cid = _make_client(client, prefix="unp")
        fid = _make_facture(client, cid, QUITTANCE_BILLETS)

        data = client.get(f"/api/factures/{fid}/paiements").json()

        assert data["paiements"] == []
        assert not any(b["paye"] for b in data["billets"])

    def test_store_paid_billets_shape(self, client, fake_pdf_bytes, monkeypatch):
        from facturo.payments import store

        _use_text(monkeypatch, QUITTANCE_TEXT)
        cid = _make_client(client, prefix="sto")
        fid = _make_facture(client, cid, QUITTANCE_BILLETS)
        paiement = _upload(client, fake_pdf_bytes).json()

        billets = store.paid_billets()
        assert billets[(fid, 0)]["paiement_id"] == paiement["id"]
        assert billets[(fid, 0)]["reference"] == "220-451"
        assert set(billets[(fid, 0)]) == {"paiement_id", "reference"}
        assert len(billets) == 4

    def test_store_has_no_whole_invoice_links(self):
        from facturo.payments import store

        assert not hasattr(store, "paid_factures")


# ── Validation ─────────────────────────────────────────────────────────

class TestValidation:
    def test_rejects_non_pdf_bytes(self, client):
        resp = client.post(
            "/api/paiements",
            files={"file": ("not-a-pdf.pdf", io.BytesIO(b"hello world, not a pdf"), "application/pdf")},
        )
        assert resp.status_code == 400

    def test_rejects_oversized_file(self, client):
        oversized = b"%PDF-1.4\n" + b"0" * (25 * 1024 * 1024 + 10)
        resp = client.post(
            "/api/paiements",
            files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
        )
        assert resp.status_code == 400

    def test_rejects_pdf_with_no_text_layer(self, client, fake_pdf_bytes, monkeypatch):
        def _raise(raw):
            raise pdf_text.PaymentParseError("Ce PDF ne contient pas de texte lisible.")

        monkeypatch.setattr(pdf_text, "extract_text", _raise)
        resp = _upload(client, fake_pdf_bytes)
        assert resp.status_code == 400
        assert "texte lisible" in resp.json()["detail"]

    def test_file_serving_rejects_path_traversal(self, client):
        resp = client.get("/api/paiements/file/..%2f..%2f..%2fetc%2fpasswd")
        assert resp.status_code == 404

    def test_file_serving_missing_file_is_404(self, client):
        resp = client.get("/api/paiements/file/does-not-exist.pdf")
        assert resp.status_code == 404


# ── List, filters and header edits ───────────────────────────────────────

class TestListAndEdit:
    def test_list_returns_one_summary_per_payment(self, client, fake_pdf_bytes, monkeypatch):
        _use_text(monkeypatch, QUITTANCE_TEXT)
        cid = _make_client(client, prefix="lst")
        _make_facture(client, cid, QUITTANCE_BILLETS)
        paiement = _upload(client, fake_pdf_bytes).json()

        [summary] = client.get("/api/paiements").json()
        assert summary["id"] == paiement["id"]
        assert summary["reference"] == "220-451"
        assert summary["statut_global"] == "complet"
        assert summary["nb_lignes"] == 4
        assert summary["nb_lignes_liees"] == 4
        assert "categorie" not in summary

    def test_put_updates_header_fields(self, client, fake_pdf_bytes, monkeypatch):
        _use_text(monkeypatch, QUITTANCE_TEXT)
        cid = _make_client(client, prefix="edt")
        _make_facture(client, cid, QUITTANCE_BILLETS)
        paiement = _upload(client, fake_pdf_bytes).json()

        resp = client.put(f"/api/paiements/{paiement['id']}", json={
            "emetteur": "Nom Corrigé Inc.", "notes": "Vérifié manuellement",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["emetteur"] == "Nom Corrigé Inc."
        assert resp.json()["notes"] == "Vérifié manuellement"



# ── Bills addressed to the company are refused (user decision: proofs of payment only) ─

class TestBillsRefused:
    @pytest.mark.parametrize("text", [BILL_INLINE_TEXT, BILL_SCRAMBLED_TEXT])
    def test_bill_to_company_is_rejected_with_422_and_nothing_is_stored(
        self, client, monkeypatch, tmp_path, text,
    ):
        _use_text(monkeypatch, text)
        resp = client.post(
            "/api/paiements",
            files={"file": ("bill.pdf", io.BytesIO(b"%PDF-1.4\nfake\n"), "application/pdf")},
        )
        assert resp.status_code == 422
        assert "pas une preuve de paiement" in resp.json()["detail"]
        assert client.get("/api/paiements").json() == []
        folder = tmp_path / "paiements"
        assert not folder.exists() or list(folder.iterdir()) == []


# ── Real samples through the real pipeline (gitignored; skipped when absent) ──

class TestRealSamplesThroughTheApi:
    def _post_real(self, api, path):
        return api.post(
            "/api/paiements",
            files={"file": (path.name, io.BytesIO(path.read_bytes()), "application/pdf")},
        )

    def test_real_bills_are_rejected(self, client):
        bills = sorted(REAL_PDF_DIR.glob("*.pdf")) if REAL_PDF_DIR.exists() else []
        if not bills:
            pytest.skip("real samples not present (gitignored, dev-machine only)")
        for path in bills:
            resp = self._post_real(client, path)
            assert resp.status_code == 422, path.name
        assert client.get("/api/paiements").json() == []

    def test_real_quittance_imports_with_every_billet_row(self, client):
        path = REAL_PDF_DIR / "With Billet.PDF"
        if not path.exists():
            pytest.skip("real sample not present (gitignored, dev-machine only)")
        resp = self._post_real(client, path)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["lignes"]) == 10
        assert data["escompte"] is not None and data["escompte"] > 0
        assert all(ligne["statut"] == "non_lie" for ligne in data["lignes"])  # empty DB

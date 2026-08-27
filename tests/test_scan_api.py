"""/api/scans: bounded uploads, no orphan files, logged deletion failures."""

import io
import logging

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from facturo.api import scans as scans_api
from facturo.core import database as db
from facturo.server import app


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(scans_api, "SCANS_DIR", tmp_path / "scans")
    with TestClient(app) as c:
        yield c


def _client(api):
    return api.post("/api/clients", json={
        "ref": "SC", "prefix": "sc", "nom": "CLIENT SCAN", "adresse": "1 rue S",
    }).json()["id"]


def _upload(api, cid, data=b"%PDF-1.4 scan", name="s.pdf"):
    return api.post("/api/scans", data={"client_id": str(cid)},
                    files={"file": (name, io.BytesIO(data), "application/pdf")})


def test_upload_read_is_capped_before_reading_the_whole_file(api, monkeypatch):
    cid = _client(api)
    sizes = []
    real_read = UploadFile.read

    async def spy(self, size=-1):
        sizes.append(size)
        return await real_read(self, size)

    monkeypatch.setattr(UploadFile, "read", spy)
    resp = _upload(api, cid, data=b"x" * (scans_api.MAX_SCAN_BYTES + 10))

    assert resp.status_code == 400
    assert sizes == [scans_api.MAX_SCAN_BYTES + 1]


def test_db_failure_after_the_write_leaves_no_orphan_scan(api, tmp_path, monkeypatch):
    cid = _client(api)

    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "add_scan", boom)
    resp = _upload(api, cid)

    assert resp.status_code == 500
    folder = tmp_path / "scans"
    assert not folder.exists() or list(folder.iterdir()) == []


def test_scan_file_that_cannot_be_deleted_is_logged(api, tmp_path, monkeypatch, caplog):
    cid = _client(api)
    scan = _upload(api, cid).json()
    stuck = tmp_path / "scans" / scan["fichier"]
    stuck.unlink()
    stuck.mkdir()  # a directory: unlink() raises
    (stuck / "x").write_bytes(b"")

    with caplog.at_level(logging.WARNING):
        resp = api.delete(f"/api/scans/{scan['id']}")

    assert resp.status_code == 200
    assert scan["fichier"] in caplog.text
    assert db.get_scan(scan["id"]) is None

"""RED tests for the /api/version and /api/updates/* HTTP endpoints.

`facturo.api.updates` currently exports an empty `APIRouter()` (already
mounted in `facturo/server.py`), so every request below 404s until the
deployment engineer adds the routes described in `changes/team-d.md`.

Uses FastAPI's TestClient (httpx-based, already a dev dependency) — no real
network, no subprocess. Every test gets its own throwaway sqlite file and
update_config.json via monkeypatch, mirroring the isolation pattern already
used in tests/test_known_values.py.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from facturo import version
from facturo.core import database as db
from facturo.core import schema
from facturo.server import app
from facturo.services import updater


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "api-test.db")
    monkeypatch.setattr(updater, "CONFIG_PATH", tmp_path / "update_config.json")
    updater.reset_cache()
    with TestClient(app) as c:
        yield c
    updater.reset_cache()


# ── GET /api/version ──────────────────────────────────────


def test_get_version_reports_current_version_and_schema(client):
    r = client.get("/api/version")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == version.__version__
    assert body["schema_version"] == schema.SCHEMA_VERSION
    assert body["frozen"] is False
    assert body["db_newer_than_app"] is False


def test_get_version_flags_db_newer_than_app(client):
    conn = db.get_conn()
    conn.execute(f"PRAGMA user_version = {schema.SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()

    r = client.get("/api/version")
    assert r.status_code == 200
    assert r.json()["db_newer_than_app"] is True


# ── GET /api/updates/status ───────────────────────────────


def test_updates_status_reports_unconfigured_by_default(client):
    r = client.get("/api/updates/status")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["current"] == version.__version__
    assert body["include_prereleases"] is False


def test_updates_status_never_includes_the_token(client):
    updater.save_config({"token": "ghp_should_never_leak_anywhere"})
    r = client.get("/api/updates/status")
    assert r.status_code == 200
    assert "ghp_should_never_leak_anywhere" not in r.text
    assert "token" not in json.dumps(r.json())
    assert r.json()["configured"] is True


# ── POST /api/updates/config ──────────────────────────────


def test_updates_config_rejects_invalid_token_without_persisting(client, monkeypatch):
    def fake_check(**kwargs):
        raise updater.UpdateError("Jeton GitHub refusé ou expiré.")

    monkeypatch.setattr(updater, "check", fake_check)
    r = client.post("/api/updates/config", json={"token": "bad-token"})
    assert r.status_code == 400
    assert "refus" in r.json()["detail"]
    assert "bad-token" not in r.text
    assert updater.load_config().get("token") != "bad-token"


def test_updates_config_accepts_valid_token_and_never_echoes_it(client, monkeypatch):
    monkeypatch.setattr(updater, "check", lambda **k: {
        "current": "2.0.0", "latest": "2.0.0", "available": False,
        "notes": "", "published_at": "", "asset": None,
    })
    r = client.post("/api/updates/config", json={"token": "good-token", "include_prereleases": True})
    assert r.status_code == 200
    assert "good-token" not in r.text
    assert updater.load_config().get("token") == "good-token"
    assert updater.load_config().get("include_prereleases") is True


# ── GET /api/updates/check ────────────────────────────────


def test_updates_check_returns_the_check_result(client, monkeypatch):
    fake_result = {
        "current": "2.0.0", "latest": "2.0.1", "available": True,
        "notes": "x", "published_at": "", "asset": None,
    }
    monkeypatch.setattr(updater, "check", lambda **k: fake_result)
    r = client.get("/api/updates/check")
    assert r.status_code == 200
    assert r.json() == fake_result


def test_updates_check_maps_update_error_to_400(client, monkeypatch):
    def raise_error(**kwargs):
        raise updater.UpdateError("Aucun jeton configuré.")

    monkeypatch.setattr(updater, "check", raise_error)
    r = client.get("/api/updates/check")
    assert r.status_code == 400
    assert "jeton" in r.json()["detail"].lower()


# ── POST /api/updates/install ─────────────────────────────


def test_updates_install_maps_update_error_to_400(client, monkeypatch):
    def raise_error(**kwargs):
        raise updater.UpdateError("Mise à jour disponible seulement en mode installé (développement).")

    monkeypatch.setattr(updater, "install", raise_error)
    r = client.post("/api/updates/install", json={"port": 8000})
    assert r.status_code == 400
    assert "développement" in r.json()["detail"]


def test_updates_install_forwards_the_current_port(client, monkeypatch):
    calls = []

    def fake_install(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "version": "2.0.1"}

    monkeypatch.setattr(updater, "install", fake_install)
    r = client.post("/api/updates/install", json={"port": 8123})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "version": "2.0.1"}
    assert calls and calls[0].get("port") == 8123


# ── schema guard surfaced through the API layer ───────────


def test_version_endpoint_flags_guard_before_any_sync_action(client):
    """The banner/guard must be visible through /api/version alone, with no
    dependency on sync being configured at all — a fresh install with a
    pulled newer db must still show the warning."""
    conn = db.get_conn()
    conn.execute(f"PRAGMA user_version = {schema.SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()

    r = client.get("/api/version")
    assert r.json()["db_newer_than_app"] is True

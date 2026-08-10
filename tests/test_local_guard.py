"""The local API only answers the app's own page.

Any web page open in the user's browser can send requests to 127.0.0.1. These
tests pin the two defences: the Host header must be local (blocks DNS
rebinding) and state-changing requests from another origin are refused (blocks
cross-site request forgery, including fetch() with no Content-Type).
"""

import pytest
from fastapi.testclient import TestClient

from facturo.server import app


@pytest.fixture
def client():
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c


def test_same_origin_write_is_allowed(client):
    resp = client.post("/api/known-values", json={"kind": "plaque", "valeur": "ZZ 111111"},
                       headers={"Origin": "http://127.0.0.1:8000", "Sec-Fetch-Site": "same-origin"})
    assert resp.status_code == 200


def test_write_without_browser_headers_is_allowed(client):
    """Local tools and tests send neither Origin nor Sec-Fetch-Site."""
    resp = client.post("/api/known-values", json={"kind": "plaque", "valeur": "ZZ 222222"})
    assert resp.status_code == 200


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://127.0.0.1:9999",
                                    "http://localhost.evil.example:8000"])
def test_cross_origin_write_is_refused(client, origin):
    resp = client.post("/api/reset", headers={"Origin": origin})
    assert resp.status_code == 403


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_cross_site_fetch_metadata_is_refused(client, site):
    resp = client.delete("/api/logo", headers={"Sec-Fetch-Site": site})
    assert resp.status_code == 403


def test_foreign_host_header_is_refused_even_for_reads(client):
    resp = client.get("/api/clients", headers={"Host": "attacker.example:8000"})
    assert resp.status_code == 403


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:8123", "localhost"])
def test_local_host_headers_are_accepted(client, host):
    assert client.get("/api/clients", headers={"Host": host}).status_code == 200


def test_cross_origin_read_is_not_blocked_by_origin_rule(client):
    """GETs change nothing; the browser's same-origin policy already hides the response."""
    resp = client.get("/api/clients", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 200


def test_shipped_host_allow_list_is_loopback_only():
    import importlib

    import facturo.local_guard as guard

    assert importlib.reload(guard).LOCAL_HOSTS == frozenset({"127.0.0.1", "localhost"})

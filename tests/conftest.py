"""Shared test setup: every test run gets a throwaway data directory.

FACTURO_DATA_DIR must be set before any facturo module is imported, because the
module-level paths (database, output, scans) are resolved at import time.
"""

import os
import tempfile

os.environ.setdefault("FACTURO_DATA_DIR", tempfile.mkdtemp(prefix="facturo-test-"))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_github(monkeypatch):
    """No test may ever reach GitHub (or any real host), whatever code path it takes.

    updater.check() reads GITHUB_API_BASE at call time, so pointing it at a
    closed loopback port turns any unmocked call (e.g. set_config()'s token
    validation) into an instant connection error. Every updater request and
    redirect is additionally limited to loopback; URLs the production policy
    refuses anyway still reach that policy, so its refusals stay tested.
    """
    from urllib.parse import urlsplit

    from facturo.services import updater

    def is_loopback(url):
        return (urlsplit(url).hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}

    monkeypatch.setattr(updater, "GITHUB_API_BASE", "http://127.0.0.1:9")

    real_open = updater._open

    def guarded_open(url, **kwargs):
        allowed = updater._url_allowed(url, carries_token=bool(kwargs.get("token")))
        if allowed and not is_loopback(url):
            raise AssertionError(f"test tried to reach a real host: {url}")
        return real_open(url, **kwargs)

    monkeypatch.setattr(updater, "_open", guarded_open)

    real_redirect = updater._SafeRedirectHandler.redirect_request

    def guarded_redirect(self, req, fp, code, msg, headers, newurl):
        if updater._url_allowed(newurl, carries_token=False) and not is_loopback(newurl):
            raise AssertionError(f"test redirect to a real host: {newurl}")
        return real_redirect(self, req, fp, code, msg, headers, newurl)

    monkeypatch.setattr(updater._SafeRedirectHandler, "redirect_request", guarded_redirect)


@pytest.fixture(autouse=True)
def _allow_testclient_host(monkeypatch):
    """TestClient sends Host: testserver. Trust it in tests only — the shipped
    allow-list stays loopback-only (see tests/test_local_guard.py)."""
    from facturo import local_guard

    monkeypatch.setattr(local_guard, "LOCAL_HOSTS", local_guard.LOCAL_HOSTS | {"testserver"})


@pytest.fixture
def french():
    """Run one test in French: service errors are translated when they are raised,
    so tests that pin the original French wording need the language set first."""
    from facturo import i18n

    token = i18n.set_lang("fr")
    try:
        yield
    finally:
        i18n.reset_lang(token)

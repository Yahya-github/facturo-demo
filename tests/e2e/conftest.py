"""Live-server fixtures for browser tests.

Each session starts the real app (python -m uvicorn facturo.server:app) on a free
port against a fresh temp data directory, seeded through the public API — so
parallel agents and CI never share state or ports.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def api(base: str, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


@pytest.fixture(scope="session")
def live_server():
    data_dir = Path(tempfile.mkdtemp(prefix="facturo-e2e-"))
    port = _free_port()
    env = {**os.environ, "FACTURO_DATA_DIR": str(data_dir)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "facturo.server:app", "--port", str(port)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(base + "/api/clients", timeout=1)
            break
        except OSError:
            time.sleep(0.25)
    else:
        proc.kill()
        raise RuntimeError(proc.stderr.read().decode())
    client = api(base, "POST", "/api/clients",
                 {"ref": "TEST", "prefix": "tst", "nom": "CLIENT TEST INC", "adresse": "1 rue Test"})
    api(base, "POST", "/api/factures/generate", {
        "client_id": client["id"], "date": "2026-09-01",
        "billets": [{"date_billet": "2026-09-01", "chantier": "Chantier A", "plaque": "L 123456",
                     "numero_billet": "900001", "quantite": 8, "taux": 120}],
    })
    yield base
    proc.terminate()
    proc.wait(timeout=10)


# The app defaults to English; most of these tests were written against the French UI, so
# their page starts in French. Set only when unset, so a test that switches language
# keeps its choice across reloads. `page_en` covers the default language.
def lang_init_script(lang: str) -> str:
    return (f"try {{ if (!localStorage.getItem('facturo-lang')) "
            f"localStorage.setItem('facturo-lang', '{lang}'); }} catch (e) {{}}")


def _open_page(live_server, lang: str | None):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        if lang:
            context.add_init_script(lang_init_script(lang))
        pg = context.new_page()
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and pg.errors.append(m.text))
        pg.goto(live_server)
        pg.wait_for_selector(".page")
        yield pg
        browser.close()


@pytest.fixture
def page(live_server):
    yield from _open_page(live_server, "fr")


@pytest.fixture
def page_en(live_server):
    """A fresh browser with no stored preference: the app's default (English)."""
    yield from _open_page(live_server, None)

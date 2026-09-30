"""Paramètres « Mises à jour » card, sidebar dot and newer-database banner.

Runs against dev-mode servers (not frozen), so no test here can reach GitHub:
the boot-time check only runs in the frozen exe, and nothing clicks
« Vérifier ». Every request the page makes is asserted to stay on 127.0.0.1.
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

from tests.e2e.conftest import _free_port, api, lang_init_script

FAKE_TOKEN = "github_pat_e2e_should_never_reach_the_page_0123456789"


def _js_errors(pg):
    # Fonts are fetched from Google; offline runs log a network error for them.
    return [e for e in pg.errors if "fonts.g" not in e and "net::ERR" not in e]


@pytest.fixture(scope="module")
def configured_server():
    """A dev server whose update_config.json already holds a (fake) token."""
    data_dir = Path(tempfile.mkdtemp(prefix="facturo-e2e-updates-"))
    (data_dir / "update_config.json").write_text(json.dumps({"token": FAKE_TOKEN}), encoding="utf-8")
    port = _free_port()
    env = {**os.environ, "FACTURO_DATA_DIR": str(data_dir)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "facturo.server:app", "--port", str(port)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(base + "/api/version", timeout=1)
            break
        except OSError:
            time.sleep(0.25)
    else:
        proc.kill()
        raise RuntimeError(proc.stderr.read().decode())
    yield base, data_dir
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
def browser_page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1024, "height": 800})
        context.add_init_script(lang_init_script("fr"))
        pg = context.new_page()
        pg.errors, pg.requests = [], []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and pg.errors.append(m.text))
        pg.on("request", lambda r: pg.requests.append(r.url))
        yield pg
        browser.close()


def _open_settings(pg):
    pg.click('.nav-btn[data-page="settings"]')
    pg.wait_for_selector("#update-card")


def test_dev_mode_update_card_renders_without_errors(page, live_server):
    _open_settings(page)
    card = page.locator("#update-card")
    assert card.locator("h3", has_text="Mises à jour").is_visible()
    version = api(live_server, "GET", "/api/version")["version"]
    assert page.locator("#update-current").inner_text() == version
    assert "Mode développement" in card.inner_text()
    assert card.locator("#update-token").get_attribute("type") == "password"
    assert card.locator("#update-token").input_value() == ""
    assert card.locator("label[for=update-prereleases]").is_visible()
    assert card.locator("#update-check-btn").is_visible()
    assert page.locator("#update-dot").is_hidden(), "no update can be known without a check"
    assert page.locator("#db-newer-banner").count() == 0
    assert _js_errors(page) == []


def test_saved_token_is_never_shown_and_no_github_call(configured_server, browser_page):
    base, _ = configured_server
    pg = browser_page
    pg.goto(base)
    pg.wait_for_selector(".page")
    _open_settings(pg)
    pg.wait_for_function(
        "document.querySelector('#update-token').placeholder.includes('Jeton enregistré')")

    assert pg.locator("#update-token").input_value() == ""
    assert FAKE_TOKEN not in pg.content()
    assert "non configuré" not in pg.locator("#update-card").inner_text()
    assert all(u.startswith(base) or "fonts.g" in u for u in pg.requests), pg.requests
    assert not any("/api/updates/check" in u for u in pg.requests), "dev mode must not auto-check"
    assert _js_errors(pg) == []


def test_newer_database_shows_blocking_banner(configured_server, browser_page):
    base, data_dir = configured_server
    conn = sqlite3.connect(str(data_dir / "data.db"))
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    try:
        conn.execute(f"PRAGMA user_version = {current + 1}")
        conn.commit()
        pg = browser_page
        pg.goto(base)
        banner = pg.wait_for_selector("#db-newer-banner")
        text = banner.inner_text()
        assert "provient d'une version plus récente" in text
        assert "mettez à jour l'application" in text
        _open_settings(pg)
        assert pg.locator("#db-newer-banner").is_visible(), "banner must survive navigation"
        assert _js_errors(pg) == []
    finally:
        conn.execute(f"PRAGMA user_version = {current}")
        conn.commit()
        conn.close()

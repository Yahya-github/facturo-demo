#!/usr/bin/env python3
"""Regenerate the README screenshots in docs/screenshots/.

Usage:

    python scripts/screenshots.py            # English (the app's default)
    python scripts/screenshots.py --lang fr  # French

Starts the real app on a free port against a throwaway data directory, fills it
with scripts/seed_demo.py, then drives Chromium through ten views and saves
each as a WebP. Needs the dev requirements plus `playwright install chromium`
and Pillow. Nothing outside the temp directory and docs/screenshots/ is touched.
"""

from __future__ import annotations

import argparse
import io
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}
SETTLE_MS = 1400  # count-up numbers and chart entrance animations
WEBP_QUALITY = 80


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(data_dir: Path) -> tuple[subprocess.Popen, str]:
    port = free_port()
    env = {**os.environ, "FACTURO_DATA_DIR": str(data_dir)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "facturo.server:app", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            urllib.request.urlopen(base + "/api/clients", timeout=1)
            return proc, base
        except OSError:
            time.sleep(0.25)
    proc.kill()
    raise RuntimeError(proc.stderr.read().decode())


def save_webp(png: bytes, name: str) -> None:
    from PIL import Image

    OUT.mkdir(parents=True, exist_ok=True)
    Image.open(io.BytesIO(png)).convert("RGB").save(OUT / name, "WEBP", quality=WEBP_QUALITY, method=6)
    print("saved", name)


def capture(base: str, lang: str) -> None:
    from playwright.sync_api import sync_playwright

    init = (f"try {{ localStorage.setItem('facturo-lang', '{lang}'); "
            f"localStorage.setItem('facturo-theme', 'light'); }} catch (e) {{}}")
    with sync_playwright() as p:
        browser = p.chromium.launch()

        def shot(name: str, viewport=DESKTOP, script: str | None = None, act=None) -> None:
            ctx = browser.new_context(viewport=viewport, reduced_motion="no-preference")
            ctx.add_init_script(init)
            page = ctx.new_page()
            page.goto(base)
            page.wait_for_selector(".page")
            if script:
                page.evaluate(script)
                page.wait_for_selector(".page")
            page.wait_for_timeout(SETTLE_MS)
            if act:
                act(page)
                page.wait_for_timeout(500)
            save_webp(page.screenshot(), name)
            ctx.close()

        shot("01-accueil.webp")
        shot("02-historique.webp", script="navigate('history')")
        shot("03-nouvelle-facture.webp", script="newFacture()")
        shot("04-paiements.webp", script="openPayments()")
        shot("05-parametres.webp", script="navigate('settings')")
        shot("06-palette.webp", act=lambda pg: pg.keyboard.press("Control+k"))
        shot("07-accueil-sombre.webp", act=lambda pg: pg.evaluate("ui.theme.setPreference('dark')"))
        shot("08-menu-reduit.webp", act=lambda pg: pg.click("#sidebar-toggle"))
        shot("09-mobile.webp", viewport=MOBILE)
        shot("10-clients.webp", script="navigate('clients')")
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--lang", choices=("en", "fr"), default="en")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="facturo-shots-") as tmp:
        proc, base = start_server(Path(tmp))
        try:
            subprocess.run([sys.executable, str(ROOT / "scripts" / "seed_demo.py"), "--base", base],
                           check=True, stdout=subprocess.DEVNULL)
            capture(base, args.lang)
        finally:
            proc.terminate()
            proc.wait(timeout=10)


if __name__ == "__main__":
    main()

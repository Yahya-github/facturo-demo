"""Entry point: `python -m facturo` starts the local server and opens the browser."""


def _pick_port(preferred: int = 8000) -> int:
    import socket

    for candidate in (preferred, 8001, 8002, 8003, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", candidate))
                return s.getsockname()[1]
            except OSError:
                continue
    return preferred


def _open_browser(url: str) -> None:
    import subprocess
    import time
    import webbrowser

    time.sleep(1.5)  # give uvicorn a moment to start listening
    if webbrowser.open(url):
        return
    # webbrowser silently returns False in some sandboxed/minimal desktop
    # environments (no BROWSER env var, no registered handler). Fall back
    # to xdg-open directly before giving up.
    for opener in ("xdg-open", "gio"):
        try:
            args = [opener, "open", url] if opener == "gio" else [opener, url]
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except FileNotFoundError:
            continue
    print(f"Impossible d'ouvrir le navigateur automatiquement. Ouvrez manuellement : {url}")


# The helper health-checks the new exe for ~30 s and needs Factures.old.exe
# for a rollback until then, so leftovers are only removed well after that.
POST_UPDATE_CLEANUP_DELAY_SECONDS = 120
SMOKE_TIMEOUT_SECONDS = 20


def _post_update_housekeeping() -> None:
    import threading

    from facturo.services import updater

    if updater.pending_failure_report():
        # Rollback case: the helper is done; surface its report right away.
        updater.cleanup_after_update()
        return
    timer = threading.Timer(POST_UPDATE_CLEANUP_DELAY_SECONDS, updater.cleanup_after_update)
    timer.daemon = True
    timer.start()


def _smoke_test(port: int) -> int:
    """Boot the real app, GET /api/version, print the version. 0 = healthy."""
    import json
    import sys
    import threading
    import time
    import urllib.request

    import uvicorn

    from facturo.server import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}/api/version"
    deadline = time.monotonic() + SMOKE_TIMEOUT_SECONDS
    body = None
    try:
        while time.monotonic() < deadline and thread.is_alive():
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    body = json.loads(response.read().decode("utf-8"))
                break
            except OSError:
                time.sleep(0.2)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    if not body or "version" not in body:
        print("Smoke test : le serveur n'a pas répondu sur /api/version", file=sys.stderr)
        return 1
    print(f"Factures {body['version']} (schema {body.get('schema_version')})")
    return 0


def main(argv: list[str] | None = None) -> None:
    import argparse
    import os
    import shutil
    import sys
    import tempfile
    import threading

    parser = argparse.ArgumentParser(prog="facturo")
    parser.add_argument("--port", type=int, help="port to listen on (strict: no fallback)")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    parser.add_argument("--smoke-test", action="store_true",
                        help="boot once, hit /api/version, print the version, exit 0/1")
    args = parser.parse_args(argv)

    if args.smoke_test:
        # Never touch real data: use a throwaway data dir unless one is given.
        # Set before importing the app, whose modules resolve paths at import.
        temp_dir = None
        if not os.environ.get("FACTURO_DATA_DIR"):
            temp_dir = tempfile.mkdtemp(prefix="facturo-smoke-")
            os.environ["FACTURO_DATA_DIR"] = temp_dir
        try:
            code = _smoke_test(args.port or _pick_port())
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
        sys.exit(code)

    import uvicorn

    from facturo import paths
    from facturo.server import app

    if paths.IS_FROZEN:
        _post_update_housekeeping()

    port = args.port or _pick_port()
    url = f"http://localhost:{port}"
    from facturo.brand import COMPANY_NAME

    print(f"Factures — {COMPANY_NAME}")
    print(f"Ouverture de {url} dans votre navigateur...")
    print("Gardez cette fenêtre ouverte pendant l'utilisation. Fermez-la pour quitter.")

    if not args.no_browser:
        threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    # 127.0.0.1 only: local app, no LAN exposure, no Windows firewall prompt.
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()

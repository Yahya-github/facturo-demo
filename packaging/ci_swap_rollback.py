"""CI end-to-end proof of the in-app update swap and rollback (Windows only).

Run by .github/workflows/release.yml with three frozen builds of the same
source: version N, a healthy N+1 and a deliberately broken N+2 (built with
FACTURO_BUILD_BROKEN=1, which exits at startup). It uses the production
helper generator (updater._write_helper_script) and launcher
(updater._launch_helper), in a folder whose name has a space, an accent
and an ampersand, and asserts:

  1. N -> N+1: the helper waits for the still-running old PID, swaps, the new
     version answers /api/version, Factures.old.exe and the helper are gone;
  2. N+1 -> broken: the health check fails, N+1 is restored and restarted,
     it reports the rollback exactly once via /api/updates/status, and an
     unrelated Factures.exe running from another folder is left alone (the
     helper kills the PID it started, never by image name);
  3. data.db content (a hash of its full SQL dump, after a WAL checkpoint) is
     identical before and after both updates; byte hashes are printed too.

Usage: python packaging/ci_swap_rollback.py --n A.exe --next B.exe --broken C.exe \
           --n-version 0.0.1 --next-version 0.0.2 --broken-version 0.0.3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from facturo.services import updater  # noqa: E402

EXE = updater.EXE_NAME


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _get(port: int, path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(port: int, path: str, body: dict):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _wait_version(port: int, version: str, timeout: float) -> None:
    deadline, last = time.monotonic() + timeout, None
    start = time.monotonic()
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            resp = _get(port, "/api/version")
            last = resp.get("version")
            elapsed = time.monotonic() - start
            print(f"[_wait_version] Attempt {attempt} ({elapsed:.1f}s): got version {last}")
            if last == version:
                print(f"[_wait_version] SUCCESS: version {version} answered in {elapsed:.1f}s")
                return
        except (OSError, ValueError) as e:
            elapsed = time.monotonic() - start
            if attempt % 5 == 1:  # Log every 5 attempts to avoid spam
                print(f"[_wait_version] Attempt {attempt} ({elapsed:.1f}s): {type(e).__name__}")
        time.sleep(1)
    raise AssertionError(f"version {version} never answered on port {port} (last seen: {last}) after {timeout}s")


def _wait_gone(*files: Path, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and any(f.exists() for f in files):
        time.sleep(1)
    left = [f.name for f in files if f.exists()]
    assert not left, f"still present after {timeout}s: {left}"


def _start(work: Path, port: int) -> subprocess.Popen:
    env = {k: v for k, v in os.environ.items() if k != "FACTURO_DATA_DIR"}
    exe_path = str(work / EXE)
    print(f"[_start] Starting {exe_path} on port {port}")
    print(f"[_start] Working directory: {work}")
    print(f"[_start] Exe exists: {Path(exe_path).exists()}")
    if Path(exe_path).exists():
        print(f"[_start] Exe size: {Path(exe_path).stat().st_size}")
    proc = subprocess.Popen([exe_path, "--port", str(port), "--no-browser"], cwd=work,
                            env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)
    print(f"[_start] Process started with PID {proc.pid}")
    return proc


def _kill_all() -> None:
    subprocess.run(["taskkill", "/F", "/T", "/IM", EXE], capture_output=True)
    time.sleep(3)


def _db_fingerprint(db: Path) -> tuple[str, str]:
    """(content hash, byte hash) after folding the WAL into data.db."""
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        dump = "\n".join(conn.iterdump())
    finally:
        conn.close()
    return hashlib.sha256(dump.encode("utf-8")).hexdigest(), _sha(db)


def _update(work: Path, port: int, old: subprocess.Popen, new_exe: Path, expected: str) -> None:
    """What /api/updates/install does after its verified download, then the app exit."""
    print(f"\n[_update] Copying {new_exe} to {work / updater.NEW_EXE_NAME}")
    shutil.copyfile(new_exe, work / updater.NEW_EXE_NAME)

    print(f"[_update] Generating helper script (port={port}, old_pid={old.pid}, expected={expected})")
    script = updater._write_helper_script(exe_dir=work, exe_name=EXE,
                                          new_exe_name=updater.NEW_EXE_NAME, old_pid=old.pid,
                                          port=port, expected_version=expected)
    print(f"[_update] Helper script written to {script}")
    print("[_update] Helper script content (first 30 lines):")
    with open(script, 'r', encoding='ascii', errors='replace') as f:
        for i, line in enumerate(f):
            if i >= 30:
                break
            print(f"  {line.rstrip()}")

    print("[_update] Files before launching helper:")
    for f in sorted(work.glob("*")):
        print(f"  {f.name}: {f.stat().st_size if f.is_file() else 'DIR'}")

    print(f"[_update] Launching helper (detached from PID {old.pid})")
    updater._launch_helper(script)
    time.sleep(4)

    print("[_update] Files 4s after helper launch:")
    for f in sorted(work.glob("*")):
        print(f"  {f.name}: {f.stat().st_size if f.is_file() else 'DIR'}")

    assert _sha(work / EXE) != _sha(new_exe), "helper swapped before the old process exited"
    print(f"[_update] Killing old process PID {old.pid}")
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(old.pid)], capture_output=True)


def _show_logs() -> None:
    """Print any helper logs and diagnostic files found."""
    temp = Path(tempfile.gettempdir())
    print(f"\n=== Searching for helper logs in {temp} ===")

    # Search recursively for all update_helper.log files
    for log in temp.rglob("update_helper.log"):
        try:
            content = log.read_text(errors='replace')
            print(f"\n--- {log} ---")
            print(content)
        except OSError as e:
            print(f"Could not read {log}: {e}")

    # Also search for update_helper.cmd files
    for cmd in temp.rglob("update_helper.cmd"):
        try:
            content = cmd.read_text(errors='replace')
            print(f"\n--- {cmd} (first 50 lines) ---")
            lines = content.split('\n')
            print('\n'.join(lines[:50]))
        except OSError as e:
            print(f"Could not read {cmd}: {e}")

    # Search for update_failed.txt and update_new_pid.txt
    for marker in ["update_failed.txt", "update_new_pid.txt"]:
        for file in temp.rglob(marker):
            try:
                content = file.read_text(errors='replace')
                print(f"\n--- {file} ---")
                print(content)
            except OSError as e:
                print(f"Could not read {file}: {e}")


def run(args) -> None:
    work = Path(tempfile.mkdtemp()) / "Facturo té & st"
    work.mkdir()
    shutil.copyfile(args.n, work / EXE)
    port = _free_port()
    db = work / "data.db"
    print(f"work dir: {work}  port: {port}")
    print("Initial work dir contents:")
    for f in sorted(work.glob("*")):
        size = f.stat().st_size if f.is_file() else "DIR"
        print(f"  {f.name}: {size}")

    # Seed data with version N, then fingerprint it.
    _start(work, port)
    _wait_version(port, args.n_version, 90)
    client = _post(port, "/api/clients", {"ref": "CI", "prefix": "ci", "nom": "CLIENT CI",
                                          "adresse": "1 rue du Test"})
    _post(port, "/api/factures/generate", {
        "client_id": client["id"], "date": "2026-09-01",
        "billets": [{"date_billet": "2026-09-01", "chantier": "Chantier A", "plaque": "L 123456",
                     "numero_billet": "900001", "quantite": 8, "taux": 120}],
    })
    _kill_all()
    before = _db_fingerprint(db)
    print(f"data.db before: content={before[0]} bytes={before[1]}")

    # 1. Healthy update N -> N+1.
    proc = _start(work, port)
    _wait_version(port, args.n_version, 90)
    _update(work, port, proc, Path(args.next), args.next_version)
    _wait_version(port, args.next_version, 180)
    _wait_gone(work / updater.OLD_EXE_NAME, work / updater.HELPER_NAME, work / updater.NEW_EXE_NAME)
    assert _sha(work / EXE) == _sha(Path(args.next)), "Factures.exe is not the new build"
    assert not (work / updater.FAILED_FILE_NAME).exists()
    print("1. update N -> N+1: OK")
    _kill_all()
    after_update = _db_fingerprint(db)

    # 2. Broken update N+1 -> N+2 must roll back to N+1. A decoy Factures.exe
    #    (another folder, another port) must survive: the helper kills only the
    #    PID it started, never by image name.
    decoy_dir = work.parent / "decoy"
    decoy_dir.mkdir()
    shutil.copyfile(args.n, decoy_dir / EXE)
    decoy_port = _free_port()
    _start(decoy_dir, decoy_port)
    _wait_version(decoy_port, args.n_version, 90)
    proc = _start(work, port)
    _wait_version(port, args.next_version, 90)
    _update(work, port, proc, Path(args.broken), args.broken_version)
    time.sleep(10)  # let the helper swap the broken exe in before polling
    _wait_version(port, args.next_version, 240)
    status = _get(port, "/api/updates/status")
    assert status.get("update_failed_message"), f"rollback not reported: {status}"
    assert _get(port, "/api/updates/status").get("update_failed_message") is None, "reported twice"
    assert _sha(work / EXE) == _sha(Path(args.next)), "Factures.exe is not the restored N+1 build"
    _wait_gone(work / updater.NEW_EXE_NAME, work / updater.OLD_EXE_NAME, work / updater.FAILED_FILE_NAME,
               work / updater.NEW_PID_FILE_NAME)
    assert _get(decoy_port, "/api/version")["version"] == args.n_version, "decoy was killed"
    print(f"2. broken update rolled back, unrelated Factures.exe untouched: OK "
          f"({status['update_failed_message']})")
    _kill_all()
    after_rollback = _db_fingerprint(db)

    for label, fp in (("after update", after_update), ("after rollback", after_rollback)):
        print(f"data.db {label}: content={fp[0]} bytes={fp[1]}")
        assert fp[0] == before[0], f"data.db content changed {label}"
        # Bytes are informational: every app start runs schema.migrate(), which
        # re-sets PRAGMA user_version and commits, bumping SQLite's file change
        # counter even when no row changes (verified with two plain restarts).
    print("3. data.db unchanged: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("--n", "--next", "--broken", "--n-version", "--next-version", "--broken-version"):
        parser.add_argument(name, required=True)
    args = parser.parse_args()
    if not sys.platform.startswith("win"):
        print("Windows only", file=sys.stderr)
        return 2
    try:
        run(args)
        return 0
    except (AssertionError, OSError, urllib.error.URLError) as e:
        print(f"FAILED: {e}", file=sys.stderr)
        _show_logs()
        return 1
    finally:
        _kill_all()


if __name__ == "__main__":
    sys.exit(main())

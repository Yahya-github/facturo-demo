"""Security hardening of facturo.services.updater beyond the base contract.

Every HTTP interaction uses the local fake servers from tests/support; the
"remote" hosts below are never contacted (the URL checks refuse them first).
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys

import pytest
from fastapi.testclient import TestClient

from facturo import paths, version
from facturo.api import updates as updates_api
from facturo.core import database as db
from facturo.server import app
from facturo.services import updater
from tests.support import fake_http as fh


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "CONFIG_PATH", tmp_path / "update_config.json")
    updater.reset_cache()
    yield
    updater.reset_cache()


# ── where the token may go ────────────────────────────────


@pytest.mark.parametrize("url, carries_token, allowed", [
    ("https://api.github.com/repos/x/y/releases/assets/1", True, True),
    ("https://objects.githubusercontent.com/blob", True, False),   # token never leaves GitHub's API
    ("https://objects.githubusercontent.com/blob", False, True),   # tokenless redirect target: fine
    ("http://api.github.com/repos", True, False),                  # plain HTTP refused
    ("http://example.com/blob", False, False),
    ("http://127.0.0.1:8000/x", True, True),                       # loopback test servers
    ("file:///etc/passwd", False, False),
    ("ftp://example.com/x", False, False),
])
def test_url_policy(url, carries_token, allowed):
    assert updater._url_allowed(url, carries_token=carries_token) is allowed


def test_download_refuses_to_send_the_token_to_a_foreign_host(tmp_path):
    with pytest.raises(updater.UpdateError, match="refusée"):
        updater.download(exe_asset_url="https://evil.example/Factures.exe",
                         sha_asset_url="https://evil.example/Factures.exe.sha256",
                         dest_dir=tmp_path, token="secret")
    assert not (tmp_path / updater.NEW_EXE_NAME).exists()


def test_redirect_to_plain_http_is_refused(tmp_path):
    server, _ = fh.make_server({
        "/assets/1": lambda h: fh.redirect_response(h, "http://storage.example/blob"),
        "/assets/2": lambda h: fh.text_response(h, 200, "a" * 64),  # sha is fetched first
    })
    with fh.running(server) as base:
        with pytest.raises(updater.UpdateError, match="refusée"):
            updater.download(exe_asset_url=f"{base}/assets/1", sha_asset_url=f"{base}/assets/2",
                             dest_dir=tmp_path, token="tok")
    assert list(tmp_path.iterdir()) == []


# ── download integrity ────────────────────────────────────


def _serve(payload: bytes, sha_text: str):
    return fh.make_server({
        "/assets/1": lambda h: fh.bytes_response(h, 200, payload),
        "/assets/2": lambda h: fh.text_response(h, 200, sha_text),
    })


def test_download_is_size_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "MAX_EXE_BYTES", 10)
    payload = b"x" * 11
    server, _ = _serve(payload, hashlib.sha256(payload).hexdigest())
    with fh.running(server) as base:
        with pytest.raises(updater.UpdateError, match="volumineux"):
            updater.download(exe_asset_url=f"{base}/assets/1", sha_asset_url=f"{base}/assets/2",
                             dest_dir=tmp_path, token="tok")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("sha_text", ["", "not-a-hash  Factures.exe\n", "abc"])
def test_download_rejects_a_malformed_sha_file(tmp_path, sha_text):
    server, _ = _serve(b"exe-bytes", sha_text)
    with fh.running(server) as base:
        with pytest.raises(updater.UpdateError, match="SHA-256"):
            updater.download(exe_asset_url=f"{base}/assets/1", sha_asset_url=f"{base}/assets/2",
                             dest_dir=tmp_path, token="tok")
    assert list(tmp_path.iterdir()) == []


def test_download_rejects_an_empty_body(tmp_path):
    server, _ = _serve(b"", hashlib.sha256(b"").hexdigest())
    with fh.running(server) as base:
        with pytest.raises(updater.UpdateError, match="vide"):
            updater.download(exe_asset_url=f"{base}/assets/1", sha_asset_url=f"{base}/assets/2",
                             dest_dir=tmp_path, token="tok")


def test_download_http_error_is_mapped_without_the_token(tmp_path):
    server, _ = fh.make_server({"/assets/1": lambda h: fh.text_response(h, 403, "no"),
                                "/assets/2": lambda h: fh.text_response(h, 200, "a" * 64)})
    with fh.running(server) as base:
        with pytest.raises(updater.UpdateError, match="refus") as exc:
            updater.download(exe_asset_url=f"{base}/assets/1", sha_asset_url=f"{base}/assets/2",
                             dest_dir=tmp_path, token="ghp_secret_value")
    assert "ghp_secret_value" not in str(exc.value)


# ── check() robustness ────────────────────────────────────

RELEASES_PATH = f"/repos/{updater.GITHUB_OWNER}/{updater.GITHUB_REPO}/releases"


def test_check_rejects_a_non_list_payload():
    server, _ = fh.make_server({RELEASES_PATH: lambda h: fh.json_response(h, 200, {"m": "odd"})})
    with fh.running(server) as base:
        with pytest.raises(updater.UpdateError, match="illisible"):
            updater.check(base_url=base, token="tok", force=True)


def test_check_maps_server_errors():
    server, _ = fh.make_server({RELEASES_PATH: lambda h: fh.json_response(h, 502, {})})
    with fh.running(server) as base:
        with pytest.raises(updater.UpdateError, match="502"):
            updater.check(base_url=base, token="tok", force=True)


def test_check_without_assets_reports_no_asset(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: "1.0.0")
    release = {"tag_name": "v2.0.0", "draft": False, "prerelease": False, "body": None,
               "published_at": None, "assets": []}
    server, _ = fh.make_server({RELEASES_PATH: lambda h: fh.json_response(h, 200, [release])})
    with fh.running(server) as base:
        result = updater.check(base_url=base, token="tok", force=True)
    assert result["available"] is True and result["asset"] is None
    assert result["notes"] == "" and result["published_at"] == ""
    assert updater.status()["last_check"]


def test_compare_versions_rejects_garbage():
    with pytest.raises(ValueError):
        updater.compare_versions("2.0", "2.0.0")
    assert updater.compare_versions("2.0.0-rc9", "2.0.0-rc10") == -1


# ── config file ───────────────────────────────────────────


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permission bits")
def test_config_file_is_owner_only():
    updater.save_config({"token": "t"})
    mode = stat.S_IMODE(os.stat(updater.CONFIG_PATH).st_mode)
    assert mode == 0o600
    assert updater.load_config() == {"token": "t"}


def test_corrupt_config_is_ignored():
    updater.CONFIG_PATH.write_text("{not json", encoding="utf-8")
    assert updater.load_config() == {}
    updater.CONFIG_PATH.write_text("[1, 2]", encoding="utf-8")
    assert updater.load_config() == {}


@pytest.mark.parametrize("bad", ["two words", "tok\nen", "x" * 300])
def test_set_config_rejects_malformed_tokens_before_any_network(monkeypatch, bad):
    monkeypatch.setattr(updater, "check", lambda **k: pytest.fail("must not validate remotely"))
    with pytest.raises(updater.UpdateError, match="invalide"):
        updater.set_config(token=bad)
    assert not updater.CONFIG_PATH.exists()


def test_set_config_empty_token_falls_back_to_sync_token(monkeypatch):
    from facturo.services import sync

    updater.save_config({"token": "old"})
    monkeypatch.setattr(sync, "load_config", lambda: {"token": "sync-tok"})
    seen = {}
    monkeypatch.setattr(updater, "check", lambda **k: seen.update(k) or {})
    result = updater.set_config(token="  ")
    assert seen["token"] == "sync-tok"
    assert "token" not in updater.load_config()
    assert result["configured"] is True and "token" not in result


# ── helper script ─────────────────────────────────────────


def _script(**over):
    kw = dict(exe_dir="C:\\Program Files\\Façade & Co", exe_name="Factures.exe",
              new_exe_name="Factures.exe.new", old_pid=4242, port=8123, expected_version="2.1.0")
    kw.update(over)
    return updater.build_helper_script(**kw)


def test_helper_script_is_ascii_crlf_and_path_free():
    script = _script()
    script.encode("ascii")
    assert "\r\n" in script and "\n" not in script.replace("\r\n", "")
    assert "Façade" not in script and "Program Files" not in script
    assert "%~dp0" in script
    assert "/api/version?expect=2.1.0" in script
    assert "timeout /t" not in script.lower(), "timeout aborts without a console"


@pytest.mark.parametrize("over", [
    {"exe_name": "Factures.exe & calc"}, {"new_exe_name": "..\\x.exe"},
    {"old_pid": 0}, {"port": 70000}, {"expected_version": "2.1.0 & calc"},
])
def test_helper_script_rejects_unsafe_inputs(over):
    with pytest.raises(ValueError):
        _script(**over)


def test_launch_helper_refuses_outside_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(updater.UpdateError, match="Windows"):
        updater._launch_helper(tmp_path / "update_helper.cmd")


def test_launch_helper_starts_cmd_detached_without_pyinstaller_env(monkeypatch, tmp_path):
    import subprocess

    monkeypatch.setattr(sys, "platform", "win32")
    for name, value in (("CREATE_NO_WINDOW", 0x08000000), ("CREATE_NEW_PROCESS_GROUP", 0x200),
                        ("CREATE_BREAKAWAY_FROM_JOB", 0x01000000)):
        monkeypatch.setattr(subprocess, name, value, raising=False)
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "x")
    calls = []

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            raise OSError("breakaway not allowed")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    script = tmp_path / "update_helper.cmd"
    updater._launch_helper(script)
    assert len(calls) == 2, "falls back when job breakaway is refused"
    args, kwargs = calls[1]
    # `call` must be its own argument: with the path first, cmd.exe's /c quote
    # stripping splits a folder such as "Facturo té & st" at the ampersand.
    assert args[1:] == ["/d", "/c", "call", str(script)]
    assert "_PYI_APPLICATION_HOME_DIR" not in kwargs["env"]


def _frozen_install_env(monkeypatch, tmp_path, check_result):
    monkeypatch.setattr(paths, "IS_FROZEN", True)
    monkeypatch.setattr("sys.executable", str(tmp_path / "Factures.exe"))
    monkeypatch.setattr(updater, "_exe_dir_writable", lambda p: True)
    monkeypatch.setattr(updater, "_resolve_token", lambda cfg=None: "tok")
    monkeypatch.setattr(db, "checkpoint", lambda: None)
    monkeypatch.setattr(updater, "check", lambda **k: check_result)


def test_install_removes_download_and_helper_when_launch_fails(monkeypatch, tmp_path):
    _frozen_install_env(monkeypatch, tmp_path, {
        "available": True, "latest": "2.1.0", "asset": {"exe_url": "u1", "sha256_url": "u2"}})
    new = tmp_path / updater.NEW_EXE_NAME

    def fake_download(**k):
        new.write_bytes(b"verified")
        return new

    monkeypatch.setattr(updater, "download", fake_download)
    monkeypatch.setattr(sys, "platform", "linux")  # the real _launch_helper refuses
    with pytest.raises(updater.UpdateError, match="Windows"):
        updater.install(port=8123)
    assert not new.exists()
    assert not (tmp_path / updater.HELPER_NAME).exists()


def test_install_refuses_a_renamed_exe(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "IS_FROZEN", True)
    monkeypatch.setattr("sys.executable", str(tmp_path / "Factures (1).exe"))
    monkeypatch.setattr(updater, "_exe_dir_writable", lambda p: True)
    with pytest.raises(updater.UpdateError, match="Factures.exe"):
        updater.install(port=8123)


def test_install_refuses_a_release_without_exe(monkeypatch, tmp_path):
    _frozen_install_env(monkeypatch, tmp_path, {"available": True, "latest": "2.1.0", "asset": None})
    with pytest.raises(updater.UpdateError, match="ne contient pas"):
        updater.install(port=8123)


def test_exe_dir_writable_probe(tmp_path):
    assert updater._exe_dir_writable(tmp_path) is True
    assert updater._exe_dir_writable(tmp_path / "missing") is False


# ── rollback report and leftovers ─────────────────────────


def test_cleanup_translates_helper_codes_and_removes_leftovers(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "IS_FROZEN", True)
    monkeypatch.setattr("sys.executable", str(tmp_path / "Factures.exe"))
    (tmp_path / updater.FAILED_FILE_NAME).write_text("ROLLBACK HEALTH_CHECK_FAILED\r\n")
    leftovers = (updater.FAILED_EXE_NAME, updater.HELPER_NAME, updater.NEW_EXE_NAME)
    for name in leftovers:
        (tmp_path / name).write_bytes(b"x")
    assert updater.pending_failure_report() is True
    result = updater.cleanup_after_update()
    assert "n'a pas démarré" in result["message"]
    assert not any((tmp_path / n).exists() for n in leftovers)
    assert updater.pending_failure_report() is False


def test_cleanup_unknown_code_uses_generic_message(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "IS_FROZEN", True)
    monkeypatch.setattr("sys.executable", str(tmp_path / "Factures.exe"))
    (tmp_path / updater.FAILED_FILE_NAME).write_text("ROLLBACK SOMETHING_NEW")
    assert "précédente" in updater.cleanup_after_update()["message"]


# ── API layer ─────────────────────────────────────────────


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "api.db")
    with TestClient(app) as c:
        yield c


def test_version_expect_matches_only_the_running_version(client):
    assert client.get(f"/api/version?expect={version.__version__}").status_code == 200
    assert client.get(f"/api/version?expect=v{version.__version__}").status_code == 200
    assert client.get("/api/version?expect=99.0.0").status_code == 409


def test_install_endpoint_schedules_exit_only_when_frozen(client, monkeypatch):
    started = []

    class FakeTimer:
        def __init__(self, delay, fn, args=()):
            started.append((delay, fn, args))
            self.daemon = False

        def start(self):
            pass

    monkeypatch.setattr(updates_api.threading, "Timer", FakeTimer)
    monkeypatch.setattr(updater, "install", lambda **k: {"ok": True, "version": "2.1.0"})

    monkeypatch.setattr(paths, "IS_FROZEN", False)
    assert client.post("/api/updates/install", json={"port": 8123}).status_code == 200
    assert started == []

    monkeypatch.setattr(paths, "IS_FROZEN", True)
    assert client.post("/api/updates/install", json={"port": 8123}).status_code == 200
    assert len(started) == 1 and started[0][1] is os._exit


def test_install_endpoint_rejects_invalid_ports(client):
    assert client.post("/api/updates/install", json={"port": 0}).status_code == 422
    assert client.post("/api/updates/install", json={"port": 70000}).status_code == 422


# ── C1: concurrent installs/downloads ─────────────────────


def test_concurrent_downloads_cannot_mix_payloads(tmp_path):
    """Two overlapping downloads into the same folder: the second is refused at
    once, and the promoted Factures.exe.new is byte-for-byte the verified one."""
    import threading

    payload_a, payload_b = b"A" * 300_000, b"B" * 300_000
    started, release_a = threading.Event(), threading.Event()

    def slow_a(handler):
        started.set()
        release_a.wait(10)
        fh.bytes_response(handler, 200, payload_a)

    server_a, _ = fh.make_server({
        "/assets/1": slow_a,
        "/assets/2": lambda h: fh.text_response(h, 200, hashlib.sha256(payload_a).hexdigest()),
    })
    server_b, received_b = _serve(payload_b, hashlib.sha256(payload_b).hexdigest())
    outcome = {}

    def first(base):
        try:
            outcome["a"] = updater.download(exe_asset_url=f"{base}/assets/1",
                                            sha_asset_url=f"{base}/assets/2",
                                            dest_dir=tmp_path, token="tok")
        except Exception as e:  # surfaced by the assertions below
            outcome["a_error"] = e

    with fh.running(server_a) as base_a, fh.running(server_b) as base_b:
        t = threading.Thread(target=first, args=(base_a,))
        t.start()
        assert started.wait(10)
        with pytest.raises(updater.UpdateError, match="déjà en cours"):
            updater.download(exe_asset_url=f"{base_b}/assets/1", sha_asset_url=f"{base_b}/assets/2",
                             dest_dir=tmp_path, token="tok")
        release_a.set()
        t.join(15)

    assert "a_error" not in outcome, outcome.get("a_error")
    final = outcome["a"]
    assert final.read_bytes() == payload_a
    assert hashlib.sha256(final.read_bytes()).hexdigest() == hashlib.sha256(payload_a).hexdigest()
    assert received_b == [], "the refused download must not have touched the network"
    assert sorted(p.name for p in tmp_path.iterdir()) == [updater.NEW_EXE_NAME]


def test_install_is_refused_while_another_install_runs(monkeypatch):
    import threading

    held, done = threading.Event(), threading.Event()

    def holder():
        with updater._install_lock:
            held.set()
            done.wait(10)

    t = threading.Thread(target=holder)
    t.start()
    try:
        assert held.wait(10)
        monkeypatch.setattr(paths, "IS_FROZEN", True)
        with pytest.raises(updater.UpdateError, match="Une mise à jour est déjà en cours."):
            updater.install(port=8123)
    finally:
        done.set()
        t.join(10)
    monkeypatch.setattr(paths, "IS_FROZEN", False)
    with pytest.raises(updater.UpdateError, match="développement"):
        updater.install(port=8123)  # lock released: normal preconditions apply again


def test_download_rehashes_the_file_on_disk_before_promoting(tmp_path, monkeypatch):
    payload = b"exe-bytes"
    server, _ = _serve(payload, hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(updater, "_sha256_file", lambda path: "0" * 64)  # disk != stream
    with fh.running(server) as base:
        with pytest.raises(updater.UpdateError, match="SHA-256"):
            updater.download(exe_asset_url=f"{base}/assets/1", sha_asset_url=f"{base}/assets/2",
                             dest_dir=tmp_path, token="tok")
    assert list(tmp_path.iterdir()) == []


def test_download_verifies_again_after_promotion(tmp_path, monkeypatch):
    payload = b"exe-bytes"
    good = hashlib.sha256(payload).hexdigest()
    server, _ = _serve(payload, good)
    real = updater._sha256_file
    monkeypatch.setattr(updater, "_sha256_file",
                        lambda path: real(path) if path.name.endswith(".part") else "f" * 64)
    with fh.running(server) as base:
        with pytest.raises(updater.UpdateError, match="SHA-256"):
            updater.download(exe_asset_url=f"{base}/assets/1", sha_asset_url=f"{base}/assets/2",
                             dest_dir=tmp_path, token="tok")
    assert list(tmp_path.iterdir()) == []


def test_cleanup_removes_stray_part_files(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "IS_FROZEN", True)
    monkeypatch.setattr("sys.executable", str(tmp_path / "Factures.exe"))
    stray = tmp_path / "Factures.exe.new.abc123.part"
    stray.write_bytes(b"x")
    (tmp_path / updater.NEW_PID_FILE_NAME).write_text("1234")
    updater.cleanup_after_update()
    assert not stray.exists() and not (tmp_path / updater.NEW_PID_FILE_NAME).exists()


# ── M2: rollback kills only the new process ───────────────


def test_helper_kills_only_the_pid_it_started():
    script = _script()
    assert "/IM" not in script.upper().replace("/IMAGE", "")
    assert "taskkill /F /T /PID %NEW_PID%" in script
    assert "Start-Process -FilePath $env:NEW_EXE_PATH" in script and "-PassThru" in script
    assert "--port','8123','--no-browser'" in script


# ── H2: token at rest, separate releases repo ─────────────


def test_releases_come_from_a_separate_repo():
    assert (updater.GITHUB_OWNER, updater.GITHUB_REPO) == ("your-github-user", "facturo-releases")
    assert updater.RELEASES_REPO != "Facturo"


def _fake_dpapi(monkeypatch):
    monkeypatch.setattr(updater, "_use_dpapi", lambda: True)

    def fake(data, *, protect):
        if protect:
            return b"ENC:" + data[::-1]
        if not data.startswith(b"ENC:"):
            raise OSError("blob from another Windows user")
        return data[4:][::-1]

    monkeypatch.setattr(updater, "_dpapi", fake)


def test_windows_token_is_encrypted_at_rest(monkeypatch):
    import json

    _fake_dpapi(monkeypatch)
    updater.save_config({"token": "github_pat_secret", "include_prereleases": True})
    on_disk = updater.CONFIG_PATH.read_text(encoding="utf-8")
    assert "github_pat_secret" not in on_disk
    assert set(json.loads(on_disk)) == {"token_dpapi", "include_prereleases"}
    assert updater.load_config() == {"token": "github_pat_secret", "include_prereleases": True}


def test_windows_plaintext_token_is_migrated_on_read(monkeypatch):
    import json

    updater.CONFIG_PATH.write_text(json.dumps({"token": "github_pat_legacy"}), encoding="utf-8")
    _fake_dpapi(monkeypatch)
    assert updater.load_config()["token"] == "github_pat_legacy"
    stored = json.loads(updater.CONFIG_PATH.read_text(encoding="utf-8"))
    assert "token" not in stored and stored["token_dpapi"]


def test_undecryptable_token_is_dropped_not_crashed(monkeypatch):
    import json

    from facturo.services import sync

    updater.CONFIG_PATH.write_text(json.dumps({"token_dpapi": "Zm9v"}), encoding="utf-8")
    _fake_dpapi(monkeypatch)
    monkeypatch.setattr(sync, "load_config", lambda: None)
    assert updater.load_config() == {}
    assert updater.status()["configured"] is False


def test_non_windows_keeps_plaintext_in_0600_file(monkeypatch):
    import json

    monkeypatch.setattr(updater, "_use_dpapi", lambda: False)
    updater.save_config({"token": "t", "token_dpapi": "stale"})
    assert json.loads(updater.CONFIG_PATH.read_text(encoding="utf-8")) == {"token": "t"}


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="real DPAPI needs Windows")
def test_real_dpapi_roundtrip():
    blob = updater._protect_token("github_pat_roundtrip")
    assert "github_pat_roundtrip" not in blob
    assert updater._unprotect_token(blob) == "github_pat_roundtrip"


# ── the suite itself can never reach GitHub ───────────────


def test_unmocked_set_config_cannot_reach_github():
    with pytest.raises(updater.UpdateError, match="[Cc]onnexion"):
        updater.set_config(token="github_pat_would_be_sent")
    assert not updater.CONFIG_PATH.exists()
    assert updater.GITHUB_API_BASE.startswith("http://127.0.0.1:")


# ── Silent-failure review: unexpected errors during install ──


def test_install_maps_a_checkpoint_failure_to_update_error(monkeypatch, tmp_path):
    import sqlite3

    _frozen_install_env(monkeypatch, tmp_path, {
        "available": True, "latest": "2.1.0", "asset": {"exe_url": "u1", "sha256_url": "u2"}})

    def locked():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(db, "checkpoint", locked)
    downloads = []
    monkeypatch.setattr(updater, "download", lambda **k: downloads.append(k))
    with pytest.raises(updater.UpdateError,
                       match="Impossible de préparer la base de données pour la mise à jour."):
        updater.install(port=8123)
    assert downloads == []  # nothing fetched once the database could not be prepared


def test_install_endpoint_unexpected_error_is_a_french_500_without_the_token(client, monkeypatch, caplog):
    secret = "github_pat_install_should_never_leak_0123456789"

    def explode(**k):
        raise RuntimeError(f"https://x-access-token:{secret}@api.github.com failed")

    monkeypatch.setattr(updater, "install", explode)
    r = client.post("/api/updates/install", json={"port": 8123})
    assert r.status_code == 500
    assert "mise à jour" in r.json()["detail"]
    assert secret not in r.text
    assert secret not in caplog.text


# ── Q1 review ─────────────────────────────────────────────


@pytest.mark.parametrize("name", [".", "..", ".hidden.exe", "..exe"])
def test_helper_script_rejects_dot_names(name):
    with pytest.raises(ValueError):
        _script(new_exe_name=name)


def test_sha_is_fetched_before_the_exe(tmp_path):
    payload = b"exe-bytes"
    server, received = _serve(payload, hashlib.sha256(payload).hexdigest())
    with fh.running(server) as base:
        updater.download(exe_asset_url=f"{base}/assets/1", sha_asset_url=f"{base}/assets/2",
                         dest_dir=tmp_path, token="tok")
    assert [r["path"] for r in received] == ["/assets/2", "/assets/1"]


def test_bad_sha_file_means_the_exe_is_never_downloaded(tmp_path):
    server, received = _serve(b"exe-bytes", "not-a-hash")
    with fh.running(server) as base, pytest.raises(updater.UpdateError):
        updater.download(exe_asset_url=f"{base}/assets/1", sha_asset_url=f"{base}/assets/2",
                         dest_dir=tmp_path, token="tok")
    assert "/assets/1" not in [r["path"] for r in received]


def test_os_error_after_promotion_removes_the_promoted_exe(tmp_path, monkeypatch):
    payload = b"exe-bytes"
    server, _ = _serve(payload, hashlib.sha256(payload).hexdigest())
    real = updater._sha256_file

    def unreadable_after_promotion(path):
        if path.name == updater.NEW_EXE_NAME:
            raise OSError("locked by antivirus")
        return real(path)

    monkeypatch.setattr(updater, "_sha256_file", unreadable_after_promotion)
    with fh.running(server) as base, pytest.raises(updater.UpdateError):
        updater.download(exe_asset_url=f"{base}/assets/1", sha_asset_url=f"{base}/assets/2",
                         dest_dir=tmp_path, token="tok")
    assert list(tmp_path.iterdir()) == []


def test_set_config_does_not_swallow_a_pending_failure_message(monkeypatch):
    monkeypatch.setattr(updater, "_last_update_failure", "La mise à jour a échoué.")
    monkeypatch.setattr(updater, "check", lambda **k: {"available": False})
    assert updater.set_config(include_prereleases=True)["update_failed_message"] \
        == "La mise à jour a échoué."
    assert updater.status()["update_failed_message"] == "La mise à jour a échoué."
    assert updater.status()["update_failed_message"] is None

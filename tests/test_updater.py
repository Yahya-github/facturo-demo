"""RED tests for `facturo.services.updater` (in-app GitHub-Releases updates).

Nothing here ever calls the real GitHub API: every HTTP interaction goes
through a local fake server (`tests/support/fake_http.py`) started on
127.0.0.1:0. See `changes/team-d.md` for the full contract these tests define
— a separate implementer makes them pass; nothing in this file is executable
production code.

Every test isolates two pieces of shared module state explicitly, because
`facturo.services.updater` mirrors `facturo.services.sync`'s module-level
config-path pattern:
  * `updater.CONFIG_PATH`   — monkeypatched to a throwaway file per test that
    needs one (never the real `update_config.json`).
  * `updater._cache`        — the in-memory 1h check() cache; reset before and
    after every test so results don't leak between tests.
"""

from __future__ import annotations

import hashlib
import logging

import pytest

from facturo import paths
from facturo.core import database as db
from facturo.core import schema
from facturo.services import sync, updater
from tests.support import fake_http as fh

GITHUB_RELEASES_PATH = f"/repos/{updater.GITHUB_OWNER}/{updater.GITHUB_REPO}/releases"


@pytest.fixture(autouse=True)
def _isolate_updater_state():
    updater.reset_cache()
    yield
    updater.reset_cache()


def _release(tag, *, draft=False, prerelease=False, published_at="2026-01-01T00:00:00Z",
             body="Notes", assets=None):
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "published_at": published_at,
        "body": body,
        "assets": assets or [],
    }


def _releases_payload(tag="v2.0.0", asset_base="http://example.invalid"):
    return [_release(tag, assets=[
        {"name": "Factures.exe", "url": f"{asset_base}/assets/1"},
        {"name": "Factures.exe.sha256", "url": f"{asset_base}/assets/2"},
    ])]


# ── semver compare, including -rcN ordering ──────────────


@pytest.mark.parametrize("lower, higher", [
    ("2.0.0-rc1", "2.0.0-rc2"),
    ("2.0.0-rc2", "2.0.0"),
    ("2.0.0", "2.0.1"),
    ("1.9.9", "2.0.0"),
    ("2.0.0-rc9", "2.0.0-rc10"),  # numeric rc compare, not lexicographic
])
def test_compare_versions_orders_lower_before_higher(lower, higher):
    assert updater.compare_versions(lower, higher) < 0
    assert updater.compare_versions(higher, lower) > 0


def test_compare_versions_equal_versions():
    assert updater.compare_versions("2.0.0", "2.0.0") == 0


def test_compare_versions_ignores_leading_v():
    assert updater.compare_versions("v2.0.0", "2.0.0") == 0
    assert updater.compare_versions("v2.0.0-rc1", "2.0.0-rc1") == 0


def test_is_prerelease_tag():
    assert updater.is_prerelease_tag("2.0.0-rc1") is True
    assert updater.is_prerelease_tag("v2.0.0-rc12") is True
    assert updater.is_prerelease_tag("2.0.0") is False
    assert updater.is_prerelease_tag("v2.0.0") is False


# ── release selection (drafts / prereleases) ─────────────


def test_select_release_skips_drafts_always():
    releases = [_release("v2.0.1", draft=True), _release("v2.0.0")]
    picked = updater.select_release(releases, include_prereleases=True)
    assert picked["tag_name"] == "v2.0.0"


def test_select_release_skips_prereleases_by_default():
    releases = [_release("v2.1.0-rc1", prerelease=True), _release("v2.0.0")]
    picked = updater.select_release(releases, include_prereleases=False)
    assert picked["tag_name"] == "v2.0.0"


def test_select_release_includes_prereleases_when_enabled():
    releases = [_release("v2.1.0-rc1", prerelease=True), _release("v2.0.0")]
    picked = updater.select_release(releases, include_prereleases=True)
    assert picked["tag_name"] == "v2.1.0-rc1"


def test_select_release_picks_highest_version_regardless_of_list_order():
    releases = [_release("v2.0.0"), _release("v2.0.1"), _release("v1.9.0")]
    picked = updater.select_release(releases, include_prereleases=False)
    assert picked["tag_name"] == "v2.0.1"


def test_select_release_skips_tags_that_are_not_valid_semver():
    releases = [_release("nightly-build"), _release("v2.0.0")]
    picked = updater.select_release(releases, include_prereleases=True)
    assert picked["tag_name"] == "v2.0.0"


def test_select_release_returns_none_when_nothing_eligible():
    assert updater.select_release([_release("v2.0.0-rc1", prerelease=True)],
                                   include_prereleases=False) is None
    assert updater.select_release([], include_prereleases=True) is None


# ── check() against a fake GitHub server ─────────────────


def test_check_reports_available_when_release_is_newer(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: "1.9.0")
    server, received = fh.make_server({
        GITHUB_RELEASES_PATH: lambda h: fh.json_response(h, 200, _releases_payload()),
    })
    with fh.running(server) as base_url:
        result = updater.check(base_url=base_url, token="tok", force=True)

    assert result["current"] == "1.9.0"
    assert result["latest"] == "2.0.0"
    assert result["available"] is True
    assert "Notes" in result["notes"]
    assert result["asset"]["exe_url"] == "http://example.invalid/assets/1"
    assert result["asset"]["sha256_url"] == "http://example.invalid/assets/2"
    assert received[0]["headers"].get("Authorization") == "Bearer tok"


def test_check_reports_not_available_when_up_to_date(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: "2.0.0")
    server, _ = fh.make_server({
        GITHUB_RELEASES_PATH: lambda h: fh.json_response(h, 200, _releases_payload(tag="v2.0.0")),
    })
    with fh.running(server) as base_url:
        result = updater.check(base_url=base_url, token="tok", force=True)
    assert result["available"] is False


def test_check_raises_when_no_token_configured(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "CONFIG_PATH", tmp_path / "update_config.json")
    monkeypatch.setattr(sync, "load_config", lambda: None)
    # Port 1 is never reachable for an unprivileged client; if check() ever
    # tried to connect despite having no token, this would hang/fail with a
    # *different* error and the match= below would catch that mistake.
    with pytest.raises(updater.UpdateError, match="[Jj]eton"):
        updater.check(base_url="http://127.0.0.1:1", force=True)


def test_check_raises_friendly_message_on_401(monkeypatch):
    server, _ = fh.make_server({
        GITHUB_RELEASES_PATH: lambda h: fh.json_response(h, 401, {"message": "Bad credentials"}),
    })
    with fh.running(server) as base_url:
        with pytest.raises(updater.UpdateError, match="refus"):
            updater.check(base_url=base_url, token="bad-token", force=True)


def test_check_raises_friendly_message_on_403(monkeypatch):
    server, _ = fh.make_server({
        GITHUB_RELEASES_PATH: lambda h: fh.json_response(h, 403, {"message": "Forbidden"}),
    })
    with fh.running(server) as base_url:
        with pytest.raises(updater.UpdateError, match="refus"):
            updater.check(base_url=base_url, token="scoped-wrong", force=True)


def test_check_raises_friendly_message_on_404(monkeypatch):
    server, _ = fh.make_server({
        GITHUB_RELEASES_PATH: lambda h: fh.json_response(h, 404, {"message": "Not Found"}),
    })
    with fh.running(server) as base_url:
        with pytest.raises(updater.UpdateError, match="introuvable"):
            updater.check(base_url=base_url, token="tok", force=True)


def test_check_raises_friendly_message_on_network_error():
    with pytest.raises(updater.UpdateError, match="[Cc]onnexion"):
        updater.check(base_url="http://127.0.0.1:1", token="tok", force=True)


def test_check_caches_result_for_one_hour(monkeypatch):
    fake_clock = {"t": 1_000_000.0}
    monkeypatch.setattr(updater, "_monotonic", lambda: fake_clock["t"])
    server, received = fh.make_server({
        GITHUB_RELEASES_PATH: lambda h: fh.json_response(h, 200, _releases_payload()),
    })
    with fh.running(server) as base_url:
        updater.check(base_url=base_url, token="tok")
        updater.check(base_url=base_url, token="tok")  # served from cache
        assert len(received) == 1

        fake_clock["t"] += 60  # well under the 1h TTL
        updater.check(base_url=base_url, token="tok")
        assert len(received) == 1

        updater.check(base_url=base_url, token="tok", force=True)  # explicit bypass
        assert len(received) == 2


def test_check_cache_expires_after_ttl(monkeypatch):
    fake_clock = {"t": 1_000_000.0}
    monkeypatch.setattr(updater, "_monotonic", lambda: fake_clock["t"])
    server, received = fh.make_server({
        GITHUB_RELEASES_PATH: lambda h: fh.json_response(h, 200, _releases_payload()),
    })
    with fh.running(server) as base_url:
        updater.check(base_url=base_url, token="tok")
        fake_clock["t"] += 3601  # past the 1h TTL
        updater.check(base_url=base_url, token="tok")
        assert len(received) == 2


def test_check_never_logs_the_token(monkeypatch, caplog):
    secret = "ghp_should_never_appear_in_any_log_line"
    caplog.set_level(logging.DEBUG)
    server, _ = fh.make_server({
        GITHUB_RELEASES_PATH: lambda h: fh.json_response(h, 401, {"message": "Bad credentials"}),
    })
    with fh.running(server) as base_url:
        with pytest.raises(updater.UpdateError) as exc_info:
            updater.check(base_url=base_url, token=secret, force=True)
    assert secret not in str(exc_info.value)
    assert secret not in caplog.text
    for record in caplog.records:
        assert secret not in record.getMessage()


# ── download(): redirect must drop Authorization, sha256 verified ──────────


def test_download_follows_redirect_without_forwarding_authorization(tmp_path):
    payload = b"fake-exe-bytes-" * 200
    digest = hashlib.sha256(payload).hexdigest()

    def storage_route(handler):
        if "Authorization" in handler.headers:
            fh.text_response(handler, 403, "signed storage URLs must not carry Authorization")
        else:
            fh.bytes_response(handler, 200, payload)

    storage_server, storage_received = fh.make_server({"/blob/exe": storage_route})

    def asset_route(handler):
        if "Authorization" not in handler.headers:
            fh.text_response(handler, 401, "token required")
        else:
            fh.redirect_response(handler, f"http://127.0.0.1:{storage_server.server_port}/blob/exe")

    def sha_route(handler):
        if "Authorization" not in handler.headers:
            fh.text_response(handler, 401, "token required")
        else:
            fh.text_response(handler, 200, f"{digest}  Factures.exe\n")

    api_server, api_received = fh.make_server({"/assets/1": asset_route, "/assets/2": sha_route})

    with fh.running(storage_server), fh.running(api_server) as api_base:
        dest_dir = tmp_path / "exe_dir"
        dest_dir.mkdir()
        result = updater.download(
            exe_asset_url=f"{api_base}/assets/1",
            sha_asset_url=f"{api_base}/assets/2",
            dest_dir=dest_dir,
            token="secret-download-token",
        )

    assert result == dest_dir / "Factures.exe.new"
    assert result.read_bytes() == payload
    assert api_received[0]["headers"].get("Accept") == "application/octet-stream"
    assert "secret-download-token" in api_received[0]["headers"].get("Authorization", "")
    assert all("Authorization" not in r["headers"] for r in storage_received)


def test_download_deletes_new_file_and_raises_on_sha_mismatch(tmp_path):
    payload = b"exe-bytes-that-do-not-match"
    wrong_digest = "0" * 64

    server, _ = fh.make_server({
        "/assets/1": lambda h: fh.bytes_response(h, 200, payload),
        "/assets/2": lambda h: fh.text_response(h, 200, f"{wrong_digest}  Factures.exe\n"),
    })
    with fh.running(server) as base_url:
        dest_dir = tmp_path / "exe_dir"
        dest_dir.mkdir()
        with pytest.raises(updater.UpdateError, match="[Ss][Hh][Aa]|intégrité|integrite"):
            updater.download(
                exe_asset_url=f"{base_url}/assets/1",
                sha_asset_url=f"{base_url}/assets/2",
                dest_dir=dest_dir,
                token="tok",
            )
    assert not (dest_dir / "Factures.exe.new").exists()


# ── install() preconditions ───────────────────────────────


def test_install_refuses_in_dev_mode(monkeypatch):
    monkeypatch.setattr(paths, "IS_FROZEN", False)
    with pytest.raises(updater.UpdateError, match="développement|developpement"):
        updater.install(port=8000)


def test_install_refuses_when_exe_dir_not_writable(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "IS_FROZEN", True)
    monkeypatch.setattr("sys.executable", str(tmp_path / "Factures.exe"))
    monkeypatch.setattr(updater, "_exe_dir_writable", lambda p: False)
    with pytest.raises(updater.UpdateError, match="écriture|ecriture|permission"):
        updater.install(port=8000)


def test_install_refuses_when_sync_in_progress(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "IS_FROZEN", True)
    monkeypatch.setattr("sys.executable", str(tmp_path / "Factures.exe"))
    monkeypatch.setattr(updater, "_exe_dir_writable", lambda p: True)
    assert sync._lock.acquire(blocking=False), "test setup: lock should be free"
    try:
        with pytest.raises(updater.UpdateError, match="synchronisation"):
            updater.install(port=8000)
    finally:
        sync._lock.release()


def test_install_refuses_when_no_update_available(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "IS_FROZEN", True)
    monkeypatch.setattr("sys.executable", str(tmp_path / "Factures.exe"))
    monkeypatch.setattr(updater, "_exe_dir_writable", lambda p: True)
    monkeypatch.setattr(updater, "check", lambda **k: {
        "current": "2.0.0", "latest": "2.0.0", "available": False,
        "notes": "", "published_at": "", "asset": None,
    })
    with pytest.raises(updater.UpdateError, match="disponible"):
        updater.install(port=8000)


def test_install_backs_up_db_downloads_and_launches_helper(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "IS_FROZEN", True)
    exe_path = tmp_path / "Factures.exe"
    exe_path.write_bytes(b"old-exe-bytes")
    monkeypatch.setattr("sys.executable", str(exe_path))
    monkeypatch.setattr(updater, "_exe_dir_writable", lambda p: True)
    monkeypatch.setattr(updater, "_resolve_token", lambda cfg=None: "tok")

    checkpoint_calls = []
    monkeypatch.setattr(db, "checkpoint", lambda: checkpoint_calls.append(True))

    db_file = paths.db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    db_file.write_bytes(b"sqlite-bytes")

    monkeypatch.setattr(updater, "check", lambda **k: {
        "current": "2.0.0", "latest": "2.0.1", "available": True,
        "notes": "", "published_at": "", "asset": {
            "exe_url": "http://example.invalid/assets/1",
            "sha256_url": "http://example.invalid/assets/2",
        },
    })

    new_exe = tmp_path / "Factures.exe.new"
    new_exe.write_bytes(b"new-exe-bytes")
    download_calls = []

    def fake_download(*, exe_asset_url, sha_asset_url, dest_dir, token):
        download_calls.append(
            {"exe_asset_url": exe_asset_url, "sha_asset_url": sha_asset_url,
             "dest_dir": dest_dir, "token": token}
        )
        return new_exe

    monkeypatch.setattr(updater, "download", fake_download)

    written_scripts = []

    def fake_write_helper(**kwargs):
        p = tmp_path / "update_helper.cmd"
        p.write_text("REM helper", encoding="utf-8")
        written_scripts.append(kwargs)
        return p

    monkeypatch.setattr(updater, "_write_helper_script", fake_write_helper)

    launched = []
    monkeypatch.setattr(updater, "_launch_helper", lambda script_path: launched.append(script_path))

    result = updater.install(port=8123)

    assert checkpoint_calls == [True]
    backups = list(paths.backups_dir().glob("data.db.*.pre-update.bak"))
    assert len(backups) == 1, "install() must back up data.db before touching anything"
    assert download_calls and download_calls[0]["token"] == "tok"
    assert download_calls[0]["exe_asset_url"] == "http://example.invalid/assets/1"
    assert written_scripts and written_scripts[0]["port"] == 8123
    assert launched == [tmp_path / "update_helper.cmd"]
    assert result["ok"] is True
    assert result["version"] == "2.0.1"


# ── helper script contract (pure text, testable on any OS) ─────────────────


def test_build_helper_script_contains_required_contract_pieces():
    script = updater.build_helper_script(
        exe_dir="C:\\Facturo", exe_name="Factures.exe", new_exe_name="Factures.exe.new",
        old_pid=54321, port=8007,
    )
    assert isinstance(script, str) and script.strip()
    lower = script.lower()

    assert "54321" in script, "must wait for the OLD process to exit"
    assert "tasklist" in lower, "must poll for the old PID via tasklist"
    assert "factures.old.exe" in lower, "must rename the current exe aside"
    assert "factures.exe.new" in lower, "must reference the freshly downloaded exe"
    assert "pyinstaller_reset_environment" in lower, "must clear _PYI_* via this env var"
    assert "--port 8007" in script, "must relaunch on the same port"
    assert "--no-browser" in script, "must relaunch without popping a browser tab"
    assert "/api/version" in script, "must health-poll the new process"
    assert "update_failed.txt" in lower, "must record a failure for the app to surface"
    # The rollback path also renames Factures.old.exe -> Factures.exe, so the
    # name must appear at least twice (once to create it, once to restore it).
    assert lower.count("factures.old.exe") >= 2


def test_write_helper_script_creates_cmd_file(tmp_path):
    path = updater._write_helper_script(
        exe_dir=tmp_path, exe_name="Factures.exe", new_exe_name="Factures.exe.new",
        old_pid=999, port=8010,
    )
    assert path == tmp_path / "update_helper.cmd"
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "999" in content
    assert "--port 8010" in content


# ── cleanup_after_update() ────────────────────────────────


def test_cleanup_after_update_is_noop_in_dev_mode(monkeypatch):
    monkeypatch.setattr(paths, "IS_FROZEN", False)
    assert updater.cleanup_after_update() is None


def test_cleanup_after_update_removes_old_exe_and_helper_when_healthy(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "IS_FROZEN", True)
    exe = tmp_path / "Factures.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr("sys.executable", str(exe))
    old_exe = tmp_path / "Factures.old.exe"
    old_exe.write_bytes(b"old")
    helper = tmp_path / "update_helper.cmd"
    helper.write_text("REM", encoding="utf-8")

    result = updater.cleanup_after_update()

    assert result is None
    assert not old_exe.exists()
    assert not helper.exists()


def test_cleanup_after_update_surfaces_failure_message_once_via_status(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "IS_FROZEN", True)
    exe = tmp_path / "Factures.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr("sys.executable", str(exe))
    monkeypatch.setattr(updater, "CONFIG_PATH", tmp_path / "update_config.json")
    failed = tmp_path / "update_failed.txt"
    failed.write_text("La mise à jour a échoué ; retour à la version précédente.", encoding="utf-8")

    cleanup_result = updater.cleanup_after_update()
    assert cleanup_result is not None
    assert "précédente" in cleanup_result["message"] or "échoué" in cleanup_result["message"]
    assert not failed.exists(), "update_failed.txt must be consumed"

    status_first = updater.status()
    assert status_first["update_failed_message"] == cleanup_result["message"]

    status_second = updater.status()
    assert status_second["update_failed_message"] is None, "message must surface only once"


# ── schema guard: sync push refuses when the db is newer than this app ─────


def test_sync_push_refused_when_db_is_newer_than_app(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "sync-guard.db")
    # A throwaway path, never the real sync_config.json, and never a real
    # remote: 127.0.0.1:9 refuses connections instantly, so this test cannot
    # reach any real GitHub endpoint even if the guard under test is missing.
    monkeypatch.setattr(sync, "CONFIG_PATH", tmp_path / "fake_sync_config_for_test.json")
    monkeypatch.setattr(sync, "_base", lambda: tmp_path)

    db.init_db()
    conn = db.get_conn()
    conn.execute(f"PRAGMA user_version = {schema.SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()

    sync.save_config({
        "remote_url": "http://127.0.0.1:9/unreachable/data.git",
        "token": "t",
        "branch": "main",
    })

    with pytest.raises(sync.SyncError, match="jour|récente|recente"):
        sync.push()

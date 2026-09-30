"""« Recevoir » (sync.pull) is destructive: it must not run without its safety net.

The pull resets the working tree onto GitHub's data. The safety copy of
data.db and the removal of SQLite's side files used to swallow OSError, so a
pull could wipe local data with no backup, or leave an old WAL to be replayed
onto the freshly pulled database. No network, no git: the repo, fetch and
reset are faked.
"""

import json
import logging
import os
import sqlite3
import stat
import sys
from types import SimpleNamespace

import pytest

from facturo.core import database as db
from facturo.services import sync


class _FakeRefs(dict):
    def set_symbolic_ref(self, name, target):
        self[name] = target


@pytest.fixture
def pull_env(tmp_path, monkeypatch):
    """A configured sync whose remote has one commit; records every reset."""
    (tmp_path / "data.db").write_bytes(b"local data")
    resets = []
    stamped = []
    monkeypatch.setattr(sync, "_base", lambda: tmp_path)
    monkeypatch.setattr(sync, "_sync_base", lambda: tmp_path)
    monkeypatch.setattr(sync, "_require_config",
                        lambda: {"branch": "main", "remote_url": "https://example.invalid/r", "token": "t"})
    monkeypatch.setattr(sync, "_open_or_init_repo",
                        lambda base, branch: SimpleNamespace(refs=_FakeRefs()))
    monkeypatch.setattr(sync.porcelain, "fetch",
                        lambda repo, url, errstream=None: SimpleNamespace(refs={b"refs/heads/main": b"abc"}))
    monkeypatch.setattr(sync.porcelain, "reset", lambda repo, mode, sha: resets.append(sha))

    def fake_stamp(cfg, action):
        stamped.append(action)
        cfg["last_synced"] = "now"  # the real _stamp updates cfg in place
        return cfg

    monkeypatch.setattr(sync, "_stamp", fake_stamp)
    monkeypatch.setattr(db, "checkpoint", lambda: None)
    monkeypatch.setattr(db, "init_db", lambda: None)
    # The fake repo has no object store; the tree check has its own test below.
    monkeypatch.setattr(sync, "_assert_tree_is_data_only", lambda repo, sha: None, raising=False)
    return SimpleNamespace(base=tmp_path, resets=resets, stamped=stamped)


def _undeletable(path):
    """A side file that cannot be unlinked (a non-empty directory of that name)."""
    path.mkdir()
    (path / "x").write_bytes(b"")


def test_pull_happy_path_backs_up_then_resets(pull_env):
    assert sync.pull()["ok"] is True
    assert pull_env.resets == [b"abc"]
    assert list(pull_env.base.glob("data.db.*.bak"))


@pytest.mark.usefixtures("french")
def test_backup_failure_aborts_pull_before_the_reset(pull_env, caplog):
    (pull_env.base / "data.db").unlink()
    (pull_env.base / "data.db").mkdir()  # exists, but cannot be read as a file

    with caplog.at_level(logging.ERROR), pytest.raises(sync.SyncError) as exc:
        sync.pull()

    assert str(exc.value) == "Sauvegarde de sécurité impossible ; réception annulée."
    assert pull_env.resets == []
    assert "data.db" in caplog.text


def test_wal_that_cannot_be_cleared_aborts_pull_before_the_reset(pull_env, caplog):
    _undeletable(pull_env.base / "data.db-wal")

    with caplog.at_level(logging.ERROR), pytest.raises(sync.SyncError):
        sync.pull()

    assert pull_env.resets == []
    assert "data.db-wal" in caplog.text


@pytest.mark.usefixtures("french")
def test_wal_that_reappears_after_the_reset_is_surfaced(pull_env, monkeypatch, caplog):
    def reset_leaving_a_wal(repo, mode, sha):
        pull_env.resets.append(sha)
        _undeletable(pull_env.base / "data.db-wal")

    monkeypatch.setattr(sync.porcelain, "reset", reset_leaving_a_wal)

    with caplog.at_level(logging.ERROR), pytest.raises(sync.SyncError, match="Redémarrez"):
        sync.pull()

    assert pull_env.resets == [b"abc"]
    assert pull_env.stamped == []  # not reported as a successful pull
    assert "data.db-wal" in caplog.text


# ── Q1 review: guard before destroy, safe config, honest failures ──────

_REAL_STAMP = sync._stamp  # captured before any fixture fakes it


def _repo_with_files(path, names):
    """A real local dulwich repo with one commit holding `names`; returns (repo, sha)."""
    from dulwich import porcelain

    path.mkdir()
    repo = porcelain.init(str(path))
    for name in names:
        (path / name).write_bytes(b"x")
    porcelain.add(repo, [str(path / n) for n in names])
    sha = porcelain.commit(repo, message=b"m", author=b"a <a@a>", committer=b"a <a@a>")
    return repo, sha


def test_pull_refuses_a_remote_that_is_not_data_only_before_touching_anything(
        tmp_path, monkeypatch):
    base = tmp_path / "app"
    base.mkdir()
    (base / "data.db").write_bytes(b"local data")
    repo, sha = _repo_with_files(tmp_path / "remote", ["app.py", "data.db"])
    resets = []
    monkeypatch.setattr(sync, "_base", lambda: base)
    monkeypatch.setattr(sync, "_sync_base", lambda: base)
    monkeypatch.setattr(sync, "_require_config",
                        lambda: {"branch": "main", "remote_url": "https://github.com/u/r.git",
                                 "token": "t"})
    monkeypatch.setattr(sync, "_open_or_init_repo", lambda b, branch: repo)
    monkeypatch.setattr(sync.porcelain, "fetch",
                        lambda r, url, errstream=None: SimpleNamespace(refs={b"refs/heads/main": sha}))
    monkeypatch.setattr(sync.porcelain, "reset", lambda r, mode, s: resets.append(s))
    monkeypatch.setattr(db, "checkpoint", lambda: None)

    with pytest.raises(sync.SyncError, match="app.py"):
        sync.pull()

    assert resets == []
    assert not list(base.glob("data.db.*.bak"))
    assert (base / "data.db").read_bytes() == b"local data"


@pytest.mark.parametrize("url", [
    "https://gitlab.com/u/r",
    "http://github.com/u/r",
    "https://github.com.evil.example/u/r",
    "https://evil.example/github.com/u/r",
    "https://user@github.com/u/r",
    "file:///tmp/r",
])
def test_sync_url_must_be_https_github(url):
    with pytest.raises(sync.SyncError, match="github.com"):
        sync._normalize_url(url)


@pytest.mark.parametrize("url, expected", [
    ("https://github.com/u/r", "https://github.com/u/r.git"),
    ("git@github.com:u/r.git", "https://github.com/u/r.git"),
    ("  https://GitHub.com/u/r.git ", "https://GitHub.com/u/r.git"),
])
def test_sync_url_accepts_github(url, expected):
    assert sync._normalize_url(url) == expected


def test_stored_non_github_url_is_refused_before_the_token_is_used(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "CONFIG_PATH", tmp_path / "sync_config.json")
    sync.save_config({"remote_url": "https://evil.example/r.git", "token": "t", "branch": "main"})
    with pytest.raises(sync.SyncError, match="github.com"):
        sync._require_config()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permission bits")
def test_sync_config_is_written_owner_only(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "CONFIG_PATH", tmp_path / "sync_config.json")
    monkeypatch.setattr(sync, "_use_dpapi", lambda: False)
    sync.save_config({"remote_url": "https://github.com/u/r.git", "token": "t", "branch": "main"})
    assert stat.S_IMODE(os.stat(sync.CONFIG_PATH).st_mode) == 0o600
    assert sync.load_config()["token"] == "t"


def test_sync_token_is_encrypted_at_rest_on_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "CONFIG_PATH", tmp_path / "sync_config.json")
    monkeypatch.setattr(sync, "_use_dpapi", lambda: True)
    monkeypatch.setattr(sync, "_dpapi",
                        lambda data, *, protect: (b"ENC:" + data) if protect else data[4:])
    sync.save_config({"remote_url": "https://github.com/u/r.git", "token": "ghp_secret",
                      "branch": "main"})
    raw = sync.CONFIG_PATH.read_text(encoding="utf-8")
    on_disk = json.loads(raw)
    assert "token" not in on_disk and on_disk["token_dpapi"]
    assert "ghp_secret" not in raw
    assert sync.load_config()["token"] == "ghp_secret"


def test_corrupt_sync_config_is_logged(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(sync, "CONFIG_PATH", tmp_path / "sync_config.json")
    sync.CONFIG_PATH.write_text("{nope", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert sync.load_config() is None
    assert "sync_config.json" in caplog.text


def test_disconnect_reports_a_config_it_cannot_delete(tmp_path, monkeypatch):
    stuck = tmp_path / "sync_config.json"
    _undeletable(stuck)  # a non-empty directory: unlink() fails
    monkeypatch.setattr(sync, "CONFIG_PATH", stuck)
    with pytest.raises(sync.SyncError):
        sync.disconnect()


def test_failure_after_the_reset_names_the_backup(pull_env, monkeypatch):
    def broken_init():
        raise RuntimeError("disk full")

    monkeypatch.setattr(db, "init_db", broken_init)

    with pytest.raises(sync.SyncError) as exc:
        sync.pull()

    backup = next(pull_env.base.glob("data.db.*.bak"))
    assert backup.name in str(exc.value)
    assert "temporaires" not in str(exc.value)
    assert pull_env.stamped == []


def test_wal_failure_after_the_reset_names_the_backup(pull_env, monkeypatch):
    def reset_leaving_a_wal(repo, mode, sha):
        pull_env.resets.append(sha)
        _undeletable(pull_env.base / "data.db-wal")

    monkeypatch.setattr(sync.porcelain, "reset", reset_leaving_a_wal)
    with pytest.raises(sync.SyncError) as exc:
        sync.pull()
    assert next(pull_env.base.glob("data.db.*.bak")).name in str(exc.value)


@pytest.mark.usefixtures("french")
def test_pull_aborts_when_the_checkpoint_stays_busy(pull_env, monkeypatch):
    def busy():
        raise db.DatabaseBusyError("occupée")

    monkeypatch.setattr(db, "checkpoint", busy)
    with pytest.raises(sync.SyncError, match="occupée"):
        sync.pull()
    assert pull_env.resets == []


def _raise_oserror(cfg):
    raise OSError("read-only")


def test_completed_pull_survives_a_config_that_cannot_be_saved(pull_env, monkeypatch, caplog):
    monkeypatch.setattr(sync, "_stamp", _REAL_STAMP)
    monkeypatch.setattr(sync, "save_config", _raise_oserror)

    with caplog.at_level(logging.WARNING):
        result = sync.pull()

    assert result["ok"] is True
    assert result["warning"]
    assert "sync_config" in caplog.text


# ── db.checkpoint must never report success on a partial checkpoint ────


@pytest.fixture
def wal_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "data.db")
    monkeypatch.setattr(db, "CHECKPOINT_BUSY_TIMEOUT_MS", 10, raising=False)
    monkeypatch.setattr(db, "_sleep", lambda s: None, raising=False)
    db.init_db()
    with db.transaction() as conn:
        conn.execute("INSERT INTO clients (ref, prefix, nom) VALUES ('r', 'p', 'n')")
    return tmp_path


def test_checkpoint_raises_when_a_reader_keeps_it_busy(wal_db):
    reader = sqlite3.connect(str(wal_db / "data.db"))
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM clients").fetchall()  # holds a WAL snapshot
    # A write newer than that snapshot cannot be checkpointed while it lives.
    with db.transaction() as conn:
        conn.execute("INSERT INTO clients (ref, prefix, nom) VALUES ('r2', 'p', 'n')")
    try:
        with pytest.raises(db.DatabaseBusyError):
            db.checkpoint()
    finally:
        reader.close()


def test_checkpoint_succeeds_when_nothing_holds_the_wal(wal_db):
    db.checkpoint()
    wal = wal_db / "data.db-wal"
    assert not wal.exists() or wal.stat().st_size == 0

"""Optional GitHub sync for the app's data, so the user can work on several PCs.

Single-user, one-device-at-a-time model — there is NO merging, because the
SQLite database is binary and cannot be merged:

  * Envoyer (push)  → this device's data becomes the source of truth on GitHub.
  * Recevoir (pull) → GitHub's data replaces this device's data.

What is synced: data.db, output/ (generated invoices), scans/ (uploaded scans),
paiements/ (imported payment PDFs) and company_logo.png. The program, backups and
the secret tokens are never committed (see GITIGNORE).

Implemented with dulwich (pure-Python git) so Git need not be installed on each
PC. Authentication uses a GitHub token injected into the remote URL at call time,
so the token lives only in sync_config.json (gitignored, owner-only, encrypted with
DPAPI on Windows), never in .git/config. Only https://github.com/ remotes are
accepted, so the token is never sent to another host.
"""

import io
import json
import logging
import shutil
import socket
from datetime import datetime
from pathlib import Path
from threading import Lock
from urllib.parse import quote, urlparse

from dulwich import porcelain
from dulwich.repo import Repo

from facturo import paths
from facturo.core import database as db
from facturo.core import secret_store

CONFIG_PATH = paths.app_dir() / "sync_config.json"

# Files/folders that make up "the data" — copied between app_dir and the sync
# workdir in dev mode, and added directly from app_dir in the installed app.
_DATA_ENTRIES = ("data.db", "company_logo.png", "output", "scans", "paiements")

# Track only data — never the exe, the secret token, or SQLite's side files.
GITIGNORE = """\
# Facturo sync — track only data, never the program or secrets.
/*
!/.gitignore
!/data.db
!/company_logo.png
!/output/
!/scans/
!/paiements/
"""

log = logging.getLogger(__name__)

_AUTHOR = b"Facturo Sync <sync@facturo.local>"
_lock = Lock()  # serialize sync operations (they rewrite data.db wholesale)


class SyncError(Exception):
    """A user-facing sync failure; the message is shown as-is in the UI."""


# ── Configuration ────────────────────────────────────────


def _base() -> Path:
    return paths.app_dir()


def _sync_base() -> Path:
    """Directory the sync git repo lives in.

    Installed app: the exe folder itself. Development: an isolated subfolder of
    data/, because data/ sits inside the source checkout and must never become
    part of the code repository's history.
    """
    base = _base()
    if not paths.IS_FROZEN:
        return base / ".sync_data"
    return base


def _copy_into_sync(base: Path, sync_base: Path) -> None:
    """Dev mode only: mirror the live data files into the sync workdir before commit."""
    for name in _DATA_ENTRIES:
        src, dst = base / name, sync_base / name
        if not src.exists():
            continue
        if src.is_dir():
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


def _copy_from_sync(sync_base: Path, base: Path) -> None:
    """Dev mode only: apply the freshly pulled data files back onto the live app_dir."""
    for name in _DATA_ENTRIES:
        src, dst = sync_base / name, base / name
        if not src.exists():
            continue
        if src.is_dir():
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


# The token at rest: owner-only file everywhere, DPAPI-encrypted on Windows
# ("token_dpapi"); callers always see a plaintext "token" key in memory.
_DPAPI_ENTROPY = b"facturo-sync-token-v1"
_DPAPI_DESCRIPTION = "Facturo sync token"


def _use_dpapi() -> bool:
    return secret_store.use_dpapi()


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    return secret_store.dpapi(data, protect=protect, entropy=_DPAPI_ENTROPY,
                              description=_DPAPI_DESCRIPTION)


def load_config() -> dict | None:
    """The sync config with a plaintext "token", or None if absent/unreadable.

    On Windows a legacy plaintext token found on disk is re-saved encrypted.
    """
    if not CONFIG_PATH.exists():
        return None
    try:
        stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        log.warning("%s illisible ; configuration de synchronisation ignorée", CONFIG_PATH.name)
        return None
    if not isinstance(stored, dict):
        log.warning("%s invalide ; configuration de synchronisation ignorée", CONFIG_PATH.name)
        return None
    cfg = {k: v for k, v in stored.items() if k != "token_dpapi"}
    encrypted = stored.get("token_dpapi")
    if isinstance(encrypted, str) and encrypted:
        try:
            cfg["token"] = _dpapi(secret_store.decode_blob(encrypted), protect=False).decode("utf-8")
        except (OSError, ValueError, UnicodeDecodeError):
            log.warning("Jeton de synchronisation illisible sur ce compte Windows ; ignoré")
    elif _use_dpapi() and cfg.get("token"):
        try:
            save_config(cfg)
        except OSError:
            log.warning("Chiffrement du jeton de synchronisation impossible pour l'instant")
    return cfg


def save_config(cfg: dict) -> None:
    """Persist the config owner-only; on Windows the token is DPAPI-encrypted."""
    stored = {k: v for k, v in cfg.items() if k not in ("token", "token_dpapi")}
    token = cfg.get("token")
    if isinstance(token, str) and token and _use_dpapi():
        stored["token_dpapi"] = secret_store.encode_blob(
            _dpapi(token.encode("utf-8"), protect=True))
    elif token:
        stored["token"] = token
    secret_store.write_private_json(CONFIG_PATH, stored)


def is_configured() -> bool:
    cfg = load_config()
    return bool(cfg and cfg.get("remote_url") and cfg.get("token"))


def status() -> dict:
    cfg = load_config() or {}
    return {
        "configured": is_configured(),
        "remote_url": cfg.get("remote_url", ""),
        "branch": cfg.get("branch", "main"),
        "last_synced": cfg.get("last_synced"),
        "last_action": cfg.get("last_action"),
    }


def _require_config() -> dict:
    cfg = load_config()
    if not (cfg and cfg.get("remote_url") and cfg.get("token")):
        raise SyncError("La synchronisation n'est pas configurée.")
    # The token is injected into this URL: never send it anywhere but GitHub,
    # even if the stored config was edited by hand.
    _assert_github_url(cfg["remote_url"])
    return cfg


# ── URL / repo helpers ───────────────────────────────────

_MSG_GITHUB_ONLY = ("Adresse du dépôt refusée : utilisez un dépôt GitHub "
                    "(https://github.com/propriétaire/dépôt).")


def _assert_github_url(url: str) -> None:
    """Only https://github.com/<path> may receive the sync token."""
    p = urlparse(url)
    if (p.scheme.lower() != "https" or (p.hostname or "").lower() != "github.com"
            or p.username or p.password or p.port or not p.path.strip("/")):
        raise SyncError(_MSG_GITHUB_ONLY)


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("git@github.com:"):  # accept SSH form, store as HTTPS
        url = "https://github.com/" + url.split(":", 1)[1]
    if not url:
        raise SyncError("URL du dépôt requise.")
    _assert_github_url(url)
    if not url.endswith(".git"):
        url += ".git"
    return url


def _authed_url(remote_url: str, token: str) -> str:
    """Inject the token as URL userinfo so push/fetch authenticate over HTTPS."""
    p = urlparse(remote_url)
    return f"{p.scheme}://{quote(token, safe='')}@{p.netloc}{p.path}"


def _open_or_init_repo(base: Path, branch: str) -> Repo:
    if (base / ".git").exists():
        repo = Repo(str(base))
    else:
        repo = porcelain.init(str(base))
    # Rewritten every time so a repo created by an older version picks up newly
    # synced folders (paiements/ was added in v2).
    gi = base / ".gitignore"
    if not gi.exists() or gi.read_text(encoding="utf-8") != GITIGNORE:
        gi.write_text(GITIGNORE, encoding="utf-8")
    # Always work on the configured branch so commits and the push refspec agree
    # (dulwich's default HEAD branch name varies between versions).
    repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/" + branch.encode())
    return repo


def _has_staged_changes(repo: Repo) -> bool:
    st = porcelain.status(repo)
    staged = st.staged if isinstance(st.staged, dict) else {}
    return any(staged.get(k) for k in ("add", "delete", "modify"))


def _has_commits(repo: Repo) -> bool:
    try:
        return repo.head() is not None
    except KeyError:
        return False


def _is_ancestor(repo: Repo, ancestor: bytes, head: bytes) -> bool:
    """True if `ancestor` is reachable from `head` (i.e. push is fast-forward).

    Both commits must already be in the local object store; the caller fetches
    the remote first so its commits are present.
    """
    if ancestor == head:
        return True
    store = repo.object_store
    seen: set[bytes] = set()
    stack = [head]
    while stack:
        sha = stack.pop()
        if sha == ancestor:
            return True
        if sha in seen:
            continue
        seen.add(sha)
        try:
            commit = store[sha]
        except KeyError:
            continue
        stack.extend(getattr(commit, "parents", []))
    return False


def _clear_wal(base: Path) -> None:
    """Drop SQLite side files so a freshly checked-out data.db opens cleanly.

    Raises OSError when one cannot be removed: an old WAL left next to the new
    data.db would be replayed onto it, so the caller must not carry on as if
    the pull were clean.
    """
    for suffix in ("-wal", "-shm", "-journal"):
        f = base / ("data.db" + suffix)
        try:
            if f.exists():
                f.unlink()
        except OSError:
            log.error("Impossible de supprimer %s", f, exc_info=True)
            raise


def _backup_db(base: Path) -> Path | None:
    """Copy the current db aside before a destructive pull, as a safety net.

    Returns the backup path (None when there was no local db). A pull without
    this copy could wipe local data with no way back, so a failure aborts the
    pull instead of being ignored.
    """
    src = base / "data.db"
    if not src.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = base / f"data.db.{stamp}.bak"
    try:
        target.write_bytes(src.read_bytes())
    except OSError as e:
        log.error("Sauvegarde de %s impossible avant réception", src, exc_info=True)
        raise SyncError("Sauvegarde de sécurité impossible ; réception annulée.") from e
    return target


def _checkpoint() -> None:
    """Flush the WAL; a database kept busy aborts the sync before anything moves."""
    try:
        db.checkpoint()
    except db.DatabaseBusyError as e:
        raise SyncError(f"{e} Synchronisation annulée.") from e


_MSG_STAMP_FAILED = ("Synchronisation terminée, mais la date de dernière synchronisation "
                     "n'a pas pu être enregistrée.")


def _stamp(cfg: dict, action: str) -> dict:
    """Record the completed sync. The sync itself is done: a config that cannot
    be saved is logged and reported as a warning, never turned into a failure."""
    cfg["last_synced"] = datetime.now().isoformat(timespec="seconds")
    cfg["last_action"] = action
    try:
        save_config(cfg)
    except OSError:
        log.warning("Enregistrement de %s impossible après « %s »", CONFIG_PATH.name, action,
                    exc_info=True)
        cfg["_stamp_warning"] = _MSG_STAMP_FAILED
    return cfg


def _result(cfg: dict) -> dict:
    result = {"ok": True, "last_synced": cfg.get("last_synced")}
    if cfg.get("_stamp_warning"):
        result["warning"] = cfg["_stamp_warning"]
    return result


# ── Public operations ────────────────────────────────────


# Only these top-level entries may exist in a sync repo. Anything else means the
# repo is being used for something other than this app's data (most importantly,
# the source-code repo) — connecting would let a pull dump those files next to the
# exe and overwrite the database, so we refuse.
_ALLOWED_TREE = {b".gitignore", b"data.db", b"company_logo.png", b"output", b"scans", b"paiements"}


def _assert_remote_is_data_only(repo: Repo, authed: str, branch: str) -> None:
    try:
        refs = porcelain.ls_remote(authed)
    except Exception as e:  # noqa: BLE001
        raise SyncError(f"Connexion au dépôt impossible : {_short(e)}") from e

    head_ref = b"refs/heads/" + branch.encode()
    if head_ref not in refs and b"HEAD" not in refs:
        return  # empty repo — safe to adopt; the first Envoyer will populate it

    fr = porcelain.fetch(repo, authed, errstream=io.BytesIO())
    sha = fr.refs.get(head_ref) or fr.refs.get(b"HEAD")
    if not sha:
        return
    _assert_tree_is_data_only(repo, sha)


def _assert_tree_is_data_only(repo: Repo, sha: bytes) -> None:
    """Refuse a fetched commit whose top level holds anything but app data."""
    commit = repo.object_store[sha]
    tree = repo.object_store[commit.tree]
    extra = [e.path.decode("utf-8", "replace") for e in tree.items()
             if e.path not in _ALLOWED_TREE]
    if extra:
        preview = ", ".join(extra[:5]) + ("…" if len(extra) > 5 else "")
        raise SyncError(
            f"Ce dépôt contient déjà d'autres fichiers ({preview}). "
            "Utilisez un dépôt GitHub vide et privé, créé uniquement pour les "
            "données de Factures — jamais le dépôt du code source."
        )


def configure(remote_url: str, token: str, branch: str = "main") -> dict:
    with _lock:
        sync_base = _sync_base()
        sync_base.mkdir(parents=True, exist_ok=True)
        if not (token or "").strip():
            raise SyncError("Jeton GitHub requis.")
        remote_url = _normalize_url(remote_url)
        branch = (branch or "main").strip() or "main"

        repo = _open_or_init_repo(sync_base, branch)
        # Validate URL + token AND refuse a repo that already holds other files.
        _assert_remote_is_data_only(repo, _authed_url(remote_url, token), branch)

        save_config({
            "remote_url": remote_url,
            "branch": branch,
            "token": token,
            "last_synced": None,
            "last_action": None,
        })
        return status()


def push() -> dict:
    """Envoyer — commit local data and push it to GitHub (never force)."""
    # Schema guard: refuse push if db is newer than app version
    if db.is_newer_than_app():
        raise SyncError(
            "Cette base de données a été créée par une version plus récente de "
            "Factures. Mettez à jour l'application avant d'envoyer."
        )

    with _lock:
        base = _base()
        sync_base = _sync_base()
        cfg = _require_config()
        branch = cfg["branch"]
        repo = _open_or_init_repo(sync_base, branch)

        _checkpoint()  # flush WAL into data.db so the committed file is whole
        if sync_base != base:
            _copy_into_sync(base, sync_base)

        porcelain.add(repo, [
            str(sync_base / "data.db"),
            str(sync_base / "company_logo.png"),
            str(sync_base / "output"),
            str(sync_base / "scans"),
            str(sync_base / "paiements"),
            str(sync_base / ".gitignore"),
        ])
        if _has_staged_changes(repo) or not _has_commits(repo):
            msg = f"Sync depuis {socket.gethostname()} — {datetime.now():%Y-%m-%d %H:%M}"
            porcelain.commit(repo, message=msg.encode(), author=_AUTHOR, committer=_AUTHOR)

        authed = _authed_url(cfg["remote_url"], cfg["token"])
        ref = f"refs/heads/{branch}"
        branch_ref = b"refs/heads/" + branch.encode()

        # Pre-flight: pull down remote state and refuse if it has commits we don't
        # have (another device pushed). This gives a clear "Recevoir first" message
        # instead of relying on the git backend's raw rejection text, and never
        # force-pushes — so a stale device can't silently overwrite newer data.
        try:
            fr = porcelain.fetch(repo, authed, errstream=io.BytesIO())
        except Exception as e:  # noqa: BLE001
            raise SyncError(f"Envoi impossible (connexion) : {_short(e)}") from e
        remote_sha = fr.refs.get(branch_ref)
        if remote_sha and not _is_ancestor(repo, remote_sha, repo.head()):
            raise SyncError(
                "Le dépôt distant contient des données plus récentes "
                "(un autre appareil a synchronisé). Cliquez « Recevoir » avant d'envoyer."
            )

        err = io.BytesIO()
        try:
            result = porcelain.push(repo, authed, f"{ref}:{ref}", errstream=err)
        except Exception as e:  # noqa: BLE001
            raise SyncError(_friendly_push_error(e, err)) from e
        _check_push_result(result, ref)

        return _result(_stamp(cfg, "push"))


def pull() -> dict:
    """Recevoir — replace local data with the GitHub version (destructive)."""
    with _lock:
        base = _base()
        sync_base = _sync_base()
        cfg = _require_config()
        branch = cfg["branch"]
        repo = _open_or_init_repo(sync_base, branch)

        try:
            result = porcelain.fetch(
                repo, _authed_url(cfg["remote_url"], cfg["token"]), errstream=io.BytesIO()
            )
        except Exception as e:  # noqa: BLE001
            raise SyncError(f"Réception impossible : {_short(e)}") from e

        sha = result.refs.get(b"refs/heads/" + branch.encode())
        if not sha:
            raise SyncError(
                "Le dépôt distant est vide. Cliquez « Envoyer » depuis l'appareil "
                "qui possède déjà les données."
            )

        # Same guard as configure(): a remote that has since gained anything but
        # app data must be refused BEFORE the backup and the destructive reset.
        _assert_tree_is_data_only(repo, sha)

        _checkpoint()                # flush the WAL first so the safety copy is complete
        backup = _backup_db(base)    # safety copy before we overwrite anything
        # Checkpointed, so the side files hold nothing the backup lacks. If they
        # cannot be removed now, they could not be after the reset either — stop
        # while local data is still untouched.
        try:
            _clear_wal(sync_base)
        except OSError as e:
            raise SyncError("Fichiers temporaires de la base impossibles à supprimer ; "
                            "réception annulée. Redémarrez Facturo puis réessayez.") from e

        local_ref = b"refs/heads/" + branch.encode()
        repo.refs[local_ref] = sha
        repo.refs.set_symbolic_ref(b"HEAD", local_ref)
        porcelain.reset(repo, "hard", sha)

        _finish_pull(base, sync_base, backup)
        return _result(_stamp(cfg, "pull"))


def _backup_hint(backup: Path | None) -> str:
    if backup is None:
        return ""
    return f" Votre base précédente est sauvegardée dans « {backup.name} » ({backup.parent})."


def _finish_pull(base: Path, sync_base: Path, backup: Path | None) -> None:
    """Everything after the destructive reset. Nothing here can be undone, so a
    failure must tell the user the pull is not clean and where their backup is."""
    hint = _backup_hint(backup)

    def clear_wal(where: Path) -> None:
        # Old WAL must not be replayed onto the new db.
        try:
            _clear_wal(where)
        except OSError as e:
            raise SyncError("Données reçues, mais les fichiers temporaires de la base n'ont "
                            "pas pu être supprimés. Redémarrez Facturo puis cliquez de nouveau "
                            "sur « Recevoir »." + hint) from e

    def run(step) -> None:
        try:
            step()
        except Exception as e:
            log.exception("Réception : mise en place des données reçues impossible")
            raise SyncError("Données reçues, mais leur mise en place a échoué "
                            f"({_short(e)}). Redémarrez Facturo puis cliquez de nouveau sur "
                            "« Recevoir »." + hint) from e

    clear_wal(sync_base)
    if sync_base != base:
        run(lambda: _copy_from_sync(sync_base, base))
        clear_wal(base)
    # The database just pulled was written by whichever version the other
    # device runs, which may predate a table this one needs. Migrating here
    # stops a pull leaving the app running against a schema missing something
    # — and init_db is idempotent, so a same-version pull pays nothing for it.
    run(db.init_db)


def disconnect() -> dict:
    """Forget the sync configuration. Local data and history are left intact."""
    with _lock:
        try:
            CONFIG_PATH.unlink(missing_ok=True)
        except OSError as e:
            log.error("Suppression de %s impossible", CONFIG_PATH, exc_info=True)
            raise SyncError("Impossible de supprimer la configuration de synchronisation "
                            f"({CONFIG_PATH.name}). Fermez les autres programmes qui "
                            "l'utilisent puis réessayez.") from e
        return {"ok": True}


# ── Error formatting ─────────────────────────────────────


def _short(e: Exception) -> str:
    s = str(e).strip() or e.__class__.__name__
    return s if len(s) < 200 else s[:200] + "…"


def _friendly_push_error(e: Exception, err: io.BytesIO) -> str:
    detail = (err.getvalue().decode("utf-8", "replace") + " " + str(e)).lower()
    if "401" in detail or "unauthor" in detail or "403" in detail:
        return "Jeton GitHub refusé. Vérifiez le jeton et ses autorisations."
    if "non-fast-forward" in detail or "fast forward" in detail:
        return ("Le dépôt distant contient des données plus récentes. "
                "Cliquez « Recevoir » avant d'envoyer.")
    return f"Envoi impossible : {_short(e)}"


def _check_push_result(result, ref: str) -> None:
    ref_status = getattr(result, "ref_status", None) or {}
    err = ref_status.get(ref.encode())
    if err:
        low = str(err).lower()
        if "fast" in low and "forward" in low:
            raise SyncError(
                "Le dépôt distant contient des données plus récentes. "
                "Cliquez « Recevoir » avant d'envoyer."
            )
        raise SyncError(f"Envoi refusé : {err}")

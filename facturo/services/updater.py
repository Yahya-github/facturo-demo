"""In-app updates from GitHub Releases (private `facturo-releases` repo, separate from the source).

Flow: check() lists releases with the client's read-only token and picks the
highest eligible semver tag; install() backs up data.db, downloads the new exe
next to the running one, verifies its SHA-256, writes a small Windows helper
script (update_helper.cmd) and launches it detached. The /api/updates/install
endpoint then exits the app; the helper swaps the files, starts the new exe,
health-checks it and rolls back to the previous exe if it never answers.

Security rules:
  * the token is only ever sent to api.github.com (or a loopback test server),
    never logged, never returned by any endpoint, never forwarded on redirects;
  * only HTTPS is accepted, except plain HTTP to 127.0.0.1/localhost (tests);
  * downloads are size-capped and SHA-256 verified before they get the
    `Factures.exe.new` name the helper swaps in;
  * update_config.json is written owner-only (0600) where the OS supports it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from facturo import paths
from facturo.core import secret_store
from facturo.services import sync

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────

# Releases live in a separate private repo that holds only the published exe,
# its .sha256 and notes: the client's read-only token can never read source.
# PLACEHOLDERS: a fork must set these to its own GitHub user/org and releases
# repo (and RELEASES_REPO in .github/workflows/release.yml to match).
RELEASES_OWNER = "your-github-user"
RELEASES_REPO = "facturo-releases"
# Aliases other modules and the tests use; they must always name the
# releases repo, never the source repo.
GITHUB_OWNER = RELEASES_OWNER
GITHUB_REPO = RELEASES_REPO
# Read at call time (never bound as a default argument) so the test suite can
# point it at a dead loopback port: no test can ever reach GitHub.
GITHUB_API_BASE = "https://api.github.com"
CACHE_TTL_SECONDS = 3600

CONFIG_PATH = paths.app_dir() / "update_config.json"   # never synced, never logged

EXE_NAME = "Factures.exe"
NEW_EXE_NAME = "Factures.exe.new"
OLD_EXE_NAME = "Factures.old.exe"
FAILED_EXE_NAME = "Factures.failed.exe"
HELPER_NAME = "update_helper.cmd"
FAILED_FILE_NAME = "update_failed.txt"
NEW_PID_FILE_NAME = "update_new_pid.txt"
SHA_ASSET_NAME = "Factures.exe.sha256"

# The exe is ~100 MB; anything far beyond that is not ours.
MAX_EXE_BYTES = 400 * 1024 * 1024
MAX_SHA_BYTES = 4 * 1024
MAX_API_BYTES = 8 * 1024 * 1024
HTTP_TIMEOUT_SECONDS = 20
_CHUNK = 1024 * 1024

# Hosts allowed to receive the token. Loopback may use plain HTTP so the test
# suite's fake servers work; nothing else is ever contacted over HTTP.
_TOKEN_HOSTS = frozenset({"api.github.com"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# A plain file name: never "." or "..", never hidden (leading dot).
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$")
_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-rc(\d+))?$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_SHAPE = re.compile(r"^[A-Za-z0-9_\-.]{1,255}$")

_MSG_NO_TOKEN = "Aucun jeton configuré. Ajoutez un jeton GitHub en lecture seule dans Paramètres."
_MSG_REFUSED = "Jeton GitHub refusé ou expiré."
_MSG_NOT_FOUND = "Dépôt introuvable ou jeton sans accès."
_MSG_NETWORK = "Connexion impossible. Vérifiez votre connexion internet."
_MSG_INSECURE = "Adresse de téléchargement refusée (connexion non sécurisée)."
_MSG_TOO_BIG = "Fichier de mise à jour anormalement volumineux ; mise à jour annulée."

# update_helper.cmd writes an ASCII code (its body must stay ASCII so every
# Windows code page reads it the same); the app turns it into French here.
_ROLLBACK_MESSAGES = {
    "HEALTH_CHECK_FAILED": "La mise à jour a échoué : la nouvelle version n'a pas démarré. "
                           "Retour à la version précédente.",
    "ACTIVATE_NEW_FAILED": "La mise à jour a échoué : le nouveau programme n'a pas pu être mis "
                           "en place. Retour à la version précédente.",
    "RENAME_CURRENT_FAILED": "La mise à jour a échoué : le programme était verrouillé "
                             "(antivirus ?). Aucune modification n'a été faite.",
    "OLD_PROCESS_STILL_RUNNING": "La mise à jour a échoué : l'ancienne version ne s'est pas "
                                 "fermée. Aucune modification n'a été faite.",
}
_ROLLBACK_DEFAULT = "La mise à jour a échoué. Retour à la version précédente."


class UpdateError(Exception):
    """A user-facing update failure; the message is shown as-is in the UI."""


# ── Module state: cache and last failure message ──────────────

_cache: dict[str, Any] = {}
_last_update_failure: str | None = None
# Held for the whole of install() and download() (re-entrant: install calls
# download on the same thread); a concurrent caller is refused immediately.
_install_lock = threading.RLock()
_MSG_BUSY = "Une mise à jour est déjà en cours."


# ── Config management ────────────────────────────────────────

# ── Token at rest: DPAPI on Windows ──────────────────────────
# On Windows the token is stored as "token_dpapi" (base64 of a
# CryptProtectData blob bound to the current Windows user), so a copied
# update_config.json is useless elsewhere. Other OSes keep the plaintext
# "token" in a 0600 file. load_config()/save_config() convert transparently:
# callers always see a plaintext "token" key in memory, never on disk.

_DPAPI_ENTROPY = b"facturo-update-token-v1"
_DPAPI_DESCRIPTION = "Facturo update token"


def _use_dpapi() -> bool:
    return secret_store.use_dpapi()


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    return secret_store.dpapi(data, protect=protect, entropy=_DPAPI_ENTROPY,
                              description=_DPAPI_DESCRIPTION)


def _protect_token(token: str) -> str:
    return secret_store.encode_blob(_dpapi(token.encode("utf-8"), protect=True))


def _unprotect_token(value: str) -> str:
    return _dpapi(secret_store.decode_blob(value), protect=False).decode("utf-8")


def _read_config_file() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("update_config.json illisible ; configuration ignorée")
        return {}
    return cfg if isinstance(cfg, dict) else {}


def _write_config_file(cfg: dict) -> None:
    """Atomic write, owner-only (0600) where the OS supports it."""
    secret_store.write_private_json(CONFIG_PATH, cfg)


def load_config() -> dict:
    """Update config with a plaintext "token" in memory; {} if absent/corrupt.

    Never raises. On Windows a legacy plaintext token found on disk is
    re-saved encrypted (transparent migration).
    """
    stored = _read_config_file()
    cfg = {k: v for k, v in stored.items() if k != "token_dpapi"}
    encrypted = stored.get("token_dpapi")
    if isinstance(encrypted, str) and encrypted:
        try:
            cfg["token"] = _unprotect_token(encrypted)
        except (OSError, ValueError, UnicodeDecodeError):
            # Another Windows user/PC, or a damaged file: ask for the token again.
            logger.warning("Jeton de mise à jour illisible sur ce compte Windows ; ignoré")
            cfg.pop("token", None)
    elif _use_dpapi() and _clean_token(stored.get("token")):
        try:
            save_config(cfg)
        except OSError:
            logger.warning("Chiffrement du jeton de mise à jour impossible pour l'instant")
    return cfg


def save_config(cfg: dict) -> None:
    """Persist the config; on Windows the token is encrypted with DPAPI."""
    stored = {k: v for k, v in cfg.items() if k not in ("token", "token_dpapi")}
    token = _clean_token(cfg.get("token"))
    if token and _use_dpapi():
        stored["token_dpapi"] = _protect_token(token)
    elif token:
        stored["token"] = token
    _write_config_file(stored)


def is_configured() -> bool:
    """True if a token is resolvable."""
    return bool(_resolve_token(load_config()))


def _clean_token(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _resolve_token(cfg: dict | None = None) -> str | None:
    """The update token, else the sync token as a fallback, else None."""
    if cfg is None:
        cfg = load_config()
    token = _clean_token(cfg.get("token"))
    if token:
        return token
    # Through the module object so tests can monkeypatch sync.load_config.
    sync_cfg = sync.load_config() or {}
    return _clean_token(sync_cfg.get("token"))


def set_config(*, token: str | None = None, include_prereleases: bool | None = None) -> dict:
    """Merge onto the existing config, validate it against GitHub, persist it.

    An empty token removes the stored one (the sync token is then used, if
    any). Raises UpdateError and persists nothing if validation fails.
    """
    candidate = dict(load_config())
    if token is not None:
        token = token.strip()
        if not token:
            candidate.pop("token", None)
        elif not _TOKEN_SHAPE.match(token):
            raise UpdateError("Jeton invalide : collez uniquement le jeton GitHub, sans espace.")
        else:
            candidate["token"] = token
    if include_prereleases is not None:
        candidate["include_prereleases"] = bool(include_prereleases)

    check(token=_resolve_token(candidate), force=True,
          include_prereleases=bool(candidate.get("include_prereleases", False)))

    save_config(candidate)
    reset_cache()
    return status(consume_failure=False)


_failure_lock = threading.Lock()


def status(*, consume_failure: bool = True) -> dict:
    """Current update status. Never contains the token.

    The last update-failure message is surfaced exactly once: the status
    endpoint consumes it (under a lock, so two polls cannot both show or both
    miss it); other callers, like set_config(), only peek at it.
    """
    global _last_update_failure
    cfg = load_config()
    with _failure_lock:
        failure = _last_update_failure
        if consume_failure:
            _last_update_failure = None
    return {
        "current": current_version(),
        "configured": bool(_resolve_token(cfg)),
        "include_prereleases": bool(cfg.get("include_prereleases", False)),
        "last_check": _cache.get("checked_at"),
        "update_failed_message": failure,
    }


# ── Version parsing and comparison ───────────────────────────

def parse_version(tag: str) -> tuple:
    """Sortable key for `X.Y.Z` / `X.Y.Z-rcN` (leading v tolerated).

    A final release sorts after all of its release candidates; rc numbers
    compare numerically (rc9 < rc10).
    """
    m = _SEMVER.match((tag or "").strip())
    if not m:
        raise ValueError(f"Version invalide : {tag!r}")
    major, minor, patch, rc = m.groups()
    rc_key = (0, int(rc)) if rc is not None else (1, 0)
    return (int(major), int(minor), int(patch), rc_key)


def compare_versions(a: str, b: str) -> int:
    """-1 / 0 / 1. Raises ValueError if either side is not a valid version."""
    ka, kb = parse_version(a), parse_version(b)
    return (ka > kb) - (ka < kb)


def is_prerelease_tag(tag: str) -> bool:
    """True for `...-rcN` tags (v prefix tolerated)."""
    m = _SEMVER.match((tag or "").strip())
    return bool(m and m.group(4) is not None)


def current_version() -> str:
    """The running app version, read live (tests monkeypatch it)."""
    from facturo import version as version_module
    return version_module.__version__


# ── Release selection ────────────────────────────────────────

def select_release(releases: list[dict], include_prereleases: bool) -> dict | None:
    """Highest-versioned eligible release: never drafts, prereleases on request."""
    best, best_key = None, None
    for rel in releases or []:
        if not isinstance(rel, dict) or rel.get("draft"):
            continue
        if rel.get("prerelease") and not include_prereleases:
            continue
        try:
            key = parse_version(str(rel.get("tag_name", "")))
        except ValueError:
            continue
        if best_key is None or key > best_key:
            best, best_key = rel, key
    return best


# ── HTTP layer ──────────────────────────────────────────────

class _InsecureURL(urllib.error.URLError):
    """A URL (or redirect target) the updater refuses to contact."""


def _url_allowed(url: str, *, carries_token: bool) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme == "http":
        return host in _LOOPBACK_HOSTS
    if parts.scheme != "https" or not host:
        return False
    if carries_token:
        return host in _TOKEN_HOSTS or host in _LOOPBACK_HOSTS
    return True


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follows redirects to HTTPS only and never forwards the Authorization header.

    GitHub answers an asset download with a 302 to a signed storage URL on
    another host; that URL rejects (and must never see) the token.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _url_allowed(newurl, carries_token=False):
            raise _InsecureURL("redirect target refused")
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.remove_header("Authorization")
        return new


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except (ImportError, OSError):  # fall back to the OS certificate store
        return ssl.create_default_context()


def _open(url: str, *, token: str | None, accept: str):
    """Open `url`; the token rides in an unredirected header (first hop only)."""
    if not _url_allowed(url, carries_token=bool(token)):
        raise _InsecureURL("url refused")
    req = urllib.request.Request(url, headers={
        "Accept": accept,
        "User-Agent": f"Facturo-updater/{current_version()}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    if token:
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=_ssl_context()), _SafeRedirectHandler,
    )
    return opener.open(req, timeout=HTTP_TIMEOUT_SECONDS)


def _read_capped(response, limit: int) -> bytes:
    data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError("Réponse du serveur trop volumineuse.")
    return data


def _http_error(e: urllib.error.HTTPError) -> UpdateError:
    if e.code in (401, 403):
        return UpdateError(_MSG_REFUSED)
    if e.code == 404:
        return UpdateError(_MSG_NOT_FOUND)
    return UpdateError(f"GitHub a répondu avec une erreur ({e.code}). Réessayez plus tard.")


def _monotonic() -> float:
    """time.monotonic() behind a seam tests can move forward."""
    return time.monotonic()


def reset_cache() -> None:
    """Forget the last check() result."""
    _cache.clear()


def _asset_urls(release: dict) -> dict | None:
    urls = {a.get("name"): a.get("url") for a in release.get("assets") or [] if isinstance(a, dict)}
    if urls.get(EXE_NAME) and urls.get(SHA_ASSET_NAME):
        return {"exe_url": urls[EXE_NAME], "sha256_url": urls[SHA_ASSET_NAME]}
    return None


def check(*, base_url: str | None = None, force: bool = False,
          token: str | None = None, include_prereleases: bool | None = None) -> dict:
    """Ask GitHub for the newest eligible release (cached for an hour)."""
    if base_url is None:
        base_url = GITHUB_API_BASE
    if token is None or include_prereleases is None:
        cfg = load_config()
        if token is None:
            token = _resolve_token(cfg)
        if include_prereleases is None:
            include_prereleases = bool(cfg.get("include_prereleases", False))
    if not token:
        raise UpdateError(_MSG_NO_TOKEN)

    now = _monotonic()
    if not force and _cache and now - _cache["at"] < CACHE_TTL_SECONDS:
        return _cache["result"]

    url = f"{base_url.rstrip('/')}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
    try:
        with _open(url, token=token, accept="application/vnd.github+json") as response:
            releases = json.loads(_read_capped(response, MAX_API_BYTES).decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise _http_error(e) from None
    except _InsecureURL:
        raise UpdateError(_MSG_INSECURE) from None
    except (urllib.error.URLError, OSError):
        raise UpdateError(_MSG_NETWORK) from None
    except ValueError:
        raise UpdateError("Réponse de GitHub illisible.") from None
    if not isinstance(releases, list):
        raise UpdateError("Réponse de GitHub illisible.")

    chosen = select_release(releases, include_prereleases)
    current = current_version()
    latest = str(chosen["tag_name"]).strip().lstrip("v") if chosen else None
    result = {
        "current": current,
        "latest": latest,
        "available": bool(latest) and compare_versions(latest, current) > 0,
        "notes": (chosen.get("body") or "") if chosen else "",
        "published_at": (chosen.get("published_at") or "") if chosen else "",
        "asset": _asset_urls(chosen) if chosen else None,
    }
    _cache.update(result=result, at=now, checked_at=datetime.now().isoformat(timespec="seconds"))
    return result


# ── Download and verify ──────────────────────────────────────

def _fetch_expected_sha(sha_asset_url: str, token: str) -> str:
    with _open(sha_asset_url, token=token, accept="application/octet-stream") as response:
        text = _read_capped(response, MAX_SHA_BYTES).decode("utf-8", errors="replace")
    fields = text.split()
    expected = fields[0].lower() if fields else ""
    if not _SHA256_HEX.match(expected):
        raise UpdateError("Fichier SHA-256 de la version invalide ; mise à jour annulée.")
    return expected


def _stream_to(response, part: Path) -> str:
    """Write the body to `part` (size-capped) and return its sha256 hex digest."""
    declared = response.headers.get("Content-Length")
    if declared and declared.isdigit() and int(declared) > MAX_EXE_BYTES:
        raise UpdateError(_MSG_TOO_BIG)
    digest, total = hashlib.sha256(), 0
    with open(part, "wb") as out:
        while chunk := response.read(_CHUNK):
            total += len(chunk)
            if total > MAX_EXE_BYTES:
                raise UpdateError(_MSG_TOO_BIG)
            digest.update(chunk)
            out.write(chunk)
    if total == 0:
        raise UpdateError("Fichier de mise à jour vide ; mise à jour annulée.")
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


_MSG_SHA_MISMATCH = ("Échec de la vérification SHA-256 : fichier corrompu ou modifié. "
                     "Mise à jour annulée.")


def download(*, exe_asset_url: str, sha_asset_url: str, dest_dir: Path, token: str) -> Path:
    """Download the new exe to `dest_dir/Factures.exe.new`, SHA-256 verified.

    One download at a time (_install_lock). The body is streamed to a temp
    file unique to this call; the hash is recomputed from the bytes on disk
    before the file takes the name the helper swaps in, and once more after,
    so what was verified is exactly what gets installed.
    """
    if not _install_lock.acquire(blocking=False):
        raise UpdateError(_MSG_BUSY)
    try:
        return _download_locked(exe_asset_url=exe_asset_url, sha_asset_url=sha_asset_url,
                                dest_dir=Path(dest_dir), token=token)
    finally:
        _install_lock.release()


def _download_locked(*, exe_asset_url: str, sha_asset_url: str, dest_dir: Path,
                     token: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / NEW_EXE_NAME
    final.unlink(missing_ok=True)
    fd, part_name = tempfile.mkstemp(dir=dest_dir, prefix=NEW_EXE_NAME + ".", suffix=".part")
    os.close(fd)
    part = Path(part_name)
    promoted = verified = False
    try:
        # The small .sha256 first: a missing or malformed one aborts before the
        # ~100 MB exe is fetched at all.
        expected = _fetch_expected_sha(sha_asset_url, token)
        with _open(exe_asset_url, token=token, accept="application/octet-stream") as response:
            streamed = _stream_to(response, part)
        if streamed != expected or _sha256_file(part) != expected:
            raise UpdateError(_MSG_SHA_MISMATCH)
        os.replace(part, final)
        promoted = True
        if _sha256_file(final) != expected:
            raise UpdateError(_MSG_SHA_MISMATCH)
        verified = True
        return final
    except urllib.error.HTTPError as e:
        raise _http_error(e) from None
    except _InsecureURL:
        raise UpdateError(_MSG_INSECURE) from None
    except (urllib.error.URLError, OSError):
        raise UpdateError("Téléchargement interrompu. Vérifiez votre connexion internet.") from None
    finally:
        part.unlink(missing_ok=True)
        # Whatever went wrong after promotion (a mismatch, an unreadable file),
        # the helper must never find an unverified Factures.exe.new to swap in.
        if promoted and not verified:
            _discard_unverified(final)


def _discard_unverified(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.error("Impossible de supprimer %s non vérifié", path, exc_info=True)


# ── Install orchestration ────────────────────────────────────

def _exe_dir() -> Path:
    """Folder of the running exe — independent of FACTURO_DATA_DIR on purpose."""
    return Path(sys.executable).resolve().parent


def _exe_dir_writable(path: Path) -> bool:
    """Probe by creating a file: os.access() is unreliable for folders on Windows."""
    try:
        with tempfile.TemporaryFile(dir=path):
            return True
    except OSError:
        return False


def _backup_db() -> None:
    src = paths.db_path()
    if not src.exists():
        return
    dest_dir = paths.backups_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(src, dest_dir / f"data.db.{stamp}.pre-update.bak")


def install(*, port: int) -> dict:
    """Download, verify and hand over to the helper. The caller exits the app.

    Only one install at a time: a second concurrent call is refused at once.
    """
    if not _install_lock.acquire(blocking=False):
        raise UpdateError(_MSG_BUSY)
    try:
        return _install_locked(port=port)
    finally:
        _install_lock.release()


def _install_locked(*, port: int) -> dict:
    from facturo.core import database as db

    if not paths.IS_FROZEN:
        raise UpdateError("Mise à jour impossible en mode développement : "
                          "elle n'est disponible que dans Factures.exe.")
    exe_dir = _exe_dir()
    if not _exe_dir_writable(exe_dir):
        raise UpdateError("Impossible d'écrire dans le dossier de Factures.exe (permission "
                          "refusée). Déplacez le dossier hors de « Program Files ».")
    if Path(sys.executable).name.lower() != EXE_NAME.lower():
        raise UpdateError(f"Le programme doit s'appeler {EXE_NAME} pour être mis à jour.")
    if sync._lock.locked():
        raise UpdateError("Une synchronisation est en cours. Attendez qu'elle se termine.")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise UpdateError("Port invalide.")

    token = _resolve_token(load_config())
    result = check(force=True, token=token)
    if not result.get("available"):
        raise UpdateError("Aucune mise à jour disponible.")
    if not result.get("asset"):
        raise UpdateError(f"La version {result.get('latest')} ne contient pas {EXE_NAME} ; "
                          "réessayez plus tard.")

    try:
        db.checkpoint()
    except Exception:
        logger.exception("Checkpoint de data.db impossible avant la mise à jour")
        raise UpdateError("Impossible de préparer la base de données pour la mise à jour.") from None
    try:
        _backup_db()
    except OSError:
        raise UpdateError("Impossible de sauvegarder data.db ; mise à jour annulée.") from None

    downloaded = Path(download(exe_asset_url=result["asset"]["exe_url"],
                               sha_asset_url=result["asset"]["sha256_url"],
                               dest_dir=exe_dir, token=token))
    script_path = None
    try:
        script_path = _write_helper_script(exe_dir=exe_dir, exe_name=EXE_NAME,
                                           new_exe_name=downloaded.name, old_pid=os.getpid(),
                                           port=port, expected_version=result["latest"])
        _launch_helper(script_path)
    except (OSError, ValueError, UpdateError) as e:
        downloaded.unlink(missing_ok=True)
        if script_path is not None:
            Path(script_path).unlink(missing_ok=True)
        if isinstance(e, UpdateError):
            raise
        raise UpdateError("Impossible de lancer l'installation de la mise à jour.") from None
    logger.info("Mise à jour vers %s lancée", result["latest"])
    return {"ok": True, "version": result["latest"]}


# The helper is deliberately ASCII-only and path-free: it runs from the exe
# folder (%~dp0), so spaces, accents or & in the path never reach a command
# line and no code-page question arises. Sleeps use ping because `timeout`
# aborts when there is no interactive console. Written with CRLF line endings,
# which cmd needs for reliable goto/labels.
_HELPER_TEMPLATE = r"""@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Facturo update helper - generated by facturo/services/updater.py. Safe to delete.
cd /d "%~dp0" || exit /b 1
set "PYINSTALLER_RESET_ENVIRONMENT=1"
set "_MEIPASS2="
set "HEALTH_URL=http://127.0.0.1:@PORT@/api/version@QUERY@"
set "REASON="
call :log "helper started, waiting for PID @PID@"

rem 1. Wait (max 60 s) for the old app process to exit.
set /a N=0
:wait_old
tasklist /FI "PID eq @PID@" /NH 2>nul | find "@PID@" >nul
if errorlevel 1 goto move_current
set /a N+=1
if %N% geq 60 set "REASON=OLD_PROCESS_STILL_RUNNING"
if defined REASON goto abort_untouched
ping -n 2 127.0.0.1 >nul
goto wait_old

rem 2. Move the current exe aside (retries: antivirus may hold a lock).
:move_current
if exist "Factures.old.exe" del /f /q "Factures.old.exe" >nul 2>&1
set /a N=0
:retry_move_current
move /y "@EXE@" "Factures.old.exe" >nul 2>&1
if not errorlevel 1 goto move_new
set /a N+=1
if %N% geq 30 set "REASON=RENAME_CURRENT_FAILED"
if defined REASON goto abort_restart_old
ping -n 2 127.0.0.1 >nul
goto retry_move_current

rem 3. Put the verified download in place.
:move_new
set /a N=0
:retry_move_new
move /y "@NEW@" "@EXE@" >nul 2>&1
if not errorlevel 1 goto start_new
set /a N+=1
if %N% geq 30 set "REASON=ACTIVATE_NEW_FAILED"
if defined REASON goto restore_old
ping -n 2 127.0.0.1 >nul
goto retry_move_new

rem 4. Start the new version on the same port, remember ITS pid (the rollback
rem    kills only that process), and health-check it (~30 s). The exe path goes
rem    through the environment, never through a quoted command line.
:start_new
call :log "starting new version"
set "NEW_EXE_PATH=%~dp0@EXE@"
set "NEW_PID="
if exist "update_new_pid.txt" del /f /q "update_new_pid.txt" >nul 2>&1
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath $env:NEW_EXE_PATH -ArgumentList '--port','@PORT@','--no-browser' -WorkingDirectory (Split-Path -Parent $env:NEW_EXE_PATH) -PassThru; Set-Content -Encoding ascii -Path 'update_new_pid.txt' -Value $p.Id"
if exist "update_new_pid.txt" set /p NEW_PID=<"update_new_pid.txt"
if defined NEW_PID (echo %NEW_PID%| findstr /R /X "[0-9][0-9]*" >nul || set "NEW_PID=")
call :log "new version pid %NEW_PID%"
set /a N=0
:health
ping -n 2 127.0.0.1 >nul
set /a N+=1
if %N% gtr 30 set "REASON=HEALTH_CHECK_FAILED"
if defined REASON goto rollback
call :probe
if errorlevel 1 goto health
call :log "new version healthy"
del /f /q "Factures.old.exe" >nul 2>&1
del /f /q "Factures.failed.exe" >nul 2>&1
del /f /q "update_new_pid.txt" >nul 2>&1
(goto) 2>nul & del /f /q "%~f0"
exit /b 0

rem 5. Rollback: stop the new exe, restore Factures.old.exe, restart it.
:rollback
call :log "rollback: %REASON%"
if defined NEW_PID taskkill /F /T /PID %NEW_PID% >nul 2>&1
del /f /q "update_new_pid.txt" >nul 2>&1
ping -n 3 127.0.0.1 >nul
set /a N=0
:retry_move_failed
if not exist "@EXE@" goto restore_old
move /y "@EXE@" "Factures.failed.exe" >nul 2>&1
if not errorlevel 1 goto restore_old
set /a N+=1
if %N% geq 30 goto restore_old
ping -n 2 127.0.0.1 >nul
goto retry_move_failed

:restore_old
set /a N=0
:retry_restore
move /y "Factures.old.exe" "@EXE@" >nul 2>&1
if not errorlevel 1 goto restart_old
set /a N+=1
if %N% geq 30 goto restart_old
ping -n 2 127.0.0.1 >nul
goto retry_restore

:abort_restart_old
del /f /q "@NEW@" >nul 2>&1
:restart_old
>"update_failed.txt" echo ROLLBACK %REASON%
call :log "restarting previous version (%REASON%)"
start "Factures" "%~dp0@EXE@" --port @PORT@ --no-browser
exit /b 1

:abort_untouched
del /f /q "@NEW@" >nul 2>&1
>"update_failed.txt" echo ROLLBACK %REASON%
call :log "aborted: %REASON%"
exit /b 1

rem Exit code 0 once /api/version answers 200 (with ?expect=, only for that version).
:probe
if exist "%SystemRoot%\System32\curl.exe" (
  "%SystemRoot%\System32\curl.exe" -s -f -o nul --max-time 2 "%HEALTH_URL%"
) else (
  powershell -NoProfile -NonInteractive -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri $env:HEALTH_URL | Out-Null; exit 0 } catch { exit 1 }"
)
exit /b %errorlevel%

:log
>>"update_helper.log" echo [%date% %time%] %~1
exit /b 0
"""


def build_helper_script(*, exe_dir, exe_name: str, new_exe_name: str, old_pid: int, port: int,
                        expected_version: str | None = None) -> str:
    """Render update_helper.cmd (pure text, no I/O).

    `exe_dir` is accepted for the contract but never embedded: the script
    locates itself with %~dp0, which is immune to spaces/accents in the path.
    With `expected_version`, the health probe is `/api/version?expect=X`, which
    only answers 200 when that exact version is the one running.
    """
    del exe_dir  # see docstring
    for name in (exe_name, new_exe_name):
        if not _SAFE_FILENAME.match(name):
            raise ValueError(f"nom de fichier non sûr : {name!r}")
    if isinstance(old_pid, bool) or not isinstance(old_pid, int) or old_pid <= 0:
        raise ValueError("pid invalide")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("port invalide")
    query = ""
    if expected_version is not None:
        parse_version(expected_version)  # only digits, dots, "-rc" survive this
        query = f"?expect={expected_version.strip().lstrip('v')}"
    script = (_HELPER_TEMPLATE
              .replace("@EXE@", exe_name)
              .replace("@NEW@", new_exe_name)
              .replace("@PID@", str(old_pid))
              .replace("@PORT@", str(port))
              .replace("@QUERY@", query))
    script.encode("ascii")  # guard: the body must stay ASCII
    return script.replace("\r\n", "\n").replace("\n", "\r\n")


def _write_helper_script(*, exe_dir: Path, exe_name: str, new_exe_name: str, old_pid: int,
                         port: int, expected_version: str | None = None) -> Path:
    """Write update_helper.cmd into exe_dir and return its path."""
    exe_dir = Path(exe_dir)
    exe_dir.mkdir(parents=True, exist_ok=True)
    script_path = exe_dir / HELPER_NAME
    content = build_helper_script(exe_dir=exe_dir, exe_name=exe_name, new_exe_name=new_exe_name,
                                  old_pid=old_pid, port=port, expected_version=expected_version)
    script_path.write_bytes(content.encode("ascii"))
    return script_path


def _helper_env() -> dict:
    """Our environment minus PyInstaller's onefile bookkeeping variables."""
    return {k: v for k, v in os.environ.items()
            if not k.upper().startswith("_PYI") and k.upper() != "_MEIPASS2"}


def _launch_helper(script_path: Path) -> None:
    """Start the helper detached from this process (Windows only)."""
    if not sys.platform.startswith("win"):
        raise UpdateError("La mise à jour automatique n'est disponible que sous Windows.")
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    cmd_exe = str(Path(system_root) / "System32" / "cmd.exe")
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    kwargs = dict(cwd=str(Path(script_path).parent), env=_helper_env(), close_fds=True,
                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # `call` as its own argument: when the command line after /c starts with a
    # quote (a lone quoted path), cmd.exe strips the first and last quote, and an
    # `&` in the folder name then splits the command ("'...\Facturo' is not
    # recognized"). The quoted path after `call` is left intact.
    args = [cmd_exe, "/d", "/c", "call", str(script_path)]
    try:
        # Leave any job object so the helper survives this process exiting.
        subprocess.Popen(args, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kwargs)
    except OSError:
        subprocess.Popen(args, creationflags=flags, **kwargs)


# ── Cleanup after update ────────────────────────────────────

def pending_failure_report() -> bool:
    """True when the helper left an update_failed.txt to surface (frozen only)."""
    return paths.IS_FROZEN and (_exe_dir() / FAILED_FILE_NAME).exists()


def _rollback_message(raw: str) -> str:
    text = raw.strip()
    if text.startswith("ROLLBACK"):
        return _ROLLBACK_MESSAGES.get(text[len("ROLLBACK"):].strip(), _ROLLBACK_DEFAULT)
    return text or _ROLLBACK_DEFAULT


def cleanup_after_update() -> dict | None:
    """Startup housekeeping in the frozen app.

    A failure report left by the helper is consumed and surfaced once via
    status(); otherwise leftovers of a successful update are removed.
    """
    global _last_update_failure
    if not paths.IS_FROZEN:
        return None

    exe_dir = _exe_dir()
    failed_file = exe_dir / FAILED_FILE_NAME
    leftovers = [NEW_EXE_NAME, FAILED_EXE_NAME, HELPER_NAME, NEW_PID_FILE_NAME]
    leftovers += [p.name for p in exe_dir.glob(NEW_EXE_NAME + ".*.part")]
    result: dict | None = None
    if failed_file.exists():
        try:
            raw = failed_file.read_text(encoding="utf-8", errors="replace")
            failed_file.unlink()
        except OSError:
            raw = ""
        _last_update_failure = _rollback_message(raw)
        logger.warning("Mise à jour annulée par l'assistant : %s", raw.strip()[:200])
        result = {"message": _last_update_failure}
    else:
        leftovers.append(OLD_EXE_NAME)
    for name in leftovers:
        try:
            (exe_dir / name).unlink(missing_ok=True)
        except OSError:
            logger.info("Fichier de mise à jour non supprimé : %s", name)
    return result

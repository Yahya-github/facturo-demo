"""Config files that hold a GitHub token: owner-only on disk, DPAPI on Windows.

Shared by services/updater.py (update_config.json) and services/sync.py
(sync_config.json). On Windows a token is stored as the base64 of a
CryptProtectData blob bound to the current Windows user, so a copied config file
is useless on another account or PC. Elsewhere the plaintext token lives in a
file only its owner can read (0600).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CRYPTPROTECT_UI_FORBIDDEN = 0x1


def use_dpapi() -> bool:
    return sys.platform.startswith("win")


def dpapi(data: bytes, *, protect: bool, entropy: bytes, description: str) -> bytes:
    """CryptProtectData / CryptUnprotectData for the current user (Windows only)."""
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(raw: bytes) -> tuple[_Blob, Any]:
        buf = ctypes.create_string_buffer(raw, len(raw))
        return _Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    blob_p = ctypes.POINTER(_Blob)
    in_blob, _in_buf = blob(data)
    entropy_blob, _entropy_buf = blob(entropy)
    out_blob = _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.argtypes = [blob_p, wintypes.LPCWSTR if protect else ctypes.c_void_p, blob_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, blob_p]
    fn.restype = wintypes.BOOL
    ok = fn(ctypes.byref(in_blob), description if protect else None, ctypes.byref(entropy_blob),
            None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob))
    if not ok:
        raise OSError(ctypes.get_last_error(), "DPAPI")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))


def encode_blob(blob: bytes) -> str:
    return base64.b64encode(blob).decode("ascii")


def decode_blob(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def write_private_json(path: Path, obj: dict) -> None:
    """Atomic JSON write, owner-only (0600) where the OS supports it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    try:
        os.chmod(path, 0o600)
    except OSError:  # e.g. a FAT or network share: nothing more we can do
        logger.info("Impossible de restreindre les droits de %s", path.name)

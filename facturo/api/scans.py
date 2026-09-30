"""Scanned invoices filed per client (PDF or images)."""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from facturo import paths
from facturo.core import database as db
from facturo.i18n import tr

log = logging.getLogger(__name__)

router = APIRouter()


# ── Factures scannées ────────────────────────────────────
# Uploaded scans (PDF or images) filed under a client, so the user can browse
# all numerized invoices per client. Files live next to the exe in scans/.

SCANS_DIR = paths.scans_dir()
MAX_SCAN_BYTES = 25 * 1024 * 1024  # 25 MB per file
ALLOWED_SCAN_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic"}


@router.get("/api/scans")
def api_list_scans(client_id: int | None = None):
    return db.list_scans(client_id)


@router.post("/api/scans")
async def api_upload_scan(client_id: int = Form(...), file: UploadFile = File(...)):
    if not db.get_client(client_id):
        raise HTTPException(404, tr("err.client_not_found"))

    # One byte past the cap is enough to know it is too big, without ever
    # holding an arbitrarily large upload in memory.
    raw = await file.read(MAX_SCAN_BYTES + 1)
    if not raw:
        raise HTTPException(400, tr("err.file_empty"))
    if len(raw) > MAX_SCAN_BYTES:
        raise HTTPException(400, tr("err.file_too_large"))

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_SCAN_EXT:
        raise HTTPException(400, tr("err.unsupported_format"))

    # Store under a random name so two scans with the same original name (or odd
    # characters) never collide; the display name is kept in the database.
    stored = f"{uuid.uuid4().hex}{ext}"
    target = SCANS_DIR / stored
    try:
        SCANS_DIR.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return db.add_scan(client_id, stored, file.filename or stored)
    except Exception as e:
        # No file may outlive a failed upload: it would be synced but never listed.
        log.exception("Enregistrement du document scanné %s impossible", stored)
        _remove_scan_file(target)
        raise HTTPException(500, tr("err.scan_save_failed")) from e


def _remove_scan_file(path: Path) -> None:
    """Delete a scan file. A leftover file is harmless, so a failure is logged
    rather than failing the request."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log.warning("Suppression du document scanné %s impossible ; fichier laissé en place",
                    path.name, exc_info=True)


@router.get("/api/scans/file/{filename}")
def api_get_scan_file(filename: str):
    safe_name = Path(filename).name
    file_path = SCANS_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(404, tr("err.file_not_found"))
    # No filename/disposition → browser shows it inline (PDF/image preview); the
    # download button on the page uses the <a download> attribute to save it.
    return FileResponse(str(file_path))


@router.delete("/api/scans/{scan_id}")
def api_delete_scan(scan_id: int):
    scan = db.get_scan(scan_id)
    if not scan:
        raise HTTPException(404, tr("err.document_not_found"))
    _remove_scan_file(SCANS_DIR / Path(scan["fichier"]).name)
    db.delete_scan(scan_id)
    return {"ok": True}

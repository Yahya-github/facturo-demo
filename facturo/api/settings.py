"""Capabilities, company logo and full reset."""


import io
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from facturo import paths
from facturo.api import payments as payments_api
from facturo.api import scans as scans_api
from facturo.core import database as db
from facturo.invoicing import excel_generator as gen

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/capabilities")
def api_capabilities():
    """Tell the frontend which optional features are available on this PC."""
    return {
        "pdf": gen.find_soffice() is not None,
        "logo": paths.logo_path().exists(),
    }


# ── Logo ─────────────────────────────────────────────────

MAX_LOGO_BYTES = 5 * 1024 * 1024  # 5 MB upload cap


@router.get("/api/logo")
def api_get_logo():
    """Serve the current company logo for preview, or 404 if none is set."""
    logo = paths.logo_path()
    if not logo.exists():
        raise HTTPException(404, "Aucun logo")
    return FileResponse(str(logo), media_type="image/png")


@router.post("/api/logo")
async def api_upload_logo(file: UploadFile = File(...)):
    """Store a company logo, normalized to PNG so exports have one fixed format."""
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Fichier vide")
    if len(raw) > MAX_LOGO_BYTES:
        raise HTTPException(400, "Image trop volumineuse (max 5 Mo)")

    try:
        from PIL import Image as PILImage

        with PILImage.open(io.BytesIO(raw)) as im:
            im.load()
            rgba = im.convert("RGBA")
            rgba.save(str(paths.logo_path()), format="PNG")
    except Exception:
        raise HTTPException(400, "Image invalide. Utilisez un fichier PNG ou JPG.") from None

    return {"ok": True}


@router.delete("/api/logo")
def api_delete_logo():
    """Remove the company logo so exports stop including it."""
    logo = paths.logo_path()
    if logo.exists():
        logo.unlink()
    return {"ok": True}


@router.post("/api/reset")
def api_reset_db():
    """Empty the database, then the files only it referenced: scanned invoices
    and imported payment PDFs. Left behind they would be orphans that sync keeps
    shipping. Generated invoices (output/), the logo and the configs stay."""
    db.reset_db()
    for folder in (scans_api.SCANS_DIR, payments_api.PAYMENTS_DIR):
        _empty_folder(folder)
    return {"ok": True}


def _empty_folder(folder) -> None:
    if not folder.exists():
        return
    for f in folder.iterdir():
        try:
            f.unlink()
        except OSError:
            log.warning("Réinitialisation : suppression de %s impossible", f, exc_info=True)

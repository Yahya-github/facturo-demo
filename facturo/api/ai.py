"""AI-assisted billet extraction via Ollama. Never writes to the database."""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from facturo.api.scans import ALLOWED_SCAN_EXT, MAX_SCAN_BYTES, SCANS_DIR
from facturo.core import database as db
from facturo.core import known_values
from facturo.extraction import ai_extract

router = APIRouter()


class ExtractScanIn(BaseModel):
    scan_id: int


class ExtractTextIn(BaseModel):
    text: str


# ── Extraction IA (Ollama local) ────────────────────────
# Never writes to the DB or generates an invoice — only returns field data for
# the existing manual billet form to display/edit before the user hits
# "Générer la facture". None of these endpoints ever read or return a
# client_id — the invoice's client is always a manual user choice, never
# decided by the AI.


@router.get("/api/ai/status")
def api_ai_status():
    """Whether a local vision model is reachable, so the UI can say so up front."""
    return ai_extract.describe_config()


def _history() -> ai_extract.History:
    """Renter names and truck plates already billed, most frequent first.

    The same sites and the same trucks recur billet after billet, so these are a
    better authority than a fresh read of someone's cursive — "Chantier Nard" is an
    o misread as an a, and the history already says "Chantier Nord"; "AB12395" is a
    4 misread as a 9 on a truck that has been billed fourteen times. Feeding
    them to the extractor also keeps split-by-chantier from seeing one site as
    two spellings.

    Reads the curated known-values list rather than rescanning every invoice.
    Curation is the point: derived on the fly, a plate typed once as "S/O"
    became something every later extraction was pulled towards, with no way to
    remove it short of editing an old invoice. It also lets a new truck be put
    on file *before* its first billet, which is what stops snap_plate rewriting
    a genuinely new plate into the older one it resembles.
    """
    return ai_extract.History(
        chantiers=known_values.for_history("chantier"),
        plaques=known_values.for_history("plaque"),
    )


@router.post("/api/ai/extract-image")
async def api_ai_extract_image(file: UploadFile = File(...)):
    """Direct photo or PDF -> billet fields, no scan upload/persistence involved.

    Ephemeral by design: the file is read into memory, sent to the model, and
    discarded — nothing is written to disk or the database.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Fichier vide")
    if len(raw) > MAX_SCAN_BYTES:
        raise HTTPException(400, "Fichier trop volumineux (max 25 Mo)")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_SCAN_EXT:
        raise HTTPException(400, "Format non supporté. Utilisez un PDF ou une image.")
    try:
        return {"billets": ai_extract.extract_from_scan(raw, _history())}
    except ai_extract.AIExtractError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/api/ai/extract-scan")
def api_ai_extract_scan(data: ExtractScanIn):
    """An already-uploaded scan -> one billet per page.

    Scanned PDFs are batches (one paper billet per page), so this returns a
    list. Pages the model could not read carry an `error` instead of fields,
    which keeps one bad ticket from discarding the rest of the stack.
    """
    scan = db.get_scan(data.scan_id)
    if not scan:
        raise HTTPException(404, "Document introuvable")
    scan_file = SCANS_DIR / Path(scan["fichier"]).name
    if not scan_file.exists():
        raise HTTPException(404, "Fichier introuvable")
    try:
        return {"billets": ai_extract.extract_from_scan(scan_file.read_bytes(), _history())}
    except ai_extract.AIExtractError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/api/ai/extract-text")
def api_ai_extract_text(data: ExtractTextIn):
    try:
        return ai_extract.extract_from_text(data.text, _history())
    except ai_extract.AIExtractError as e:
        raise HTTPException(422, str(e)) from e

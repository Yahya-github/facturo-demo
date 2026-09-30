"""Proofs of payment (Paiements tab): import, matching review, reverse lookup.

Only proofs of payment are accepted. A bill addressed TO the company
(facturo.brand.COMPANY_NAME) is recognized by the parser and refused with 422 before anything is written.
"""

import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from facturo import paths
from facturo.brand import COMPANY_NAME
from facturo.core.billet_fields import tidy_billet_number
from facturo.i18n import tr, tr_or_text
from facturo.payments import parser, pdf_text, store

log = logging.getLogger(__name__)

router = APIRouter()

# Resolved once at import. Handlers use this module attribute (never a copy),
# so tests repoint it with monkeypatch.setattr(payments_api, "PAYMENTS_DIR", ...).
PAYMENTS_DIR = paths.payments_dir()
MAX_PAYMENT_BYTES = 25 * 1024 * 1024  # 25 MB per file
_STORED_NAME = re.compile(r"[0-9a-f]{32}\.pdf")
_ISO_DATE = r"^(\d{4}-\d{2}-\d{2})?$"


# ── Import ────────────────────────────────────────────────────────────────

def _check_upload(raw: bytes) -> None:
    if not raw:
        raise HTTPException(400, tr("err.file_empty"))
    if len(raw) > MAX_PAYMENT_BYTES:
        raise HTTPException(400, tr("err.file_too_large"))
    if not raw.startswith(b"%PDF-"):
        raise HTTPException(400, tr("err.pdf_only"))


def _remove_file(name: str) -> None:
    target = PAYMENTS_DIR / Path(name).name
    try:
        target.unlink(missing_ok=True)
    except OSError:
        log.warning("Impossible de supprimer le fichier de paiement %s", target, exc_info=True)


@router.post("/api/paiements")
async def api_import_paiement(file: UploadFile = File(...)):
    raw = await file.read(MAX_PAYMENT_BYTES + 1)
    _check_upload(raw)
    try:
        text = await run_in_threadpool(pdf_text.extract_text, raw)
    except pdf_text.PaymentParseError as e:
        raise HTTPException(400, tr_or_text(str(e))) from e

    doc = await run_in_threadpool(parser.parse, text)
    if doc.facture_adressee_entreprise:
        raise HTTPException(422, tr("err.bill_refused", company=COMPANY_NAME))

    stored = f"{uuid.uuid4().hex}.pdf"
    nom_original = Path(file.filename or "").name[:255] or stored
    try:
        await run_in_threadpool(_save_pdf, stored, raw)
    except OSError as e:
        log.error("Enregistrement du fichier de paiement %s impossible", stored, exc_info=True)
        _remove_file(stored)  # a partial write must not stay behind
        raise HTTPException(500, tr("err.payment_save_failed")) from e
    try:
        return await run_in_threadpool(store.create_paiement, doc, text, stored, nom_original)
    except BaseException:
        _remove_file(stored)
        raise


def _save_pdf(stored: str, raw: bytes) -> None:
    PAYMENTS_DIR.mkdir(parents=True, exist_ok=True)
    (PAYMENTS_DIR / stored).write_bytes(raw)


# ── Payments ──────────────────────────────────────────────────────────────

@router.get("/api/paiements")
def api_list_paiements():
    return store.list_paiements()


@router.get("/api/paiements/file/{name}")
def api_get_paiement_file(name: str):
    safe = Path(name).name
    if not _STORED_NAME.fullmatch(safe):
        raise HTTPException(404, tr("err.file_not_found"))
    base = PAYMENTS_DIR.resolve()
    target = (base / safe).resolve()
    if target.parent != base or not target.is_file():
        raise HTTPException(404, tr("err.file_not_found"))
    return FileResponse(str(target), media_type="application/pdf")


@router.get("/api/paiements/{paiement_id}")
def api_get_paiement(paiement_id: int):
    try:
        return store.get_paiement(paiement_id)
    except store.PaymentNotFound as e:
        raise HTTPException(404, tr("err.payment_not_found")) from e


class PaiementUpdate(BaseModel):
    emetteur: str | None = Field(None, max_length=200)
    reference: str | None = Field(None, max_length=100)
    date: str | None = Field(None, pattern=_ISO_DATE)
    sous_total: float | None = None
    tps: float | None = None
    tvq: float | None = None
    escompte: float | None = None
    total: float | None = None
    notes: str | None = Field(None, max_length=2000)


_TEXT_FIELDS = {"emetteur", "reference", "date", "notes"}


@router.put("/api/paiements/{paiement_id}")
def api_update_paiement(paiement_id: int, data: PaiementUpdate):
    fields = data.model_dump(exclude_unset=True)
    # Text columns are NOT NULL: a cleared field is stored as "".
    fields = {k: ("" if v is None and k in _TEXT_FIELDS else v) for k, v in fields.items()}
    try:
        return store.update_paiement(paiement_id, fields)
    except store.PaymentNotFound as e:
        raise HTTPException(404, tr("err.payment_not_found")) from e


@router.delete("/api/paiements/{paiement_id}")
def api_delete_paiement(paiement_id: int):
    try:
        fichier = store.delete_paiement(paiement_id)
    except store.PaymentNotFound as e:
        raise HTTPException(404, tr("err.payment_not_found")) from e
    if fichier:
        _remove_file(fichier)
    return {"ok": True}


# ── Lignes ────────────────────────────────────────────────────────────────

class LigneIn(BaseModel):
    numero_billet: str = Field(..., min_length=1, max_length=40)


@router.post("/api/paiements/{paiement_id}/lignes")
def api_add_ligne(paiement_id: int, data: LigneIn):
    if not data.numero_billet.strip():
        raise HTTPException(400, tr("err.ticket_number_required"))
    if not tidy_billet_number(data.numero_billet):
        # e.g. a project number ("#26-112"): storing it blank would match nothing.
        raise HTTPException(422, tr("err.not_a_ticket_number"))
    try:
        return store.add_ligne_manuelle(paiement_id, data.numero_billet)
    except store.PaymentNotFound as e:
        raise HTTPException(404, tr("err.payment_not_found")) from e


class LienIn(BaseModel):
    facture_id: int | None = None
    billet_index: int | None = Field(None, ge=0)


@router.put("/api/paiements/lignes/{ligne_id}")
def api_link_ligne(ligne_id: int, data: LienIn):
    try:
        if data.facture_id is None:
            return store.unlink_ligne(ligne_id)
        if data.billet_index is None:
            raise HTTPException(400, tr("err.choose_ticket"))
        return store.link_ligne(ligne_id, data.facture_id, data.billet_index)
    except store.LigneNotFound as e:
        raise HTTPException(404, tr("err.payment_line_not_found")) from e
    except store.InvalidBillet as e:
        raise HTTPException(400, tr("err.ticket_not_on_invoice")) from e
    except store.LinkConflict as e:
        raise HTTPException(409, tr_or_text(str(e))) from e


@router.delete("/api/paiements/lignes/{ligne_id}")
def api_delete_ligne(ligne_id: int):
    try:
        store.delete_ligne(ligne_id)
    except store.LigneNotFound as e:
        raise HTTPException(404, tr("err.payment_line_not_found")) from e
    return {"ok": True}


# ── Reverse lookup (invoice form) ─────────────────────────────────────────

@router.get("/api/factures/{facture_id}/paiements")
def api_facture_paiements(facture_id: int):
    result = store.factures_paiements(facture_id)
    if result is None:
        raise HTTPException(404, tr("err.invoice_not_found"))
    return result

"""Clients (the companies being billed)."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from facturo.api.scans import SCANS_DIR
from facturo.core import database as db
from facturo.i18n import tr

router = APIRouter()

# ── Clients ──────────────────────────────────────────────


class ClientIn(BaseModel):
    ref: str
    prefix: str
    nom: str
    adresse: str = ""
    # When true, generating an invoice for this client produces one invoice per
    # distinct "Chantier / Client" (see _group_billets_by_chantier).
    separer_chantiers: bool = False
    # Usual hourly rate; prefills new billet rows in the UI. 0 = unset.
    taux_defaut: float = 0.0


@router.get("/api/clients")
def api_list_clients():
    return db.list_clients()


@router.get("/api/clients/{client_id}")
def api_get_client(client_id: int):
    c = db.get_client(client_id)
    if not c:
        raise HTTPException(404, tr("err.client_not_found"))
    return c


@router.post("/api/clients")
def api_create_client(data: ClientIn):
    return db.create_client(
        data.ref, data.prefix, data.nom, data.adresse, data.separer_chantiers,
        data.taux_defaut,
    )


@router.put("/api/clients/{client_id}")
def api_update_client(client_id: int, data: ClientIn):
    if not db.get_client(client_id):
        raise HTTPException(404, tr("err.client_not_found"))
    return db.update_client(
        client_id, data.ref, data.prefix, data.nom, data.adresse,
        data.separer_chantiers, data.taux_defaut,
    )


@router.delete("/api/clients/{client_id}")
def api_delete_client(client_id: int):
    if not db.get_client(client_id):
        raise HTTPException(404, tr("err.client_not_found"))
    # Remove the client's scanned-invoice files before their rows are dropped.
    for s in db.list_scans(client_id):
        scan_file = SCANS_DIR / Path(s["fichier"]).name
        try:
            if scan_file.exists():
                scan_file.unlink()
        except OSError:
            pass
    db.delete_client(client_id)
    return {"ok": True}

"""GitHub data sync endpoints (see services/sync.py)."""



from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from facturo.i18n import tr, tr_or_text
from facturo.services import sync

router = APIRouter()


# ── Synchronisation GitHub ───────────────────────────────
# Optional multi-device sync of the data (db, invoices, scans, logo) through a
# private GitHub repo. See sync.py for the single-device-at-a-time model.


class SyncConfigIn(BaseModel):
    url: str
    token: str
    branch: str = "main"


@router.get("/api/sync/status")
def api_sync_status():
    return sync.status()


@router.post("/api/sync/configure")
def api_sync_configure(data: SyncConfigIn):
    try:
        return sync.configure(data.url, data.token, data.branch)
    except sync.SyncError as e:
        raise HTTPException(400, tr_or_text(str(e))) from e


@router.post("/api/sync/push")
def api_sync_push():
    try:
        return sync.push()
    except sync.SyncError as e:
        raise HTTPException(400, tr_or_text(str(e))) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, tr("err.sync_failed", detail=e)) from e


@router.post("/api/sync/pull")
def api_sync_pull():
    try:
        return sync.pull()
    except sync.SyncError as e:
        raise HTTPException(400, tr_or_text(str(e))) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, tr("err.sync_failed", detail=e)) from e


@router.post("/api/sync/disconnect")
def api_sync_disconnect():
    try:
        return sync.disconnect()
    except sync.SyncError as e:
        raise HTTPException(500, tr_or_text(str(e))) from e

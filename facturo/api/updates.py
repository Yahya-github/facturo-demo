"""Application version and in-app updates."""

import logging
import os
import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from facturo import paths, version
from facturo.core import database as db
from facturo.core import schema
from facturo.i18n import tr, tr_or_text
from facturo.services import updater

router = APIRouter()
logger = logging.getLogger(__name__)

# Long enough for the install response to reach the browser before we exit.
SHUTDOWN_DELAY_SECONDS = 1.5


class UpdateConfigIn(BaseModel):
    token: str | None = Field(default=None, max_length=255)
    include_prereleases: bool | None = None


class InstallIn(BaseModel):
    port: int = Field(ge=1, le=65535)


@router.get("/api/version")
def api_version(expect: str | None = None):
    """App/schema version. With ?expect=X, answers 409 unless X is running —
    update_helper.cmd uses this to health-check exactly the new version."""
    if expect is not None and expect.strip().lstrip("v") != version.__version__:
        raise HTTPException(409, tr("err.version_mismatch"))
    return {
        "version": version.__version__,
        "schema_version": schema.SCHEMA_VERSION,
        "frozen": paths.IS_FROZEN,
        "db_newer_than_app": db.is_newer_than_app(),
    }


@router.get("/api/updates/status")
def api_updates_status():
    return updater.status(consume_failure=True)  # the one place the message is consumed


@router.post("/api/updates/config")
def api_updates_config(data: UpdateConfigIn):
    try:
        return updater.set_config(token=data.token, include_prereleases=data.include_prereleases)
    except updater.UpdateError as e:
        raise HTTPException(400, tr_or_text(str(e))) from e


@router.get("/api/updates/check")
def api_updates_check():
    try:
        return updater.check()
    except updater.UpdateError as e:
        raise HTTPException(400, tr_or_text(str(e))) from e


def _schedule_exit() -> None:
    """Exit shortly after responding so update_helper.cmd can swap the exe.

    Only the frozen app exits: install() refuses to run anywhere else, and
    this keeps a dev server (or the test process) alive no matter what."""
    if not paths.IS_FROZEN:
        return
    logger.info("Fermeture pour mise à jour")
    timer = threading.Timer(SHUTDOWN_DELAY_SECONDS, os._exit, args=(0,))
    timer.daemon = True
    timer.start()


@router.post("/api/updates/install")
def api_updates_install(data: InstallIn):
    try:
        result = updater.install(port=data.port)
    except updater.UpdateError as e:
        raise HTTPException(400, tr_or_text(str(e))) from e
    except Exception:
        # Never echo the exception: it can carry a URL with the access token.
        logger.error("Mise à jour impossible (erreur inattendue)", exc_info=False)
        raise HTTPException(500, tr("err.update_failed")) from None
    _schedule_exit()
    return result

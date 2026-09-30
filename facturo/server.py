"""FastAPI application: mounts the web UI and every API router."""

import html
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from facturo import paths
from facturo.api import (
    ai,
    clients,
    factures,
    invoice_list,
    known_values,
    payments,
    scans,
    settings,
    sync,
    updates,
)
from facturo.brand import COMPANY_NAME
from facturo.core import database as db
from facturo.i18n_middleware import I18nMiddleware
from facturo.local_guard import LocalGuardMiddleware

WEB_DIR = paths.web_dir()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title=f"Factures — {COMPANY_NAME}", lifespan=lifespan)
# Added after the guard so i18n sits outside it: the guard's own 403s are translated too.
app.add_middleware(I18nMiddleware)
app.add_middleware(LocalGuardMiddleware)
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

ROUTERS = (settings, clients, factures, invoice_list, scans, known_values, ai, sync, payments, updates)
for module in ROUTERS:
    app.include_router(module.router)


@app.get("/", response_class=HTMLResponse)
async def index():
    page = (WEB_DIR / "templates" / "index.html").read_text(encoding="utf-8")
    # The page names the company from facturo.brand; escaped once for text and attributes.
    return page.replace("{{COMPANY_NAME}}", html.escape(COMPANY_NAME))

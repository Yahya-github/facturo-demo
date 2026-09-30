"""Invoices: generate, edit, list, paid status, downloads."""

import json
import logging
import re
from contextlib import closing
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from facturo.core import billet_fields, known_values
from facturo.core import database as db
from facturo.i18n import tr
from facturo.invoicing import discounts
from facturo.invoicing import excel_generator as gen
from facturo.payments import store as payment_store

log = logging.getLogger(__name__)

router = APIRouter()


# ── Factures ─────────────────────────────────────────────


# Discounts: a percentage and a fixed amount, both optional, at billet and
# invoice level (math in invoicing/discounts.py). The legacy single-kind pair
# is still accepted from older clients and normalized to v2 before use.
class BilletIn(BaseModel):
    date_billet: str = ""
    chantier: str = ""
    plaque: str = ""
    numero_billet: str = ""
    # Free-text description mode: when desc_libre is true, `description` replaces
    # the structured fields above on the invoice line.
    description: str = ""
    desc_libre: bool = False
    quantite: float
    taux: float
    remise_type: str = ""        # legacy v1: "percent" | "montant"
    remise_valeur: float = 0.0   # legacy v1
    remise_pct: float = 0.0      # v2: percent off this billet
    remise_montant: float = 0.0  # v2: fixed $ off this billet, after the percent
    # Optional link to a row in the scans table (a scanned paper billet). Rides
    # along inside billets_json; the id is stable across the synced database.
    scan_id: int | None = None

    # Every write path goes through here, so this is the one place a value
    # cannot slip past. The AI path has cleaned its output since day one; the
    # manual path had nothing, which is how one truck ended up in the history
    # twice — "AB12345" and "AB 12345" — the space being something only a
    # person could have typed.
    #
    # Deliberately pure: tidying only, no database lookup and no history
    # snapping. A validator that reached for the known-value list would issue a
    # query per billet, and worse, would silently overrule a user who had
    # already been shown a suggestion and declined it.
    @field_validator("chantier")
    @classmethod
    def _tidy_chantier(cls, v: str) -> str:
        return billet_fields.tidy_chantier(v)

    @field_validator("plaque")
    @classmethod
    def _tidy_plaque(cls, v: str) -> str:
        return billet_fields.tidy_plate(v)

    @field_validator("numero_billet")
    @classmethod
    def _tidy_numero_billet(cls, v: str) -> str:
        return billet_fields.tidy_billet_number(v)


class FactureIn(BaseModel):
    client_id: int
    numero: str | None = None
    date: str | None = None
    billets: list[BilletIn]
    remise_type: str = ""        # legacy v1
    remise_valeur: float = 0.0   # legacy v1
    remise_pct: float = 0.0      # v2: percent off the subtotal
    remise_montant: float = 0.0  # v2: fixed $ off once, after the percent
    # PUT only: when the stored billets cannot be read, overwriting the invoice
    # would replace real lines with whatever the (blank) form held, so PUT
    # answers 409 unless the client explicitly confirms. The UI never sends it:
    # it blocks saving instead; the flag exists for a deliberate override.
    forcer_ecrasement: bool = False


def _with_v2_discount(obj: dict) -> dict:
    """Copy of a billet/facture dict carrying only normalized v2 discount fields."""
    pct, montant = discounts.normalize_discount(obj)
    return {**obj, "remise_pct": pct, "remise_montant": montant,
            "remise_type": "", "remise_valeur": 0.0}


def _billets_and_remise(data: FactureIn) -> tuple[list[dict], float, float]:
    """Billet dicts and the invoice (pct, montant), all normalized to v2."""
    billets = [_with_v2_discount(b.model_dump()) for b in data.billets]
    pct, montant = discounts.normalize_discount(data.model_dump(exclude={"billets"}))
    return billets, pct, montant


def _group_billets_by_chantier(billets: list[dict]) -> list[list[dict]]:
    """Split billets into groups sharing the same "Chantier / Client".

    Groups keep their first-seen order so the resulting invoices follow the
    order the chantiers appear on the form. Billets with no chantier (e.g.
    free-description lines) fall together into a single group.
    """
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for b in billets:
        key = (b.get("chantier") or "").strip()
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(b)
    return [groups[k] for k in order]


def _numero_sequence(base: str, count: int) -> list[str]:
    """`count` consecutive invoice numbers starting at `base`.

    Increments the last run of digits while preserving its zero-padding, so
    'demo005' yields demo005, demo006, demo007. A base with no digits gets a
    '-2', '-3'… suffix as a fallback.
    """
    if count <= 1:
        return [base]
    m = re.search(r"(\d+)(?!.*\d)", base)  # last group of digits in the string
    if not m:
        return [base] + [f"{base}-{i + 1}" for i in range(1, count)]
    start, width = int(m.group(1)), len(m.group(1))
    head, tail = base[: m.start(1)], base[m.end(1):]
    return [f"{head}{str(start + i).zfill(width)}{tail}" for i in range(count)]


class _WrittenFiles:
    """Invoice xlsx files one request writes, so a failure can undo them.

    The database write comes after the file: if it fails, a file that already
    existed gets its previous bytes back (an in-place edit must not leave the
    xlsx showing billets the database never recorded) and a new one is deleted
    with any pdf of that name, so no orphan file claims an invoice number the
    database does not know — the number would otherwise be handed out again.
    """

    def __init__(self) -> None:
        self._before: list[tuple[Path, bytes | None]] = []

    def generate(self, client: dict, numero: str, invoice_date: str, billets: list[dict],
                 filename: str, remise_pct: float, remise_montant: float) -> Path:
        target = gen.OUTPUT_DIR / filename
        self._before.append((target, target.read_bytes() if target.exists() else None))
        return gen.generate_invoice(
            client, numero, invoice_date, billets, output_filename=filename,
            remise_pct=remise_pct, remise_montant=remise_montant,
        )

    def undo(self) -> None:
        for path, previous in reversed(self._before):
            try:
                if previous is None:
                    path.unlink(missing_ok=True)
                    path.with_suffix(".pdf").unlink(missing_ok=True)
                else:
                    path.write_bytes(previous)
            except OSError:
                log.error("Impossible de rétablir le fichier de facture %s", path, exc_info=True)
        self._before.clear()


def _with_created(message: str, invoices: list[dict]) -> str:
    """Append the invoices this request did create, so a partial split is visible."""
    if not invoices:
        return message
    numeros = ", ".join(inv["numero"] for inv in invoices)
    key = "err.invoices_already_created" if len(invoices) > 1 else "err.invoice_already_created"
    return f"{message} {tr(key, numeros=numeros)}"


@router.post("/api/factures/generate")
def api_generate_facture(data: FactureIn):
    client = db.get_client(data.client_id)
    if not client:
        raise HTTPException(404, tr("err.client_not_found"))

    if not data.billets:
        raise HTTPException(400, tr("err.billet_required"))

    invoice_date = data.date or date.today().isoformat()
    billets_dicts, remise_pct, remise_montant = _billets_and_remise(data)

    # The base number is the one typed in (which carries the series forward) or
    # the suggested next one (one past the client's highest, from db.get_client).
    base_numero = data.numero or f"{client['prefix']}{client['next_numero']:03d}"

    # When the client is flagged, one invoice per chantier; otherwise a single
    # invoice with every billet. Each resulting invoice gets the next number.
    if client.get("separer_chantiers"):
        groups = _group_billets_by_chantier(billets_dicts)
    else:
        groups = [billets_dicts]
    numeros = _numero_sequence(base_numero, len(groups))

    # Each invoice is committed on its own: when a split fails part-way, the
    # invoices already created stay (their numbers are taken) and the error
    # names them, while the failed one leaves no file behind.
    invoices = []
    for group_billets, numero in zip(groups, numeros, strict=True):
        files = _WrittenFiles()
        try:
            out_path = files.generate(
                client, numero, invoice_date, group_billets,
                filename=gen.invoice_filename(client, numero, invoice_date),
                remise_pct=remise_pct, remise_montant=remise_montant,
            )
        except Exception as e:
            files.undo()
            raise HTTPException(
                500, _with_created(tr("err.generate_failed", detail=e), invoices),
            ) from e

        try:
            db.save_facture(
                data.client_id, numero, invoice_date, str(out_path.name),
                billets_json=json.dumps(group_billets),
                remise_pct=remise_pct, remise_montant=remise_montant,
            )
        except Exception as e:
            log.exception("Enregistrement de la facture %s impossible", numero)
            files.undo()
            raise HTTPException(500, _with_created(
                tr("err.invoice_not_saved", numero=numero), invoices,
            )) from e
        invoices.append({"filename": out_path.name, "numero": numero})

    # Over the whole billet list rather than per generated invoice: a client
    # set to split by chantier produces several invoices from one submission,
    # and each value should be counted once.
    known_values.record(billets_dicts, invoice_date)
    return {"invoices": invoices, "split": len(invoices) > 1}


def _stored_billets(facture: dict) -> tuple[list[dict], str]:
    """Billets of a saved invoice, and why they could not be read ("" when fine).

    Billets generated before they were persisted are recovered from the xlsx.
    A non-empty reason means the invoice has billets we failed to read: showing
    a blank form instead would let "Enregistrer" regenerate the xlsx under the
    same filename and destroy the real invoice.
    """
    problems: list[str] = []
    billets: list = []
    if facture.get("billets_json"):
        try:
            parsed = json.loads(facture["billets_json"])
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, list):
            billets = parsed
        else:
            problems.append(tr("err.stored_billets_unreadable"))

    xlsx_path = gen.OUTPUT_DIR / facture["fichier"]
    if not billets:
        if xlsx_path.exists():
            try:
                billets = gen.read_billets_from_xlsx(xlsx_path)
            except Exception:
                log.exception("Lecture du fichier %s impossible", xlsx_path)
                problems.append(tr("err.excel_unreadable"))
        elif problems:
            problems.append(tr("err.excel_not_found"))

    billets = [b for b in billets if isinstance(b, dict)]
    if billets or not problems:
        return billets, ""
    reason = " ; ".join(problems)
    log.error("Billets illisibles pour la facture %s (%s) : %s", facture["id"], xlsx_path, reason)
    return [], reason


@router.get("/api/factures/{facture_id}")
def api_get_facture(facture_id: int):
    """Return a single invoice with its billets, for editing.

    Discounts come back as v2 fields even for rows still holding legacy ones.
    `billets_unreadable` tells the editor the billets exist but could not be
    read, so it must not offer to save over them.
    """
    facture = db.get_facture(facture_id)
    if not facture:
        raise HTTPException(404, tr("err.invoice_not_found"))

    billets, unreadable = _stored_billets(facture)
    billets = [_with_v2_discount(b) for b in billets]
    return {
        **_with_v2_discount(facture), "billets": billets,
        "billets_unreadable": bool(unreadable), "billets_unreadable_reason": unreadable,
    }


@router.put("/api/factures/{facture_id}")
def api_update_facture(facture_id: int, data: FactureIn):
    """Regenerate an existing invoice in place after edits.

    Keeps the same invoice number and overwrites the same file (so history
    links stay valid); the client counter is NOT advanced.
    """
    facture = db.get_facture(facture_id)
    if not facture:
        raise HTTPException(404, tr("err.invoice_not_found"))

    client = db.get_client(facture["client_id"])
    if not client:
        raise HTTPException(404, tr("err.client_not_found"))

    if not data.billets:
        raise HTTPException(400, tr("err.billet_required"))

    if not data.forcer_ecrasement and _stored_billets(facture)[1]:
        raise HTTPException(409, f"{tr('err.billets_unreadable')} {tr('err.save_would_overwrite')}")

    invoice_date = data.date or facture["date"]
    billets_dicts, remise_pct, remise_montant = _billets_and_remise(data)

    # When the client is flagged to split per chantier, regenerating splits too:
    # the FIRST chantier updates this invoice in place, and each extra chantier
    # becomes a new invoice with a fresh number. Otherwise it's a single invoice.
    if client.get("separer_chantiers"):
        groups = _group_billets_by_chantier(billets_dicts)
    else:
        groups = [billets_dicts]

    # First group updates this invoice. The number is editable; keep the same
    # file while it's unchanged (so existing links stay valid), otherwise write a
    # fresh file named for the new number and drop the stale xlsx/pdf.
    first_billets = groups[0]
    new_numero = (data.numero or "").strip() or facture["numero"]
    renaming = new_numero != facture["numero"]
    first_name = (gen.invoice_filename(client, new_numero, invoice_date) if renaming
                  else facture["fichier"])

    # Extra chantier groups → brand-new invoices, numbered after the client's
    # highest once this invoice carries new_numero, so they never collide.
    extra = groups[1:]
    extra_start, extra_numeros = 0, []
    if extra:
        with closing(db.get_conn()) as conn:
            extra_start = _next_after_update(conn, facture, new_numero)
        extra_numeros = _numero_sequence(f"{client['prefix']}{extra_start:03d}", len(extra))

    # Every file (xlsx, and soffice for a pdf) is written BEFORE the write
    # transaction opens, so no external I/O runs while BEGIN IMMEDIATE blocks
    # every other writer. Any failure puts the files back as they were.
    files = _WrittenFiles()
    try:
        out_path = files.generate(
            client, new_numero, invoice_date, first_billets, filename=first_name,
            remise_pct=remise_pct, remise_montant=remise_montant,
        )
        extra_paths = [
            files.generate(client, numero, invoice_date, group_billets,
                           filename=gen.invoice_filename(client, numero, invoice_date),
                           remise_pct=remise_pct, remise_montant=remise_montant)
            for group_billets, numero in zip(extra, extra_numeros, strict=True)
        ]
    except Exception as e:
        files.undo()
        raise HTTPException(500, tr("err.regenerate_failed", detail=e)) from e
    invoices = [{"filename": out_path.name, "numero": new_numero}]
    invoices += [{"filename": p.name, "numero": n}
                 for p, n in zip(extra_paths, extra_numeros, strict=True)]

    try:
        _save_update(facture, new_numero, invoice_date, out_path.name, first_billets,
                     remise_pct, remise_montant,
                     [(numero, path.name, billets) for numero, path, billets
                      in zip(extra_numeros, extra_paths, extra, strict=True)],
                     extra_start)
    except HTTPException:
        files.undo()
        raise
    except Exception as e:
        log.exception("Enregistrement de la facture %s (id %s) impossible", new_numero, facture_id)
        files.undo()
        raise HTTPException(
            500, tr("err.invoice_not_saved_after_edit", numero=new_numero),
        ) from e

    # Only once the new state is committed: removing the old files earlier
    # would lose the invoice if the database write then failed.
    if renaming and facture["fichier"] != out_path.name:
        _remove_invoice_files(gen.OUTPUT_DIR / facture["fichier"])

    known_values.record(billets_dicts, invoice_date)
    return {"invoices": invoices, "split": len(invoices) > 1}


def _next_after_update(conn, facture: dict, new_numero: str) -> int:
    """One past the client's highest invoice number once `facture` is `new_numero`."""
    rows = conn.execute("SELECT numero FROM factures WHERE client_id = ? AND id != ?",
                        (facture["client_id"], facture["id"])).fetchall()
    numbers = [db._trailing_int(r[0]) for r in rows] + [db._trailing_int(new_numero)]
    return max((n for n in numbers if n is not None), default=0) + 1


def _save_update(facture: dict, new_numero: str, invoice_date: str, filename: str,
                 first_billets: list[dict], remise_pct: float, remise_montant: float,
                 extra: list[tuple[str, str, list[dict]]], extra_start: int) -> None:
    """One transaction for the billets update, any split invoices and the
    payment relink: links are positional, so billets saved without their relink
    would leave payments pointing at the wrong billet."""
    facture_id = facture["id"]
    with db.transaction() as conn:
        # The extra numbers were chosen before the lock; another write could have
        # taken them since. Refuse rather than save a duplicate number.
        if extra and _next_after_update(conn, facture, new_numero) != extra_start:
            raise HTTPException(409, tr("err.concurrent_invoice_created"))
        db.update_facture(
            facture_id, new_numero, invoice_date, filename, json.dumps(first_billets),
            remise_pct=remise_pct, remise_montant=remise_montant, conn=conn,
        )
        new_ids = [
            db.save_facture(
                facture["client_id"], numero, invoice_date, name,
                billets_json=json.dumps(group_billets),
                remise_pct=remise_pct, remise_montant=remise_montant, conn=conn,
            )["id"]
            for numero, name, group_billets in extra
        ]
        # Payment links are positional: re-seat them on the rewritten billets.
        payment_store.relink_after_invoice_edit(
            conn, [facture_id, *new_ids], {facture_id: facture.get("billets_json") or "[]"},
        )


def _remove_invoice_files(xlsx: Path) -> None:
    """Delete an invoice's xlsx and pdf. A leftover file is harmless, so a failure
    is logged rather than failing the request."""
    for stale in (xlsx, xlsx.with_suffix(".pdf")):
        try:
            stale.unlink(missing_ok=True)
        except OSError:
            log.warning("Suppression de %s impossible ; fichier laissé en place", stale,
                        exc_info=True)


@router.delete("/api/factures/{facture_id}")
def api_delete_facture(facture_id: int):
    """Delete an invoice, then its generated xlsx/pdf files.

    The database row goes first: if that fails, the invoice must still have its
    files. A file left behind after the row is gone is only logged.
    """
    facture = db.get_facture(facture_id)
    if not facture:
        raise HTTPException(404, tr("err.invoice_not_found"))

    try:
        db.delete_facture(facture_id)
    except Exception as e:
        log.exception("Suppression de la facture %s (id %s) impossible",
                      facture["numero"], facture_id)
        raise HTTPException(
            500, tr("err.invoice_not_deleted", numero=facture["numero"]),
        ) from e

    _remove_invoice_files(gen.OUTPUT_DIR / facture["fichier"])
    return {"ok": True}


class PayeIn(BaseModel):
    paye: bool


@router.patch("/api/factures/{facture_id}/paye")
def api_set_facture_paye(facture_id: int, data: PayeIn):
    """Mark an invoice paid/unpaid. Toggled from the home and history lists."""
    if not db.get_facture(facture_id):
        raise HTTPException(404, tr("err.invoice_not_found"))
    db.set_facture_paye(facture_id, data.paye)
    return {"ok": True, "paye": data.paye}


# Invoices are regenerated in place under the same filename, so the browser must
# never serve a cached copy of a download — otherwise an edited/fixed invoice
# keeps coming back as its stale predecessor.
_NO_CACHE_HEADERS = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}


@router.get("/api/factures/download/{filename}")
def api_download_facture(filename: str):
    safe_name = Path(filename).name
    file_path = gen.OUTPUT_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(404, tr("err.file_not_found"))
    return FileResponse(
        str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=safe_name,
        headers=_NO_CACHE_HEADERS,
    )


@router.get("/api/factures/download-pdf/{filename}")
def api_download_facture_pdf(filename: str):
    safe_name = Path(filename).name
    xlsx_path = gen.OUTPUT_DIR / safe_name
    if not xlsx_path.exists():
        raise HTTPException(404, tr("err.file_not_found"))

    try:
        pdf_path = gen.convert_to_pdf(xlsx_path)
    except Exception as e:
        raise HTTPException(500, tr("err.pdf_conversion_failed", detail=e)) from e

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=pdf_path.name,
        headers=_NO_CACHE_HEADERS,
    )

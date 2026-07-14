"""Discount and invoice-total math — the single source of truth for every total.

A billet and an invoice each carry a percentage (``remise_pct``) AND a fixed
amount (``remise_montant``). The percentage is always a share of the original
base (the billet's gross, or the invoice sous-total); the fixed amount comes
off after it. Nothing ever goes below zero. Discounts apply before taxes.

``facturo/web/static/js/discounts.js`` mirrors this module formula for formula
so the live preview in the browser always equals the generated invoice
(checked by ``tests/js/discounts.test.mjs`` against the shared fixtures).

Legacy v1 data carried a single ``remise_type`` ("percent" | "montant") plus
``remise_valeur``. :func:`normalize_discount` reads it when the v2 fields are
empty, and :func:`migrate_legacy_discounts` converts it once, in place.
"""

import json
import logging
import math
import sqlite3
from typing import NamedTuple

log = logging.getLogger(__name__)

TPS_RATE = 0.05
TVQ_RATE = 0.09975


class Totals(NamedTuple):
    sous_total: float             # sum of billet nets, as printed on the rows
    remise: float                 # remise_pct_amount + remise_montant_amount
    base_taxable: float
    tps: float
    tvq: float
    total: float                  # TOTAL DÛ
    remise_pct_amount: float      # dollars removed by the invoice percentage
    remise_montant_amount: float  # dollars removed by the invoice fixed amount


def _to_float(value) -> float:
    """Parse a stored/posted number; anything unusable resolves to 0.0."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def normalize_discount(obj: dict) -> tuple[float, float]:
    """Return ``(pct, montant)`` for a billet or facture dict, both >= 0.

    The v2 fields win whenever either is nonzero; otherwise the legacy
    ``remise_type``/``remise_valeur`` pair is translated.
    """
    pct = max(0.0, _to_float(obj.get("remise_pct")))
    montant = max(0.0, _to_float(obj.get("remise_montant")))
    if pct or montant:
        return pct, montant

    valeur = _to_float(obj.get("remise_valeur"))
    if valeur <= 0:
        return 0.0, 0.0
    match obj.get("remise_type"):
        case "percent":
            return valeur, 0.0
        case "montant":
            return 0.0, valeur
        case _:
            return 0.0, 0.0


def billet_gross(billet: dict) -> float:
    return _to_float(billet.get("quantite")) * _to_float(billet.get("taux"))


def billet_net(billet: dict) -> float:
    """Line total after the billet's own discount, never negative."""
    gross = billet_gross(billet)
    pct, montant = normalize_discount(billet)
    return max(0.0, gross - gross * pct / 100.0 - montant)


def invoice_totals(billets: list[dict], facture: dict) -> Totals:
    """Totals for an invoice's billets and its invoice-level discount fields.

    Each REMISE amount is clamped to what is left when it applies, so
    ``sous_total - remise_pct_amount - remise_montant_amount == base_taxable``
    holds exactly and the printed ledger adds up on paper.
    """
    sous_total = sum(billet_net(b) for b in billets)
    pct, montant = normalize_discount(facture)
    remise_pct_amount = max(0.0, min(sous_total * pct / 100.0, sous_total))
    after_pct = sous_total - remise_pct_amount
    remise_montant_amount = max(0.0, min(montant, after_pct))
    base_taxable = after_pct - remise_montant_amount
    tps = base_taxable * TPS_RATE
    tvq = base_taxable * TVQ_RATE
    return Totals(
        sous_total=sous_total,
        remise=remise_pct_amount + remise_montant_amount,
        base_taxable=base_taxable,
        tps=tps,
        tvq=tvq,
        total=base_taxable + tps + tvq,
        remise_pct_amount=remise_pct_amount,
        remise_montant_amount=remise_montant_amount,
    )


# ── One-time v1 -> v2 migration ─────────────────────────────────────────


def _has_legacy(obj: dict) -> bool:
    return bool(obj.get("remise_type")) or _to_float(obj.get("remise_valeur")) != 0


def _load_billets(raw) -> list | None:
    """Billets of a stored invoice, or None when the JSON is unusable."""
    try:
        billets = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return None
    return billets if isinstance(billets, list) else None


def _migrate_billet(billet: dict) -> bool:
    """Move a billet's own legacy discount into its v2 fields. True if changed."""
    if not _has_legacy(billet):
        return False
    billet["remise_pct"], billet["remise_montant"] = normalize_discount(billet)
    billet["remise_type"] = ""
    billet["remise_valeur"] = 0
    return True


def _fold_invoice_montant(billets: list[dict], montant: float) -> None:
    """v1 applied an invoice-level fixed amount in full to EVERY billet, each
    clamped to that billet's own net. Reproduce that per billet so totals stay
    identical — v2's invoice-level montant is spent once, which is not."""
    for billet in billets:
        fold = min(montant, billet_net(billet))
        billet["remise_montant"] = _to_float(billet.get("remise_montant")) + fold


def migrate_legacy_discounts(conn: sqlite3.Connection) -> None:
    """Convert every invoice's v1 single-kind discounts to v2 fields, in place.

    Legacy fields are cleared once converted, so a second run is a no-op. An
    invoice-level fixed amount with no readable billet to fold into is skipped
    (logged) and keeps its legacy fields. The caller owns the transaction (``schema.migrate`` commits).
    """
    rows = conn.execute(
        "SELECT id, billets_json, remise_type, remise_valeur, remise_pct, remise_montant "
        "FROM factures"
    ).fetchall()
    for fid, billets_json, rtype, rvaleur, rpct, rmontant in rows:
        facture = {
            "remise_type": rtype,
            "remise_valeur": rvaleur,
            "remise_pct": rpct,
            "remise_montant": rmontant,
        }
        loaded = _load_billets(billets_json)
        billets = [b for b in loaded or [] if isinstance(b, dict)]
        billets_changed = any([_migrate_billet(b) for b in billets])

        pct, montant = normalize_discount(facture)
        invoice_legacy = _has_legacy(facture)
        # normalize_discount only returns a montant from legacy fields when both
        # v2 columns are empty — that is the v1 per-billet amount to fold.
        must_fold = invoice_legacy and montant > 0 and not (_to_float(rpct) or _to_float(rmontant))
        if must_fold and not billets:
            # Nothing to fold into (unreadable or empty billets). Converting would
            # erase the amount, so the row keeps its legacy fields, which
            # normalize_discount still honours on every read.
            log.warning(
                "Facture %s : remise fixe v1 conservée telle quelle (billets illisibles "
                "ou absents, rien à convertir).", fid,
            )
            continue
        if must_fold:
            _fold_invoice_montant(billets, montant)
            montant = 0.0
            billets_changed = billets_changed or bool(billets)

        new_json = json.dumps(loaded) if billets_changed else billets_json
        if invoice_legacy:
            conn.execute(
                "UPDATE factures SET remise_type = '', remise_valeur = 0, "
                "remise_pct = ?, remise_montant = ?, billets_json = ? WHERE id = ?",
                (pct, montant, new_json, fid),
            )
        elif billets_changed:
            conn.execute(
                "UPDATE factures SET billets_json = ? WHERE id = ?", (new_json, fid)
            )

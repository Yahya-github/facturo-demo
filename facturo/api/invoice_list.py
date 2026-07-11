"""Invoice list endpoint (history, home, filters).

`GET /api/factures` returns every invoice row plus the summary fields the
History/Home filters need client-side: totals, billet counts, payment status
and a folded search blob. The web history filter reads these exact field names.
"""

import json
import logging

from fastapi import APIRouter

from facturo.core import billet_fields
from facturo.core import database as db
from facturo.invoicing.discounts import invoice_totals
from facturo.payments import store

log = logging.getLogger(__name__)

router = APIRouter()

STATUT_PAYEE = "payee"
STATUT_PARTIELLE = "partielle"
STATUT_NON_PAYEE = "non_payee"

_BILLET_SEARCH_FIELDS = ("chantier", "plaque", "numero_billet", "description")


def parse_billets(raw) -> list[dict]:
    """Decode `billets_json` defensively: anything unusable becomes []."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [b for b in data if isinstance(b, dict)]


def _totals(billets: list[dict], facture: dict) -> tuple[float, float]:
    """(total_ht, total_ttc) rounded to cents; zeros when there is nothing to total."""
    if not billets:
        return 0.0, 0.0
    try:
        t = invoice_totals(billets, facture)
    except (TypeError, ValueError, KeyError):
        # A corrupt billet must not take the whole list down; the invoice
        # still shows (at 0 $) and the cause is logged for diagnosis.
        log.warning("Totaux impossibles pour la facture %s", facture.get("id"), exc_info=True)
        return 0.0, 0.0
    return round(t.base_taxable, 2), round(t.total, 2)


def _nb_payes(facture_id: int, nb_billets: int, paid_billets: dict) -> int:
    return sum(1 for i in range(nb_billets) if (facture_id, i) in paid_billets)


def statut_paiement(paye, nb_payes: int, nb_billets: int) -> str:
    """Contract order: `paye` wins, then strictly partial coverage, else unpaid.

    Full billet coverage without `paye` is deliberately "non_payee": only the
    `paye` column (set by the user, or by the app when payments cover every
    billet) flips an invoice to "payee", so the list never contradicts it.
    """
    if paye:
        return STATUT_PAYEE
    if 0 < nb_payes < nb_billets:
        return STATUT_PARTIELLE
    return STATUT_NON_PAYEE


def search_blob(facture: dict, billets: list[dict]) -> str:
    """Each field folded on its own, then joined with a single space."""
    parts = [facture.get("numero"), facture.get("client_nom"), facture.get("client_ref")]
    for b in billets:
        parts.extend(b.get(k, "") for k in _BILLET_SEARCH_FIELDS)
    folded = (billet_fields.fold(p) for p in parts if p)
    return " ".join(f for f in folded if f)


def summarize(facture: dict, paid_billets: dict) -> dict:
    """A new dict: the invoice row plus its list/filter summary fields."""
    billets = parse_billets(facture.get("billets_json"))
    nb_billets = len(billets)
    nb_payes = _nb_payes(facture["id"], nb_billets, paid_billets)
    total_ht, total_ttc = _totals(billets, facture)
    return {
        **facture,
        "total_ht": total_ht,
        "total_ttc": total_ttc,
        "nb_billets": nb_billets,
        "nb_billets_payes": nb_payes,
        "statut_paiement": statut_paiement(facture.get("paye"), nb_payes, nb_billets),
        "search_blob": search_blob(facture, billets),
    }


@router.get("/api/factures")
def api_list_factures(client_id: int | None = None):
    factures = db.list_factures(client_id)
    # Once per request, never per invoice (no N+1). Called through the module
    # so the payments workstream -- and tests -- can swap the implementation.
    paid_billets = store.paid_billets()
    return [summarize(f, paid_billets) for f in factures]

"""Curated chantier / plaque vocabulary (autocomplete + AI correction)."""



from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from facturo.core import known_values

router = APIRouter()


# ── Valeurs connues (chantiers, plaques) ────────────────
# The shop's own vocabulary: what the billet form autocompletes from, and what
# an AI reading gets corrected against. Curated by hand here because a value
# nobody can remove becomes an authority forever — see known_values.py.


class KnownValueIn(BaseModel):
    kind: str = ""          # 'chantier' | 'plaque'; ignored when renaming
    valeur: str | None = None
    hidden: bool | None = None


class MergeIn(BaseModel):
    into_id: int


@router.get("/api/known-values")
def api_list_known_values(kind: str | None = None):
    return known_values.list_all(kind)


@router.post("/api/known-values")
def api_add_known_value(data: KnownValueIn):
    """Add a value by hand — typically a new truck, before its first billet."""
    try:
        return known_values.add(data.kind, data.valeur or "")
    except known_values.KnownValueError as e:
        raise HTTPException(400, str(e)) from e


@router.put("/api/known-values/{kv_id}")
def api_update_known_value(kv_id: int, data: KnownValueIn):
    """Rename and/or hide a value. Past invoices keep the spelling they were
    generated with — billets_json records what was actually billed."""
    try:
        return known_values.update(kv_id, data.valeur, data.hidden)
    except known_values.KnownValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/api/known-values/{kv_id}")
def api_delete_known_value(kv_id: int):
    known_values.remove(kv_id)
    return {"ok": True}


@router.post("/api/known-values/{kv_id}/merge")
def api_merge_known_values(kv_id: int, data: MergeIn):
    """Declare two values the same thing, keeping the target."""
    try:
        known_values.merge(kv_id, data.into_id)
    except known_values.KnownValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}

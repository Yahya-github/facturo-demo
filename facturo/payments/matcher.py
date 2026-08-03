"""Billets listed on a payment vs. the billets already invoiced. Pure.

Keys, in order: the billet number (every wrap candidate is tried), then date +
folded plate + quantity (±0.01). Price and montant are never keys: rates carry
a diesel surcharge and coincide across unrelated billets. Client / chantier are
not keys either — one quittance pays billets of several end clients, and one
truck hauls for several clients.

A billet already linked to another payment is reported as a duplicate
("doublon"), never silently re-linked.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from facturo.core.billet_fields import fold, tidy_billet_number, tidy_plate, to_number
from facturo.payments.parser import ParsedLigne

# Quantities are hours to the quarter; 0.01 absorbs float noise, nothing more.
QTY_TOLERANCE = 0.01 + 1e-9


@dataclass(frozen=True)
class BilletRef:
    facture_id: int
    billet_index: int             # position in the facture's billets_json list
    numero_billet: str            # tidy_billet_number()'d
    date_billet: str              # as stored (ISO from the form)
    plaque: str                   # tidy_plate()'d
    quantite: float


@dataclass(frozen=True)
class Candidate:
    facture_id: int
    billet_index: int
    raison: str                   # "numero" (ambiguous number) | "plaque" | "date"


@dataclass(frozen=True)
class MatchResult:
    ligne: ParsedLigne
    statut: str                   # "lie" | "doublon" | "non_lie"
    facture_id: int | None
    billet_index: int | None
    methode: str                  # "numero" | "date_plaque" | ""
    doublon_paiement_id: int | None
    candidats: tuple[Candidate, ...]   # only when statut == "non_lie"


def billets_from_json(raw: str | None) -> list:
    """The billet list stored in factures.billets_json; [] when missing/invalid."""
    try:
        billets = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return billets if isinstance(billets, list) else []


def billet_ref(facture_id: int, billet_index: int, billet: Mapping) -> BilletRef:
    """One invoiced billet, normalized for matching."""
    return BilletRef(
        facture_id=facture_id,
        billet_index=billet_index,
        numero_billet=tidy_billet_number(billet.get("numero_billet") or ""),
        date_billet=str(billet.get("date_billet") or "").strip(),
        plaque=tidy_plate(billet.get("plaque") or ""),
        quantite=to_number(billet.get("quantite")),
    )


def build_index(factures: Sequence[Mapping]) -> list[BilletRef]:
    """One BilletRef per billet of every facture ({"id", "billets_json"} rows).

    Missing, blank or invalid billets_json contributes nothing; never raises.
    """
    return [
        billet_ref(facture["id"], i, b)
        for facture in factures
        for i, b in enumerate(billets_from_json(facture.get("billets_json")))
        if isinstance(b, dict)
    ]


def _same_plate(a: str, b: str) -> bool:
    return bool(fold(a)) and fold(a) == fold(b)


def _date_plate_qty(ligne: ParsedLigne, ref: BilletRef) -> bool:
    return (
        ligne.quantite is not None
        and bool(ligne.date_billet)
        and ligne.date_billet == ref.date_billet
        and _same_plate(ligne.plaque, ref.plaque)
        and abs(ligne.quantite - ref.quantite) <= QTY_TOLERANCE
    )


def _resolve(ligne: ParsedLigne, index: Sequence[BilletRef]) -> tuple[list[BilletRef], str]:
    """The billets this ligne points at, and by which rule."""
    numeros = {tidy_billet_number(c) for c in ligne.numero_candidates} - {""}
    by_numero = [ref for ref in index if ref.numero_billet and ref.numero_billet in numeros]
    if len(by_numero) > 1:
        # Same number on several invoices: let date/plate/qty break the tie.
        narrowed = [ref for ref in by_numero if _date_plate_qty(ligne, ref)]
        return (narrowed if len(narrowed) == 1 else by_numero), "numero"
    if by_numero:
        return by_numero, "numero"
    return [ref for ref in index if _date_plate_qty(ligne, ref)], "date_plaque"


def _candidates(ligne: ParsedLigne, index: Sequence[BilletRef],
                ambiguous: Sequence[BilletRef]) -> tuple[Candidate, ...]:
    ranked = [Candidate(r.facture_id, r.billet_index, "numero") for r in ambiguous]
    ranked += [Candidate(r.facture_id, r.billet_index, "plaque")
               for r in index if _same_plate(ligne.plaque, r.plaque)]
    ranked += [Candidate(r.facture_id, r.billet_index, "date")
               for r in index
               if ligne.date_billet and r.date_billet == ligne.date_billet
               and not _same_plate(ligne.plaque, r.plaque)]
    seen: set[tuple[int, int]] = set()
    unique = []
    for c in ranked:
        if (c.facture_id, c.billet_index) not in seen:
            seen.add((c.facture_id, c.billet_index))
            unique.append(c)
    return tuple(unique)


def match_ligne(
    ligne: ParsedLigne,
    index: Sequence[BilletRef],
    liens_existants: Mapping[tuple[int, int], int],
) -> MatchResult:
    refs, methode = _resolve(ligne, index)
    if len(refs) != 1:
        ambiguous = refs if methode == "numero" else ()
        return MatchResult(ligne, "non_lie", None, None, "", None,
                           _candidates(ligne, index, ambiguous))
    ref = refs[0]
    key = (ref.facture_id, ref.billet_index)
    if key in liens_existants:
        return MatchResult(ligne, "doublon", ref.facture_id, ref.billet_index, "",
                           liens_existants[key], ())
    return MatchResult(ligne, "lie", ref.facture_id, ref.billet_index, methode, None, ())


def match_lignes(
    lignes: Sequence[ParsedLigne],
    index: Sequence[BilletRef],
    liens_existants: Mapping[tuple[int, int], int],
) -> list[MatchResult]:
    """One result per ligne, same order.

    `liens_existants` maps (facture_id, billet_index) -> paiement_id for every
    billet already linked to some OTHER payment; used for doublon detection.
    """
    return [match_ligne(ligne, index, liens_existants) for ligne in lignes]

"""Unit tests for payments.matcher — billets found on a payment vs. the fleet's
billet index built from `factures.billets_json`.

Pure: no database, no parser text parsing. Lines are built directly as
`ParsedLigne` and the index directly as `BilletRef`/raw facture dicts, so a
match decision can be tested in complete isolation from PDF text quirks.

See changes/team-c.md for the exact matching algorithm this locks down:
numero (trying every candidate) -> date + plate (folded) + quantity (±0.01) ->
otherwise unmatched with ranked candidates. Price/montant is never a matching
key. A billet already linked to another payment is reported as a duplicate,
never silently re-linked.
"""

import json

import pytest

from facturo.payments import matcher
from facturo.payments.parser import ParsedLigne


def ligne(numero="1000", candidates=None, date="2026-09-12", plaque="P888777",
          quantite=8.0, prix=100.0, montant=800.0) -> ParsedLigne:
    return ParsedLigne(
        numero_billet=numero,
        numero_candidates=tuple(candidates) if candidates else (numero,),
        date_billet=date,
        plaque=plaque,
        quantite=quantite,
        prix=prix,
        montant=montant,
    )


def facture_row(id_, billets):
    return {"id": id_, "billets_json": json.dumps(billets)}


def billet(numero="1000", date="2026-09-12", plaque="P888777", quantite=8.0):
    return {"numero_billet": numero, "date_billet": date, "plaque": plaque, "quantite": quantite}


# ── build_index ────────────────────────────────────────────────────────

def test_build_index_produces_one_entry_per_billet_with_stable_index():
    factures = [
        facture_row(1, [billet(numero="100"), billet(numero="101")]),
        facture_row(2, [billet(numero="200")]),
    ]
    index = matcher.build_index(factures)
    pairs = {(r.facture_id, r.billet_index): r.numero_billet for r in index}
    assert pairs == {(1, 0): "100", (1, 1): "101", (2, 0): "200"}


def test_build_index_normalizes_plate_and_numero():
    factures = [facture_row(1, [billet(numero="  0102  ", plaque="p 88 87 77")])]
    index = matcher.build_index(factures)
    assert index[0].numero_billet == "0102"
    assert index[0].plaque == "P888777"


@pytest.mark.parametrize("billets_json", [None, "", "not json", "[]"])
def test_build_index_tolerates_missing_or_blank_billets_json(billets_json):
    factures = [{"id": 1, "billets_json": billets_json}]
    assert matcher.build_index(factures) == []


# ── Exact numero match ───────────────────────────────────────────────────

def test_exact_numero_match_links_the_billet():
    index = matcher.build_index([facture_row(1, [billet(numero="50210")])])
    [result] = matcher.match_lignes([ligne(numero="50210")], index, {})
    assert result.statut == "lie"
    assert result.methode == "numero"
    assert result.facture_id == 1
    assert result.billet_index == 0


def test_wrapped_numero_matches_via_either_candidate():
    """The line's numero_candidates carries both the unjoined and joined
    forms; whichever one is the real billet number must still match."""
    index = matcher.build_index([facture_row(7, [billet(numero="502113")])])
    [result] = matcher.match_lignes(
        [ligne(numero="50211", candidates=("50211", "502113"))], index, {},
    )
    assert result.statut == "lie"
    assert result.methode == "numero"
    assert result.facture_id == 7
    assert result.billet_index == 0


# ── date + plate + quantity fallback ─────────────────────────────────────

def test_date_plate_qty_fallback_when_numero_is_unknown_to_the_fleet():
    """The real-world quittance case: the payer's own billet numbers are not
    the numbers already on file, so date+plate+qty is what actually links
    them."""
    index = matcher.build_index([
        facture_row(3, [billet(numero="999999", date="2026-09-16",
                                plaque="p888777", quantite=14.25)]),
    ])
    incoming = ligne(numero="60401", candidates=("60401", "604019"),
                      date="2026-09-16", plaque="P888777", quantite=14.25)
    [result] = matcher.match_lignes([incoming], index, {})
    assert result.statut == "lie"
    assert result.methode == "date_plaque"
    assert result.facture_id == 3
    assert result.billet_index == 0


@pytest.mark.parametrize("delta, expect_match", [(0.0, True), (0.01, True), (0.02, False)])
def test_quantity_tolerance_is_one_hundredth(delta, expect_match):
    index = matcher.build_index([
        facture_row(1, [billet(numero="999", date="2026-09-16", plaque="P888777", quantite=14.25)]),
    ])
    incoming = ligne(numero="unknown-number", date="2026-09-16", plaque="P888777",
                      quantite=14.25 + delta)
    [result] = matcher.match_lignes([incoming], index, {})
    assert (result.statut == "lie") is expect_match


def test_plate_normalization_ignores_case_and_spacing():
    """DB plates carry a space ('P 888777'); parsed lines never do. Only the
    folded (upper, alnum-only) form is compared."""
    index = matcher.build_index([
        facture_row(1, [billet(numero="999", date="2026-09-16", plaque="P 888777", quantite=9.0)]),
    ])
    incoming = ligne(numero="unknown", date="2026-09-16", plaque="p888777", quantite=9.0)
    [result] = matcher.match_lignes([incoming], index, {})
    assert result.statut == "lie"
    assert result.methode == "date_plaque"


def test_never_matches_on_quantity_alone_when_date_and_plate_both_differ():
    """A coincidentally identical quantity must not be enough by itself —
    the diesel surcharge means price/amount can coincide across unrelated
    billets, and quantity alone is exactly as unsafe."""
    index = matcher.build_index([
        facture_row(1, [billet(numero="999", date="2026-09-01", plaque="L111111", quantite=9.0)]),
    ])
    incoming = ligne(numero="unknown", date="2026-09-30", plaque="L222222", quantite=9.0)
    [result] = matcher.match_lignes([incoming], index, {})
    assert result.statut == "non_lie"


def test_never_matches_on_price_or_amount():
    """montant/prix are not read by the matcher at all — proven by a pair of
    billets that share date+plate+qty but wildly different montant/prix,
    which must still match (price plays no role in the decision either way)."""
    index = matcher.build_index([
        facture_row(1, [billet(numero="999", date="2026-09-16", plaque="P888777", quantite=9.0)]),
    ])
    incoming = ligne(numero="unknown", date="2026-09-16", plaque="P888777", quantite=9.0,
                      prix=999999.99, montant=8999999.91)
    [result] = matcher.match_lignes([incoming], index, {})
    assert result.statut == "lie"


# ── Duplicate detection ──────────────────────────────────────────────────

def test_billet_already_linked_to_another_payment_is_reported_as_doublon():
    index = matcher.build_index([facture_row(1, [billet(numero="50210")])])
    liens_existants = {(1, 0): 42}  # already claimed by paiement_id 42
    [result] = matcher.match_lignes([ligne(numero="50210")], index, liens_existants)
    assert result.statut == "doublon"
    assert result.doublon_paiement_id == 42
    # informative, but this ligne must NOT be treated as a fresh link
    assert result.facture_id == 1
    assert result.billet_index == 0
    assert result.methode == ""


def test_doublon_also_detected_via_the_date_plaque_fallback():
    index = matcher.build_index([
        facture_row(1, [billet(numero="999", date="2026-09-16", plaque="P888777", quantite=9.0)]),
    ])
    liens_existants = {(1, 0): 7}
    incoming = ligne(numero="unrelated", date="2026-09-16", plaque="P888777", quantite=9.0)
    [result] = matcher.match_lignes([incoming], index, liens_existants)
    assert result.statut == "doublon"
    assert result.doublon_paiement_id == 7


# ── Unmatched: ranked candidates ─────────────────────────────────────────

def test_unmatched_ranks_same_plate_candidates():
    index = matcher.build_index([
        facture_row(1, [billet(numero="999", date="2026-09-01", plaque="P888777", quantite=5.0)]),
    ])
    incoming = ligne(numero="unknown", date="2026-09-30", plaque="P888777", quantite=99.0)
    [result] = matcher.match_lignes([incoming], index, {})
    assert result.statut == "non_lie"
    assert result.facture_id is None and result.billet_index is None
    assert any(c.facture_id == 1 and c.billet_index == 0 and c.raison == "plaque"
               for c in result.candidats)


def test_unmatched_ranks_same_date_candidates():
    index = matcher.build_index([
        facture_row(1, [billet(numero="999", date="2026-09-16", plaque="L000000", quantite=5.0)]),
    ])
    incoming = ligne(numero="unknown", date="2026-09-16", plaque="P888777", quantite=99.0)
    [result] = matcher.match_lignes([incoming], index, {})
    assert result.statut == "non_lie"
    assert any(c.facture_id == 1 and c.billet_index == 0 and c.raison == "date"
               for c in result.candidats)


def test_unmatched_with_no_plate_or_date_overlap_has_no_candidates():
    index = matcher.build_index([
        facture_row(1, [billet(numero="999", date="2026-01-01", plaque="L000000", quantite=5.0)]),
    ])
    incoming = ligne(numero="unknown", date="2026-09-30", plaque="P888777", quantite=99.0)
    [result] = matcher.match_lignes([incoming], index, {})
    assert result.statut == "non_lie"
    assert result.candidats == ()


# ── Multi-client quittance: matcher is indifferent to client identity ────

def test_resolves_each_line_independently_even_when_a_plate_is_shared_across_clients():
    """One truck can haul for several clients; the matcher only ever sees
    facture_id/billet_index/numero/date/plate/qty, never a client name, and
    must resolve two lines that reference the same truck to their own
    correct, distinct invoices."""
    index = matcher.build_index([
        facture_row(10, [billet(numero="70001", date="2026-09-16", plaque="P888777", quantite=9.0)]),
        facture_row(20, [billet(numero="70002", date="2026-09-17", plaque="P888777", quantite=9.0)]),
    ])
    lignes = [
        ligne(numero="70001", date="2026-09-16", plaque="P888777", quantite=9.0),
        ligne(numero="70002", date="2026-09-17", plaque="P888777", quantite=9.0),
    ]
    results = matcher.match_lignes(lignes, index, {})
    assert [(r.statut, r.facture_id, r.billet_index) for r in results] == [
        ("lie", 10, 0),
        ("lie", 20, 0),
    ]


def test_match_lignes_preserves_input_order_and_count():
    index = matcher.build_index([facture_row(1, [billet(numero="1"), billet(numero="2")])])
    lignes = [ligne(numero="2"), ligne(numero="unknown"), ligne(numero="1")]
    results = matcher.match_lignes(lignes, index, {})
    assert len(results) == 3
    assert [r.ligne.numero_billet for r in results] == ["2", "unknown", "1"]
    assert [r.statut for r in results] == ["lie", "non_lie", "lie"]


# ── Ambiguous numero (added by implementer, review follow-up) ─────────────

def test_numero_on_two_invoices_is_narrowed_by_date_plate_qty():
    index = matcher.build_index([
        facture_row(1, [billet(numero="80001", date="2026-09-01", quantite=5.0)]),
        facture_row(2, [billet(numero="80001", date="2026-09-02", quantite=6.0)]),
    ])
    [result] = matcher.match_lignes(
        [ligne(numero="80001", date="2026-09-02", quantite=6.0)], index, {})
    assert (result.statut, result.facture_id, result.methode) == ("lie", 2, "numero")


def test_numero_on_two_invoices_that_stays_ambiguous_is_not_linked():
    """Same number, same date/plate/qty on two invoices: never guess — report
    both as "numero" candidates, ranked first."""
    index = matcher.build_index([
        facture_row(1, [billet(numero="80001")]),
        facture_row(2, [billet(numero="80001")]),
    ])
    [result] = matcher.match_lignes([ligne(numero="80001")], index, {})
    assert result.statut == "non_lie"
    assert result.facture_id is None
    assert [(c.facture_id, c.raison) for c in result.candidats[:2]] == [(1, "numero"), (2, "numero")]
    assert len({(c.facture_id, c.billet_index) for c in result.candidats}) == len(result.candidats)

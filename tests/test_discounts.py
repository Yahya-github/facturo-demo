"""Unit tests for invoicing/discounts.py — the single source of truth for
every billet and invoice total once a billet or an invoice can carry BOTH a
percentage and a fixed-amount discount at the same time.

Contract under test (see changes/team-a.md for the full interface note):
  * discounts.normalize_discount(obj) -> (pct, montant)
  * discounts.billet_net(billet) -> float
  * discounts.invoice_totals(billets, facture) -> Totals

Rules, in order:
  1. A discount is a percent AND a fixed amount together, not one or the
     other. Percent is always a share of the ORIGINAL gross/subtotal, never
     of an already-reduced balance.
  2. Fixed amount is subtracted once the percent has been taken off.
  3. Nothing a discount produces may go below zero.
  4. Legacy single-kind fields (remise_type/remise_valeur) are read only when
     the v2 fields (remise_pct/remise_montant) are both zero/absent.

Every numeric case here is mirrored in tests/fixtures/discount_cases.json so
the same inputs/outputs are also exercised by the JS math in
tests/js/discounts.test.mjs — Python and the browser preview must agree to
the cent.
"""

import json
from pathlib import Path

import pytest

from facturo.invoicing import discounts

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "discount_cases.json").read_text()
)

EPSILON = 1e-6


# ── normalize_discount ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "obj, expected",
    [
        ({}, (0.0, 0.0)),
        ({"remise_pct": 0, "remise_montant": 0}, (0.0, 0.0)),
        ({"remise_pct": 10}, (10.0, 0.0)),
        ({"remise_montant": 25}, (0.0, 25.0)),
        ({"remise_pct": 10, "remise_montant": 25}, (10.0, 25.0)),
        # legacy fallback: only read when v2 fields are both zero/absent
        ({"remise_type": "percent", "remise_valeur": 15}, (15.0, 0.0)),
        ({"remise_type": "montant", "remise_valeur": 40}, (0.0, 40.0)),
        ({"remise_type": "", "remise_valeur": 0}, (0.0, 0.0)),
        ({"remise_type": "percent", "remise_valeur": 0}, (0.0, 0.0)),
        # v2 wins outright over legacy, even when legacy looks "bigger"
        (
            {"remise_type": "percent", "remise_valeur": 99, "remise_pct": 10, "remise_montant": 0},
            (10.0, 0.0),
        ),
        # unknown/garbage legacy type -> no discount, not a crash
        ({"remise_type": "bogus", "remise_valeur": 50}, (0.0, 0.0)),
        # defensive: negative values never leak through
        ({"remise_pct": -10, "remise_montant": -5}, (0.0, 0.0)),
        ({"remise_type": "percent", "remise_valeur": -20}, (0.0, 0.0)),
        # defensive: non-numeric legacy valeur must not raise
        ({"remise_type": "percent", "remise_valeur": "beaucoup"}, (0.0, 0.0)),
    ],
)
def test_normalize_discount(obj, expected):
    pct, montant = discounts.normalize_discount(obj)
    assert pct == pytest.approx(expected[0])
    assert montant == pytest.approx(expected[1])


def test_normalize_discount_returns_a_two_tuple_of_floats():
    result = discounts.normalize_discount({"remise_pct": "10", "remise_montant": "5"})
    assert isinstance(result, tuple)
    assert len(result) == 2
    pct, montant = result
    assert isinstance(pct, float)
    assert isinstance(montant, float)


# ── billet_net ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "case", [c for c in FIXTURES if len(c["billets"]) == 1], ids=lambda c: c["name"]
)
def test_billet_net_single_billet_cases(case):
    net = discounts.billet_net(case["billets"][0])
    assert net == pytest.approx(case["expected"]["billet_nets"][0], abs=EPSILON)


def test_billet_net_percent_is_share_of_original_gross_not_of_remainder():
    """1000 gross, 10% + $100 must remove 100 + 100 = 200, landing on 800 --
    never (1000-100)*10% = 90 computed against the already-reduced balance."""
    billet = {"quantite": 10, "taux": 100, "remise_pct": 10, "remise_montant": 100}
    assert discounts.billet_net(billet) == pytest.approx(800.0, abs=EPSILON)


def test_billet_net_clamps_at_zero_never_negative():
    billet = {"quantite": 1, "taux": 100, "remise_pct": 50, "remise_montant": 80}
    assert discounts.billet_net(billet) == pytest.approx(0.0, abs=EPSILON)
    assert discounts.billet_net(billet) >= 0.0


def test_billet_net_handles_missing_discount_keys_entirely():
    """A raw legacy billet dict that never had remise_pct/remise_montant keys
    at all (not even zeroed) must not raise and must equal the plain gross."""
    billet = {"quantite": 5, "taux": 40}
    assert discounts.billet_net(billet) == pytest.approx(200.0, abs=EPSILON)


def test_billet_net_handles_zero_quantite_or_taux():
    assert discounts.billet_net({"quantite": 0, "taux": 100}) == 0.0
    assert discounts.billet_net({"quantite": 5, "taux": 0}) == 0.0


def test_billet_net_never_negative_even_with_negative_gross_inputs():
    """Defensive: a malformed negative quantite/taux must still clamp to 0,
    not silently produce a negative line total."""
    assert discounts.billet_net({"quantite": -5, "taux": 100}) >= 0.0


# ── invoice_totals ──────────────────────────────────────────────────────


@pytest.mark.parametrize("case", FIXTURES, ids=lambda c: c["name"])
def test_invoice_totals_matches_fixture(case):
    totals = discounts.invoice_totals(case["billets"], case["facture"])
    expected = case["expected"]

    assert totals.sous_total == pytest.approx(expected["sous_total"], abs=EPSILON)
    assert totals.remise == pytest.approx(expected["remise"], abs=EPSILON)
    assert totals.base_taxable == pytest.approx(expected["base_taxable"], abs=EPSILON)
    assert totals.tps == pytest.approx(expected["tps"], abs=EPSILON)
    assert totals.tvq == pytest.approx(expected["tvq"], abs=EPSILON)
    assert totals.total == pytest.approx(expected["total"], abs=EPSILON)

    # v2 breakdown fields, needed by the xlsx "REMISE (x %):" / "REMISE:" lines
    assert totals.remise_pct_amount == pytest.approx(expected["remise_pct_amount"], abs=EPSILON)
    assert totals.remise_montant_amount == pytest.approx(
        expected["remise_montant_amount"], abs=EPSILON
    )


def test_invoice_montant_is_subtracted_once_not_per_billet():
    """The exact regression the v1 -> v2 change guards against: an
    invoice-level fixed discount must hit the invoice ONCE, never be applied
    in full to every billet independently."""
    billets = [{"quantite": 5, "taux": 100} for _ in range(3)]
    facture = {"remise_montant": 30}
    totals = discounts.invoice_totals(billets, facture)
    assert totals.sous_total == pytest.approx(1500.0, abs=EPSILON)
    assert totals.remise_montant_amount == pytest.approx(30.0, abs=EPSILON)
    assert totals.base_taxable == pytest.approx(1470.0, abs=EPSILON)
    # the v1 bug's result (30 removed from every one of the 3 billets) must
    # NOT appear here:
    assert totals.base_taxable != pytest.approx(1410.0, abs=EPSILON)


def test_invoice_totals_percent_then_fixed_amount_order():
    """10% then $20 fixed, once: sous_total 1000 -> -100 (pct) -> -20 (fixed)
    -> base 880. Order matters for what "remise_pct_amount" reports, not for
    the arithmetic identity below, which must always hold exactly."""
    billets = [{"quantite": 10, "taux": 100}]
    facture = {"remise_pct": 10, "remise_montant": 20}
    totals = discounts.invoice_totals(billets, facture)
    assert totals.remise_pct_amount == pytest.approx(100.0, abs=EPSILON)
    assert totals.remise_montant_amount == pytest.approx(20.0, abs=EPSILON)
    assert totals.base_taxable == pytest.approx(880.0, abs=EPSILON)


def test_invoice_totals_ledger_reconciles_exactly():
    """SOUS-TOTAL minus the two printed REMISE lines must equal base_taxable
    to the cent for every case -- this is a customer-facing document, the
    printed subtraction must add up on the page, even when a fixed discount
    is clamped down because it would otherwise overshoot."""
    for case in FIXTURES:
        totals = discounts.invoice_totals(case["billets"], case["facture"])
        reconciled = totals.sous_total - totals.remise_pct_amount - totals.remise_montant_amount
        assert reconciled == pytest.approx(totals.base_taxable, abs=EPSILON), case["name"]


def test_invoice_totals_base_taxable_never_negative_when_montant_overshoots():
    billets = [{"quantite": 1, "taux": 100}]
    facture = {"remise_pct": 0, "remise_montant": 500}
    totals = discounts.invoice_totals(billets, facture)
    assert totals.base_taxable == 0.0
    assert totals.total == 0.0
    # the displayed montant amount can never exceed what was actually there
    assert totals.remise_montant_amount <= totals.sous_total + EPSILON


def test_invoice_totals_empty_billets_list_does_not_crash():
    totals = discounts.invoice_totals([], {"remise_pct": 10, "remise_montant": 5})
    assert totals.sous_total == 0.0
    assert totals.base_taxable == 0.0
    assert totals.total == 0.0


def test_invoice_totals_tax_rates_are_the_quebec_statutory_rates():
    totals = discounts.invoice_totals([{"quantite": 1, "taux": 1000}], {})
    assert totals.tps == pytest.approx(1000 * discounts.TPS_RATE, abs=EPSILON)
    assert totals.tvq == pytest.approx(1000 * discounts.TVQ_RATE, abs=EPSILON)
    assert discounts.TPS_RATE == pytest.approx(0.05)
    assert discounts.TVQ_RATE == pytest.approx(0.09975)


def test_totals_namedtuple_keeps_backward_compatible_field_order():
    """Other workstreams (filters/summary) unpack Totals positionally; the
    original six fields must keep their original order, with the two new v2
    breakdown fields appended at the end."""
    totals = discounts.invoice_totals([{"quantite": 2, "taux": 50}], {"remise_pct": 10})
    sous_total, remise, base_taxable, tps, tvq, total = totals[:6]
    assert sous_total == totals.sous_total
    assert remise == totals.remise
    assert base_taxable == totals.base_taxable
    assert tps == totals.tps
    assert tvq == totals.tvq
    assert total == totals.total
    assert hasattr(totals, "remise_pct_amount")
    assert hasattr(totals, "remise_montant_amount")

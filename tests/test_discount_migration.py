"""Tests for the one-time v1 -> v2 discount migration.

`discounts.migrate_legacy_discounts(conn)` converts every invoice's legacy
single-kind discount (`remise_type` in {"", "percent", "montant"} +
`remise_valeur`) into the v2 pair (`remise_pct`, `remise_montant`), both at
the invoice level (`factures` columns) and inside each billet
(`billets_json`).

The one non-obvious rule (see docs/plan "A. Discounts"): a v1 invoice-level
`"montant"` discount was applied IN FULL, independently, to every billet
(clamped to that billet's own net) -- never subtracted once from the
invoice. So it cannot become `factures.remise_montant` (which is spent once,
per the v2 rules in test_discounts.py). Instead it is folded into EACH
billet's own `remise_montant` as the effective cut
`min(M, billet_net_after_its_own_discount)`, and the invoice-level
`remise_montant` is left at 0. A v1 invoice-level `"percent"` discount has no
such per-billet mechanic and maps straight across to `factures.remise_pct`.

Legacy fields are cleared (`remise_type=''`, `remise_valeur=0`) once
converted, at both levels, so `normalize_discount` never has to choose
between two live sources for the same row again, and so a second migration
run is a pure no-op (idempotence).

Every synthetic case below is checked two ways:
  1. Field-level: the exact v2 columns/JSON the migration must produce.
  2. Total-level: `discounts.invoice_totals()` on the MIGRATED data must
     reproduce the totals of a frozen, hand-verified copy of the v1 math
     (the "oracle" below), to the cent, for every invoice -- including a
     real legacy database when FACTURO_LEGACY_DB points at one.
"""

import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from facturo.core import schema
from facturo.invoicing import discounts

EPSILON = 1e-6

# A real pre-v2 database to check parity against, when one is available.
# Point FACTURO_LEGACY_DB at a copy of it; without it, the parity tests run
# against a synthetic v1 database built from SYNTHETIC_CASES instead.
LEGACY_DB_ENV = "FACTURO_LEGACY_DB"


# ── Frozen v1 oracle ────────────────────────────────────────────────────
# A verbatim, standalone copy of the discount math that shipped before this
# migration existed (facturo/invoicing/excel_generator.py, pre-v2). Frozen
# here on purpose: excel_generator.py is being rewritten by this same
# workstream to delegate to discounts.py, so importing it would let the
# oracle silently drift and always agree with whatever the new code does.


def _v1_discount_amount(base: float, remise_type: str, remise_valeur) -> float:
    try:
        valeur = float(remise_valeur or 0)
    except (TypeError, ValueError):
        return 0.0
    if valeur <= 0:
        return 0.0
    if remise_type == "percent":
        montant = base * valeur / 100.0
    elif remise_type == "montant":
        montant = valeur
    else:
        return 0.0
    return max(0.0, min(montant, base))


def _v1_billet_net(billet: dict) -> float:
    gross = float(billet["quantite"]) * float(billet["taux"])
    disc = _v1_discount_amount(gross, billet.get("remise_type", ""), billet.get("remise_valeur", 0))
    return gross - disc


def _v1_invoice_billet_cut(billet_net: float, remise_type: str, remise_valeur) -> float:
    if remise_type != "montant":
        return 0.0
    return _v1_discount_amount(billet_net, "montant", remise_valeur)


def _v1_totals(billets: list[dict], remise_type: str, remise_valeur) -> tuple[float, float, float]:
    """Return (sous_total, remise, base_taxable) exactly as v1 printed them."""
    if remise_type == "percent":
        sous_total = sum(_v1_billet_net(b) for b in billets)
        remise = _v1_discount_amount(sous_total, remise_type, remise_valeur)
        base_taxable = sous_total - remise
    else:
        row_totals, cuts = [], []
        for b in billets:
            net = _v1_billet_net(b)
            cut = _v1_invoice_billet_cut(net, remise_type, remise_valeur)
            row_totals.append(net - cut)
            cuts.append(cut)
        sous_total = sum(row_totals)
        remise = sum(cuts)
        base_taxable = sous_total
    return sous_total, remise, base_taxable


# ── Synthetic v1 database ───────────────────────────────────────────────


def _v1_conn(path: Path) -> sqlite3.Connection:
    """A database whose DATA is still v1-shaped (legacy remise_type/valeur
    populated, v2 remise_pct/remise_montant untouched at their SQL default of
    0) even though its schema already carries the v2 columns.

    This mirrors exactly how schema.migrate() itself gets there: base tables,
    then every v1 column, then the v2 columns (a cheap, purely additive
    ALTER TABLE with DEFAULT 0) -- all BEFORE the data conversion
    (migrate_legacy_discounts) ever runs. A real v1 database has never had a
    remise_pct/remise_montant column at all, but by the time the discount
    migration looks at it, schema.migrate() has already added them.
    """
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(schema._BASE_TABLES)
    schema._migrate_v1(conn)
    schema._migrate_v2(conn)
    conn.execute("INSERT INTO clients (id, ref, prefix, nom) VALUES (1, 'r', 'p', 'Client Test')")
    conn.commit()
    return conn


def _insert_facture(conn, numero, billets, remise_type="", remise_valeur=0.0):
    conn.execute(
        "INSERT INTO factures (client_id, numero, date, fichier, billets_json, "
        "remise_type, remise_valeur) VALUES (1, ?, '2026-01-01', 'f.xlsx', ?, ?, ?)",
        (numero, json.dumps(billets), remise_type, remise_valeur),
    )
    conn.commit()


def _facture_row(conn, numero) -> dict:
    row = conn.execute("SELECT * FROM factures WHERE numero = ?", (numero,)).fetchone()
    return dict(row)


def _billets_of(row: dict) -> list[dict]:
    return json.loads(row["billets_json"])


SYNTHETIC_CASES = [
    # name, billets (pre-migration), invoice remise_type/valeur
    (
        "invoice_percent_legacy",
        [{"quantite": 2, "taux": 100}, {"quantite": 3, "taux": 100}],
        "percent",
        20.0,
    ),
    (
        "invoice_montant_legacy_folds_into_every_billet",
        [{"quantite": 1, "taux": 100}, {"quantite": 1, "taux": 50}, {"quantite": 1, "taux": 10}],
        "montant",
        30.0,
    ),
    (
        "billet_own_montant_plus_invoice_montant_fold",
        [{"quantite": 10, "taux": 10, "remise_type": "montant", "remise_valeur": 20}],
        "montant",
        15.0,
    ),
    (
        "billet_own_percent_plus_invoice_montant_fold",
        [{"quantite": 10, "taux": 100, "remise_type": "percent", "remise_valeur": 10}],
        "montant",
        200.0,
    ),
    (
        "no_discount_untouched",
        [{"quantite": 5, "taux": 100}],
        "",
        0.0,
    ),
]


@pytest.fixture
def synthetic_db(tmp_path):
    conn = _v1_conn(tmp_path / "v1.db")
    for numero, billets, rtype, rval in SYNTHETIC_CASES:
        _insert_facture(conn, numero, billets, rtype, rval)
    yield conn
    conn.close()


@pytest.mark.parametrize(
    "numero, billets, remise_type, remise_valeur", SYNTHETIC_CASES, ids=[c[0] for c in SYNTHETIC_CASES]
)
def test_migration_reproduces_v1_totals_for_every_synthetic_case(
    synthetic_db, numero, billets, remise_type, remise_valeur
):
    oracle_sous_total, oracle_remise, oracle_base = _v1_totals(billets, remise_type, remise_valeur)

    discounts.migrate_legacy_discounts(synthetic_db)

    row = _facture_row(synthetic_db, numero)
    migrated_billets = _billets_of(row)
    totals = discounts.invoice_totals(migrated_billets, row)

    assert totals.sous_total == pytest.approx(oracle_sous_total, abs=EPSILON), numero
    assert totals.base_taxable == pytest.approx(oracle_base, abs=EPSILON), numero
    # v1's invoice-level "montant" remise was display-only (billet rows were already
    # net of it); after migration it lives inside the billets, so the invoice-level
    # remise is exactly what separates sous_total from base — 0 for those cases,
    # the full oracle remise for the percent branch.
    assert totals.remise == pytest.approx(oracle_sous_total - oracle_base, abs=EPSILON), numero
    if remise_type == "percent":
        assert totals.remise == pytest.approx(oracle_remise, abs=EPSILON), numero
    assert totals.total == pytest.approx(oracle_base * 1.14975, abs=EPSILON), numero


def test_migration_clears_legacy_fields_after_conversion(synthetic_db):
    discounts.migrate_legacy_discounts(synthetic_db)
    for numero, _billets, _rtype, _rval in SYNTHETIC_CASES:
        row = _facture_row(synthetic_db, numero)
        assert row["remise_type"] == "", numero
        assert row["remise_valeur"] == 0, numero
        for billet in _billets_of(row):
            assert billet.get("remise_type", "") == "", numero
            assert billet.get("remise_valeur", 0) == 0, numero


def test_migration_invoice_percent_maps_straight_to_v2_pct(synthetic_db):
    discounts.migrate_legacy_discounts(synthetic_db)
    row = _facture_row(synthetic_db, "invoice_percent_legacy")
    assert row["remise_pct"] == pytest.approx(20.0)
    assert row["remise_montant"] == pytest.approx(0.0)


def test_migration_invoice_montant_becomes_zero_at_invoice_level(synthetic_db):
    """The v1 per-billet montant discount must NOT survive as a live
    invoice-level remise_montant -- v2 spends that once, which is not what
    v1 did."""
    discounts.migrate_legacy_discounts(synthetic_db)
    for numero in (
        "invoice_montant_legacy_folds_into_every_billet",
        "billet_own_montant_plus_invoice_montant_fold",
        "billet_own_percent_plus_invoice_montant_fold",
    ):
        row = _facture_row(synthetic_db, numero)
        assert row["remise_montant"] == pytest.approx(0.0), numero


def test_migration_folds_invoice_montant_into_each_billet_clamped_to_its_own_net(synthetic_db):
    discounts.migrate_legacy_discounts(synthetic_db)
    row = _facture_row(synthetic_db, "invoice_montant_legacy_folds_into_every_billet")
    billets = _billets_of(row)
    # gross 100, 50, 10; invoice montant 30 -> full $30 cut on the first two,
    # clamped to $10 on the smallest billet.
    assert billets[0].get("remise_montant", 0) == pytest.approx(30.0)
    assert billets[1].get("remise_montant", 0) == pytest.approx(30.0)
    assert billets[2].get("remise_montant", 0) == pytest.approx(10.0)


def test_migration_adds_invoice_fold_on_top_of_the_billets_own_discount(synthetic_db):
    discounts.migrate_legacy_discounts(synthetic_db)
    row = _facture_row(synthetic_db, "billet_own_montant_plus_invoice_montant_fold")
    billet = _billets_of(row)[0]
    # own $20 + invoice fold min(15, 100-20=80) = 15 -> total montant 35
    assert billet.get("remise_montant", 0) == pytest.approx(35.0)
    assert billet.get("remise_pct", 0) == pytest.approx(0.0)


def test_migration_preserves_the_billets_own_percent_while_folding_montant(synthetic_db):
    discounts.migrate_legacy_discounts(synthetic_db)
    row = _facture_row(synthetic_db, "billet_own_percent_plus_invoice_montant_fold")
    billet = _billets_of(row)[0]
    assert billet.get("remise_pct", 0) == pytest.approx(10.0)
    # gross 1000, own pct cuts 100 -> net-before-fold 900; invoice montant 200
    # fits entirely -> fold amount is exactly 200
    assert billet.get("remise_montant", 0) == pytest.approx(200.0)


def test_migration_leaves_undiscounted_invoices_alone(synthetic_db):
    before = _facture_row(synthetic_db, "no_discount_untouched")
    discounts.migrate_legacy_discounts(synthetic_db)
    after = _facture_row(synthetic_db, "no_discount_untouched")
    assert after["remise_pct"] == pytest.approx(0.0)
    assert after["remise_montant"] == pytest.approx(0.0)
    assert _billets_of(after) == _billets_of(before)


def test_migration_is_idempotent(synthetic_db):
    discounts.migrate_legacy_discounts(synthetic_db)
    snapshot_after_first = [dict(r) for r in synthetic_db.execute("SELECT * FROM factures ORDER BY id")]

    discounts.migrate_legacy_discounts(synthetic_db)
    snapshot_after_second = [dict(r) for r in synthetic_db.execute("SELECT * FROM factures ORDER BY id")]

    assert snapshot_after_second == snapshot_after_first


def test_migration_via_full_schema_migrate_pipeline(tmp_path):
    """End-to-end: schema.migrate() on a genuine pre-v2 database (user_version
    0) must invoke the discount migration itself, exactly once."""
    conn = _v1_conn(tmp_path / "pipeline.db")
    _insert_facture(
        conn, "pipe001",
        [{"quantite": 4, "taux": 100}], remise_type="percent", remise_valeur=25.0,
    )
    assert schema.user_version(conn) == 0

    schema.migrate(conn)

    assert schema.user_version(conn) == schema.SCHEMA_VERSION
    row = _facture_row(conn, "pipe001")
    assert row["remise_pct"] == pytest.approx(25.0)
    assert row["remise_type"] == ""
    conn.close()


# ── Whole-database parity ────────────────────────────────────────────────


@pytest.fixture
def legacy_db_path(tmp_path) -> Path:
    """A pre-v2 database file: FACTURO_LEGACY_DB if set, else a synthetic one."""
    configured = os.environ.get(LEGACY_DB_ENV, "").strip()
    if configured:
        path = Path(configured)
        if not path.is_file():
            pytest.skip(f"{LEGACY_DB_ENV} does not name a file: {path}")
        return path
    path = tmp_path / "legacy_source.db"
    conn = _v1_conn(path)
    for numero, billets, rtype, rval in SYNTHETIC_CASES:
        _insert_facture(conn, numero, billets, rtype, rval)
    conn.close()
    return path


def test_whole_database_totals_are_identical_before_and_after_migration(tmp_path, legacy_db_path):
    """Every invoice in the legacy (copied, never modified) database must
    add up to the exact same totals after migration as the v1 oracle computed
    before it -- to the cent, for all of them, not a sample."""
    copy_path = tmp_path / "real_copy.db"
    shutil.copyfile(legacy_db_path, copy_path)

    conn = sqlite3.connect(str(copy_path))
    conn.row_factory = sqlite3.Row

    before_rows = conn.execute(
        "SELECT id, numero, remise_type, remise_valeur, billets_json FROM factures"
    ).fetchall()
    assert len(before_rows) > 0, "expected at least one invoice in the legacy database"

    oracle_by_id = {}
    for row in before_rows:
        billets = json.loads(row["billets_json"] or "[]")
        oracle_by_id[row["id"]] = _v1_totals(
            billets, row["remise_type"] or "", row["remise_valeur"] or 0
        )

    schema.migrate(conn)

    mismatches = []
    for facture_id, (oracle_sous_total, _oracle_remise, oracle_base) in oracle_by_id.items():
        row = conn.execute("SELECT * FROM factures WHERE id = ?", (facture_id,)).fetchone()
        migrated_billets = json.loads(row["billets_json"] or "[]")
        totals = discounts.invoice_totals(migrated_billets, dict(row))
        if abs(totals.sous_total - oracle_sous_total) > 0.01 or abs(totals.base_taxable - oracle_base) > 0.01:
            mismatches.append(
                (facture_id, row["numero"], oracle_sous_total, totals.sous_total, oracle_base, totals.base_taxable)
            )

    assert mismatches == [], f"totals drifted after migration for: {mismatches}"
    conn.close()


def test_whole_database_migration_is_idempotent(tmp_path, legacy_db_path):
    copy_path = tmp_path / "real_copy_idem.db"
    shutil.copyfile(legacy_db_path, copy_path)
    conn = sqlite3.connect(str(copy_path))
    conn.row_factory = sqlite3.Row

    schema.migrate(conn)
    snapshot_after_first = [dict(r) for r in conn.execute("SELECT * FROM factures ORDER BY id")]

    discounts.migrate_legacy_discounts(conn)
    snapshot_after_second = [dict(r) for r in conn.execute("SELECT * FROM factures ORDER BY id")]

    assert snapshot_after_second == snapshot_after_first
    conn.close()

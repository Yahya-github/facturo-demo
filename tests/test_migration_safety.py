"""The v1 -> v2 migration must never lose data it cannot convert.

* An invoice-level legacy fixed amount is folded into the billets. When the
  billets cannot be read (corrupt JSON) or there are none, there is nothing to
  fold into: the row is left exactly as it was, so the legacy fields still
  drive the total through normalize_discount's legacy path.
* An existing database is copied into backups/ before it is migrated, so an
  unforeseen migration bug always has a way back.
"""

import logging
import sqlite3
from contextlib import closing

import pytest

from facturo import paths
from facturo.core import database as db
from facturo.core import schema
from facturo.invoicing import discounts


def _v1_db(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(schema._BASE_TABLES)
    schema._migrate_v1(conn)
    schema._migrate_v2(conn)
    conn.execute("INSERT INTO clients (id, ref, prefix, nom) VALUES (1, 'r', 'p', 'C')")
    conn.commit()
    return conn


def _insert(conn, numero, billets_json, rtype="montant", rval=50.0):
    conn.execute(
        "INSERT INTO factures (client_id, numero, date, fichier, billets_json, "
        "remise_type, remise_valeur) VALUES (1, ?, '2026-01-01', 'f.xlsx', ?, ?, ?)",
        (numero, billets_json, rtype, rval),
    )
    conn.commit()


@pytest.mark.parametrize("billets_json", ["{bad", "[]"], ids=["corrupt_json", "no_billets"])
def test_unfoldable_invoice_montant_keeps_its_legacy_fields(tmp_path, caplog, billets_json):
    conn = _v1_db(tmp_path / "v1.db")
    _insert(conn, "x001", billets_json)
    fid = conn.execute("SELECT id FROM factures WHERE numero='x001'").fetchone()[0]

    with caplog.at_level(logging.WARNING):
        discounts.migrate_legacy_discounts(conn)

    row = dict(conn.execute("SELECT * FROM factures WHERE id=?", (fid,)).fetchone())
    assert row["remise_type"] == "montant"
    assert row["remise_valeur"] == pytest.approx(50.0)
    assert row["remise_montant"] == pytest.approx(0.0)
    assert row["billets_json"] == billets_json
    # Still read through the legacy path.
    assert discounts.normalize_discount(row) == (0.0, 50.0)
    assert str(fid) in caplog.text
    conn.close()


def test_unfoldable_row_does_not_block_the_others(tmp_path):
    conn = _v1_db(tmp_path / "v1.db")
    _insert(conn, "bad", "{bad")
    _insert(conn, "good", '[{"quantite": 1, "taux": 100}]', "percent", 10.0)

    discounts.migrate_legacy_discounts(conn)

    good = conn.execute("SELECT * FROM factures WHERE numero='good'").fetchone()
    assert good["remise_type"] == ""
    assert good["remise_pct"] == pytest.approx(10.0)
    conn.close()


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "data.db")
    monkeypatch.setattr(paths, "backups_dir", lambda: tmp_path / "backups")
    return tmp_path


def test_existing_older_db_is_backed_up_before_migrating(isolated_db):
    conn = _v1_db(isolated_db / "data.db")
    _insert(conn, "keep", '[{"quantite": 1, "taux": 100}]', "percent", 10.0)
    conn.close()

    db.init_db()

    backups = list((isolated_db / "backups").glob("data.db.*.pre-migration.bak"))
    assert len(backups) == 1
    with sqlite3.connect(str(backups[0])) as copy:
        assert schema.user_version(copy) == 0
        assert copy.execute("SELECT remise_type FROM factures").fetchone()[0] == "percent"


def test_fresh_db_is_not_backed_up(isolated_db):
    db.init_db()
    assert not (isolated_db / "backups").exists()


def test_migrate_check_prices_v1_data_with_v1_semantics(tmp_path):
    """v1 took an invoice-level fixed amount off EVERY billet (clamped per billet).
    The checker must price the pre-migration data that way, or it rejects a
    correct migration: (1000-50 + 500-50) x 1.14975 = 1609.65."""
    from facturo.tools import migrate_check

    path = tmp_path / "v1.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(schema._BASE_TABLES)
    schema._migrate_v1(conn)  # a real v1 file: no v2 columns yet
    conn.execute("INSERT INTO clients (id, ref, prefix, nom) VALUES (1, 'r', 'p', 'C')")
    conn.commit()
    _insert(conn, "v1", '[{"quantite": 10, "taux": 100}, {"quantite": 5, "taux": 100}]')
    conn.close()

    result = migrate_check.check(path)

    assert result["before_total"] == pytest.approx(1609.65, abs=0.01)
    assert result["after_total"] == pytest.approx(1609.65, abs=0.01)
    assert result["ok"] is True, result["message"]


def _indexes(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}


_LOOKUP_INDEXES = {"idx_paiement_lignes_facture", "idx_factures_client_cree"}


def test_schema_version_is_2():
    """Indexes are not a schema bump: v2 stays the only version devices must share."""
    assert schema.SCHEMA_VERSION == 2


def test_fresh_db_has_the_lookup_indexes_at_version_2(isolated_db):
    db.init_db()

    with closing(sqlite3.connect(str(isolated_db / "data.db"))) as conn:
        assert schema.user_version(conn) == 2
        assert _LOOKUP_INDEXES <= _indexes(conn)
        plan = " ".join(str(r[-1]) for r in conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM paiement_lignes WHERE facture_id = 1"))
        assert "idx_paiement_lignes_facture" in plan


def test_v2_db_without_the_indexes_gains_them_and_stays_at_2(isolated_db):
    """A v2 database from a dev machine predating the indexes gets them on start."""
    conn = _v1_db(isolated_db / "data.db")
    for name in _LOOKUP_INDEXES:
        conn.execute(f"DROP INDEX IF EXISTS {name}")
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    assert not _LOOKUP_INDEXES & _indexes(conn)
    conn.close()

    db.init_db()

    with closing(sqlite3.connect(str(isolated_db / "data.db"))) as conn:
        assert schema.user_version(conn) == 2
        assert _LOOKUP_INDEXES <= _indexes(conn)
    assert not (isolated_db / "backups").exists()  # same version: no migration backup


def test_up_to_date_v2_db_is_not_written_on_start(isolated_db):
    """Stamp only on change: a start with nothing missing commits nothing, so
    sync and backups never see an untouched database as modified."""
    db.init_db()
    with closing(sqlite3.connect(str(isolated_db / "data.db"))) as watcher:
        before = watcher.execute("PRAGMA data_version").fetchone()[0]

        db.init_db()

        after = watcher.execute("PRAGMA data_version").fetchone()[0]
    assert after == before


def test_v1_db_migrates_to_2(isolated_db):
    conn = sqlite3.connect(str(isolated_db / "data.db"))
    conn.executescript(schema._BASE_TABLES)
    schema._migrate_v1(conn)
    conn.commit()
    assert schema.user_version(conn) == 0
    conn.close()

    db.init_db()

    with closing(sqlite3.connect(str(isolated_db / "data.db"))) as conn:
        assert schema.user_version(conn) == 2
        assert _LOOKUP_INDEXES <= _indexes(conn)


def test_db_at_3_is_newer_than_app_and_left_untouched(tmp_path):
    conn = _v1_db(tmp_path / "v3.db")
    for name in _LOOKUP_INDEXES:
        conn.execute(f"DROP INDEX IF EXISTS {name}")
    conn.execute("PRAGMA user_version = 3")
    conn.commit()

    assert schema.is_newer_than_app(conn)
    schema.migrate(conn)

    assert schema.user_version(conn) == 3
    assert not _LOOKUP_INDEXES & _indexes(conn)
    conn.close()


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_fresh_db_has_no_paiement_factures_table(isolated_db):
    db.init_db()

    with closing(sqlite3.connect(str(isolated_db / "data.db"))) as conn:
        assert "paiement_factures" not in _tables(conn)
        assert {"paiements", "paiement_lignes"} <= _tables(conn)


def test_dev_v2_db_loses_the_unused_paiement_factures_table(isolated_db):
    """Development v2 databases were created with a whole-invoice link table
    nothing ever used; the v2 step drops it."""
    conn = _v1_db(isolated_db / "data.db")
    conn.execute("CREATE TABLE paiement_factures (paiement_id INTEGER, facture_id INTEGER)")
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()

    db.init_db()

    with closing(sqlite3.connect(str(isolated_db / "data.db"))) as conn:
        assert "paiement_factures" not in _tables(conn)
        assert schema.user_version(conn) == 2


def test_reset_db_empties_the_payment_tables(isolated_db):
    db.init_db()
    with closing(sqlite3.connect(str(isolated_db / "data.db"))) as conn:
        conn.execute("INSERT INTO paiements (reference) VALUES ('Q1')")
        conn.execute("INSERT INTO paiement_lignes (paiement_id) VALUES (1)")
        conn.commit()

    db.reset_db()

    with closing(sqlite3.connect(str(isolated_db / "data.db"))) as conn:
        assert conn.execute("SELECT COUNT(*) FROM paiements").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM paiement_lignes").fetchone()[0] == 0


def test_v2_db_is_not_reconverted_on_start(tmp_path):
    """Only v1 data gets the discount conversion; a v2 row with a live legacy
    montant (kept because it was unfoldable) must stay exactly as it is."""
    conn = _v1_db(tmp_path / "v2.db")
    _insert(conn, "kept", "{bad")
    conn.execute("PRAGMA user_version = 2")
    conn.commit()

    schema.migrate(conn)

    row = conn.execute("SELECT remise_type, remise_valeur FROM factures").fetchone()
    assert tuple(row) == ("montant", 50.0)
    conn.close()


def test_missing_data_folder_is_created(tmp_path, monkeypatch):
    """FACTURO_DATA_DIR may name a folder that does not exist yet."""
    from facturo.invoicing import excel_generator as gen

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "absent" / "deeper" / "data.db")
    monkeypatch.setattr(gen, "OUTPUT_DIR", tmp_path / "absent2" / "deeper" / "output")

    db.init_db()
    client = db.create_client("R", "p", "Client", "1 rue")
    out = gen.generate_invoice(client, "p001", "2026-01-01",
                               [{"quantite": 1, "taux": 100, "chantier": "C"}],
                               output_filename="p001.xlsx")

    assert db.DB_PATH.exists()
    assert out.exists()


def test_current_db_is_not_backed_up_again(isolated_db):
    db.init_db()
    db.init_db()
    assert not (isolated_db / "backups").exists()

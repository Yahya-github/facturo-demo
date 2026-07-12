"""Database schema and its migrations.

`PRAGMA user_version` records which schema a data.db file carries:
  0 — v1 databases (everything before versioned migrations)
  2 — v2: combined discounts, payments, auto-paid flag, lookup indexes

migrate() is idempotent and runs at startup and after every sync pull, because
a pulled database may have been written by an older version of the app. Every
step re-runs on a database already at the current version, so objects added
without a version bump (the lookup indexes) reach v2 databases created before
them; a step that finds nothing to do writes nothing.

A database stamped with a NEWER version than this app knows (pulled from a device
that was updated first) is left untouched: `is_newer_than_app()` lets the UI tell
the user to update instead of running an old app against a schema it does not
understand.
"""

import sqlite3

SCHEMA_VERSION = 2

_BASE_TABLES = """
    CREATE TABLE IF NOT EXISTS clients (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ref         TEXT NOT NULL,
        prefix      TEXT NOT NULL,
        nom         TEXT NOT NULL,
        adresse     TEXT NOT NULL DEFAULT '',
        next_numero INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS factures (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id   INTEGER NOT NULL REFERENCES clients(id),
        numero      TEXT NOT NULL,
        date        TEXT NOT NULL,
        fichier     TEXT NOT NULL,
        billets_json TEXT,
        cree_le     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );
    -- Scanned invoices: uploaded PDF/image files filed under a client.
    CREATE TABLE IF NOT EXISTS scans (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id    INTEGER NOT NULL REFERENCES clients(id),
        fichier      TEXT NOT NULL,
        nom_original TEXT NOT NULL DEFAULT '',
        cree_le      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );
    -- The renter names and truck plates this shop actually uses: the vocabulary
    -- the billet form autocompletes from, and the authority an AI reading gets
    -- snapped against. Curated rather than derived, so one bad invoice's junk can
    -- be deleted, hidden or merged away instead of becoming an authority.
    CREATE TABLE IF NOT EXISTS known_values (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        kind       TEXT NOT NULL CHECK (kind IN ('chantier','plaque')),
        valeur     TEXT NOT NULL,
        cle        TEXT NOT NULL,
        times_used INTEGER NOT NULL DEFAULT 0,
        last_used  TEXT NOT NULL DEFAULT '',
        curated    INTEGER NOT NULL DEFAULT 0,
        hidden     INTEGER NOT NULL DEFAULT 0,
        alias_of   INTEGER REFERENCES known_values(id),
        cree_le    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );
    -- `cle` is the accent/case/punctuation-folded identity, so "AB 12345" and
    -- "AB12345" collapse into one row instead of competing.
    CREATE UNIQUE INDEX IF NOT EXISTS idx_known_values_identity
        ON known_values(kind, cle);
"""

_PAYMENT_TABLES = """
    -- Imported proofs of payment (e.g. a client's quittance listing the billets
    -- it pays). Bills addressed TO the company are not payments and are never stored.
    CREATE TABLE IF NOT EXISTS paiements (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id    INTEGER REFERENCES clients(id) ON DELETE SET NULL,
        emetteur     TEXT NOT NULL DEFAULT '',
        reference    TEXT NOT NULL DEFAULT '',
        date         TEXT NOT NULL DEFAULT '',
        sous_total   REAL,
        tps          REAL,
        tvq          REAL,
        escompte     REAL,
        total        REAL,
        notes        TEXT NOT NULL DEFAULT '',
        fichier      TEXT NOT NULL DEFAULT '',
        nom_original TEXT NOT NULL DEFAULT '',
        texte        TEXT NOT NULL DEFAULT '',
        cree_le      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );
    -- One line per billet found on a payment. facture_id + billet_index point at
    -- the billet inside factures.billets_json once matched.
    CREATE TABLE IF NOT EXISTS paiement_lignes (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        paiement_id   INTEGER NOT NULL REFERENCES paiements(id) ON DELETE CASCADE,
        numero_billet TEXT NOT NULL DEFAULT '',
        date_billet   TEXT NOT NULL DEFAULT '',
        plaque        TEXT NOT NULL DEFAULT '',
        quantite      REAL,
        montant       REAL,
        facture_id    INTEGER REFERENCES factures(id) ON DELETE SET NULL,
        billet_index  INTEGER,
        methode       TEXT NOT NULL DEFAULT ''
                      CHECK (methode IN ('','numero','date_plaque','manuel'))
    );
    -- A billet can be held by one payment line only: enforced here as well as
    -- in payments/store.py, so a future script cannot double-link a billet.
    CREATE UNIQUE INDEX IF NOT EXISTS idx_paiement_lignes_billet
        ON paiement_lignes(facture_id, billet_index)
        WHERE facture_id IS NOT NULL AND billet_index IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_paiement_lignes_paiement
        ON paiement_lignes(paiement_id);
"""


# Indexes for the lookups every page does: payment lines of an invoice
# (coverage, relink) and a client's invoices newest first (history). Part of v2
# without a version bump; migrate() creates them on every start if missing.
_LOOKUP_INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_paiement_lignes_facture
        ON paiement_lignes(facture_id);
    CREATE INDEX IF NOT EXISTS idx_factures_client_cree
        ON factures(client_id, cree_le);
"""


def user_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def is_newer_than_app(conn: sqlite3.Connection) -> bool:
    return user_version(conn) > SCHEMA_VERSION


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def _add_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """Add a column if it isn't there yet (idempotent)."""
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _migrate_v1(conn: sqlite3.Connection) -> None:
    """Every column added during v1's life, for databases created early on."""
    _add_column(conn, "clients", "separer_chantiers", "INTEGER NOT NULL DEFAULT 0")
    _add_column(conn, "clients", "taux_defaut", "REAL NOT NULL DEFAULT 0")
    _add_column(conn, "factures", "billets_json", "TEXT")
    # Legacy single-kind invoice discount; superseded by remise_pct/remise_montant.
    _add_column(conn, "factures", "remise_type", "TEXT NOT NULL DEFAULT ''")
    _add_column(conn, "factures", "remise_valeur", "REAL NOT NULL DEFAULT 0")
    _add_column(conn, "factures", "paye", "INTEGER NOT NULL DEFAULT 0")


def _migrate_v2(conn: sqlite3.Connection) -> None:
    _add_column(conn, "factures", "remise_pct", "REAL NOT NULL DEFAULT 0")
    _add_column(conn, "factures", "remise_montant", "REAL NOT NULL DEFAULT 0")
    # 1 when `paye` was set automatically because payments cover every billet;
    # lets removing a payment revert only what the app decided, never the user.
    _add_column(conn, "factures", "paye_auto", "INTEGER NOT NULL DEFAULT 0")
    conn.executescript(_PAYMENT_TABLES)
    conn.executescript(_LOOKUP_INDEXES)
    # Development v2 databases carry an unused whole-invoice link table; a
    # payment only ever links billets (paiement_lignes). No-op once it is gone.
    conn.execute("DROP TABLE IF EXISTS paiement_factures")


def migrate(conn: sqlite3.Connection) -> None:
    """Bring `conn` up to SCHEMA_VERSION. Leaves newer databases untouched."""
    if is_newer_than_app(conn):
        return
    before = user_version(conn)
    # Seed known values only when the table is created, never because it is
    # empty: a user who deliberately cleared every value must not get them back.
    had_known_values = _has_table(conn, "known_values")
    conn.executescript(_BASE_TABLES)
    _migrate_v1(conn)
    _migrate_v2(conn)
    if not had_known_values:
        from facturo.core import known_values
        known_values.seed(conn)
    if before < 2:
        from facturo.invoicing import discounts
        discounts.migrate_legacy_discounts(conn)
    # Stamp only on change: rewriting the header on every start would make an
    # untouched database look modified to sync and to backups.
    if before != SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()

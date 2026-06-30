import logging
import re
import sqlite3
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime

from facturo import paths
from facturo.core import schema

# Stored next to the exe (when frozen) so the client's data survives upgrades
# and is easy to back up.
DB_PATH = paths.db_path()

log = logging.getLogger(__name__)


def get_conn() -> sqlite3.Connection:
    # The data folder (FACTURO_DATA_DIR, or data/ in development) may not
    # exist yet; SQLite creates the file but never its folder.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """One write transaction; reads inside it see a stable, locked snapshot.

    Lets several writes that must stand or fall together (an invoice edit and
    the payment relink that follows it) share one commit.
    """
    with closing(get_conn()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.rollback()
            raise
        conn.commit()


@contextmanager
def _writing(conn: sqlite3.Connection | None) -> Iterator[sqlite3.Connection]:
    """The caller's connection (its transaction commits), or a fresh one committed here."""
    if conn is not None:
        yield conn
        return
    with closing(get_conn()) as own:
        yield own
        own.commit()


def _needs_pre_migration_backup(conn: sqlite3.Connection) -> bool:
    """True for an existing database (it has tables) on an older schema."""
    if schema.user_version(conn) >= schema.SCHEMA_VERSION:
        return False
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone())


def _backup_before_migration(conn: sqlite3.Connection) -> None:
    """Copy the database into backups/ before a migration rewrites it.

    Uses SQLite's online backup, so rows still in the WAL are included. A failure
    raises: migrating without a way back is exactly what this guards against.
    """
    backups = paths.backups_dir()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backups / f"data.db.{stamp}.pre-migration.bak"
    try:
        backups.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(str(target))) as dst:
            conn.backup(dst)
    except (OSError, sqlite3.Error):
        log.exception("Sauvegarde avant migration impossible vers %s", target)
        raise
    log.info("Base sauvegardée avant migration : %s", target)


def init_db() -> None:
    """Create or migrate the database (see core/schema.py).

    An existing database on an older schema is copied into backups/ first.
    """
    conn = get_conn()
    try:
        if _needs_pre_migration_backup(conn):
            _backup_before_migration(conn)
        schema.migrate(conn)
    finally:
        conn.close()


def is_newer_than_app() -> bool:
    """True when data.db was written by a newer app version (see schema.py)."""
    conn = get_conn()
    try:
        return schema.is_newer_than_app(conn)
    finally:
        conn.close()


class DatabaseBusyError(Exception):
    """The WAL could not be fully flushed because another connection held it."""


CHECKPOINT_ATTEMPTS = 5
CHECKPOINT_RETRY_SECONDS = 0.5
CHECKPOINT_BUSY_TIMEOUT_MS = 2000
_sleep = time.sleep  # swapped out by tests


def checkpoint() -> None:
    """Flush the WAL into data.db so the file on disk is complete and self-contained.

    Called before a sync push/pull so the committed or backed-up database isn't
    missing writes that still live only in the -wal side file. SQLite reports a
    checkpoint blocked by another connection as busy rather than failing, so the
    flag is checked and the checkpoint retried; if it stays busy this raises
    DatabaseBusyError instead of letting a partial database be shipped.
    """
    for attempt in range(1, CHECKPOINT_ATTEMPTS + 1):
        with closing(get_conn()) as conn:
            conn.execute(f"PRAGMA busy_timeout = {int(CHECKPOINT_BUSY_TIMEOUT_MS)}")
            busy, _log_frames, _done = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if not busy:
            return
        log.warning("Checkpoint de la base occupé (tentative %d/%d)", attempt, CHECKPOINT_ATTEMPTS)
        if attempt < CHECKPOINT_ATTEMPTS:
            _sleep(CHECKPOINT_RETRY_SECONDS)
    raise DatabaseBusyError(
        "La base de données est occupée par une autre opération. "
        "Patientez quelques secondes puis réessayez."
    )


_TRAILING_DIGITS = re.compile(r"(\d+)\s*$")


def _trailing_int(numero: str) -> int | None:
    """The trailing number in an invoice number string, e.g. 'inv038' -> 38."""
    m = _TRAILING_DIGITS.search(numero or "")
    return int(m.group(1)) if m else None


def suggest_next_numero(conn, client_id: int) -> int:
    """One past the highest number already used for this client, or 1 if none.

    Based on the trailing digits of each existing invoice number, so the
    suggestion keeps following the client's real numbering even when past
    numbers were typed in manually (e.g. after 'inv038' it proposes 39).
    """
    rows = conn.execute(
        "SELECT numero FROM factures WHERE client_id = ?", (client_id,)
    ).fetchall()
    highest = 0
    for r in rows:
        n = _trailing_int(r["numero"])
        if n is not None and n > highest:
            highest = n
    return highest + 1


def list_clients() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM clients ORDER BY nom").fetchall()
    clients = []
    for r in rows:
        d = dict(r)
        d["next_numero"] = suggest_next_numero(conn, d["id"])
        clients.append(d)
    conn.close()
    return clients


def get_client(client_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if not row:
        conn.close()
        return None
    d = dict(row)
    d["next_numero"] = suggest_next_numero(conn, client_id)
    conn.close()
    return d


def create_client(
    ref: str, prefix: str, nom: str, adresse: str, separer_chantiers: bool = False,
    taux_defaut: float = 0.0,
) -> dict:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO clients (ref, prefix, nom, adresse, separer_chantiers, taux_defaut) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ref, prefix, nom, adresse, 1 if separer_chantiers else 0, taux_defaut),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM clients WHERE id = ?", (cur.lastrowid,)).fetchone()
    result = dict(row)
    conn.close()
    return result


def update_client(
    client_id: int, ref: str, prefix: str, nom: str, adresse: str,
    separer_chantiers: bool = False, taux_defaut: float = 0.0,
) -> dict:
    conn = get_conn()
    conn.execute(
        "UPDATE clients SET ref=?, prefix=?, nom=?, adresse=?, separer_chantiers=?, "
        "taux_defaut=? WHERE id=?",
        (ref, prefix, nom, adresse, 1 if separer_chantiers else 0, taux_defaut, client_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    result = dict(row)
    conn.close()
    return result


def save_facture(
    client_id: int, numero: str, date: str, fichier: str, billets_json: str | None = None,
    remise_type: str = "", remise_valeur: float = 0.0,
    remise_pct: float = 0.0, remise_montant: float = 0.0,
    conn: sqlite3.Connection | None = None,
) -> dict:
    with _writing(conn) as c:
        cur = c.execute(
            "INSERT INTO factures (client_id, numero, date, fichier, billets_json, "
            "remise_type, remise_valeur, remise_pct, remise_montant) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (client_id, numero, date, fichier, billets_json, remise_type, remise_valeur,
             remise_pct, remise_montant),
        )
        row = c.execute("SELECT * FROM factures WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def get_facture(facture_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        """SELECT f.*, c.nom as client_nom, c.ref as client_ref
           FROM factures f JOIN clients c ON f.client_id = c.id
           WHERE f.id = ?""",
        (facture_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_facture(
    facture_id: int, numero: str, date: str, fichier: str, billets_json: str,
    remise_type: str = "", remise_valeur: float = 0.0,
    remise_pct: float = 0.0, remise_montant: float = 0.0,
    conn: sqlite3.Connection | None = None,
) -> dict:
    with _writing(conn) as c:
        c.execute(
            "UPDATE factures SET numero = ?, date = ?, fichier = ?, billets_json = ?, "
            "remise_type = ?, remise_valeur = ?, remise_pct = ?, remise_montant = ? WHERE id = ?",
            (numero, date, fichier, billets_json, remise_type, remise_valeur,
             remise_pct, remise_montant, facture_id),
        )
        row = c.execute("SELECT * FROM factures WHERE id = ?", (facture_id,)).fetchone()
        return dict(row)


def set_facture_paye(facture_id: int, paye: bool) -> dict:
    """Manual paid toggle. Clears paye_auto: the user's decision now owns the flag."""
    conn = get_conn()
    conn.execute(
        "UPDATE factures SET paye = ?, paye_auto = 0 WHERE id = ?",
        (1 if paye else 0, facture_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM factures WHERE id = ?", (facture_id,)).fetchone()
    result = dict(row)
    conn.close()
    return result


def list_factures(client_id: int | None = None) -> list[dict]:
    conn = get_conn()
    if client_id:
        rows = conn.execute(
            """SELECT f.*, c.nom as client_nom, c.ref as client_ref
               FROM factures f JOIN clients c ON f.client_id = c.id
               WHERE f.client_id = ? ORDER BY f.cree_le DESC""",
            (client_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT f.*, c.nom as client_nom, c.ref as client_ref
               FROM factures f JOIN clients c ON f.client_id = c.id
               ORDER BY f.cree_le DESC""",
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_facture(facture_id: int) -> None:
    """Delete an invoice. Its payment lines become unlinked in full: the
    foreign key only nulls facture_id, which would leave a billet_index and a
    match method describing a link that no longer exists."""
    with transaction() as conn:
        conn.execute(
            "UPDATE paiement_lignes SET facture_id = NULL, billet_index = NULL, methode = '' "
            "WHERE facture_id = ?", (facture_id,),
        )
        conn.execute("DELETE FROM factures WHERE id = ?", (facture_id,))


def delete_client(client_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM scans WHERE client_id = ?", (client_id,))
    conn.execute("DELETE FROM factures WHERE client_id = ?", (client_id,))
    conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    conn.commit()
    conn.close()


def reset_db():
    conn = get_conn()
    conn.executescript("""
        DELETE FROM paiement_lignes;
        DELETE FROM paiements;
        DELETE FROM scans;
        DELETE FROM factures;
        DELETE FROM clients;
        DELETE FROM sqlite_sequence;
    """)
    conn.commit()
    conn.close()


# ── Scanned invoices ─────────────────────────────────────


def add_scan(client_id: int, fichier: str, nom_original: str) -> dict:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO scans (client_id, fichier, nom_original) VALUES (?, ?, ?)",
        (client_id, fichier, nom_original),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM scans WHERE id = ?", (cur.lastrowid,)).fetchone()
    result = dict(row)
    conn.close()
    return result


def list_scans(client_id: int | None = None) -> list[dict]:
    conn = get_conn()
    if client_id:
        rows = conn.execute(
            """SELECT s.*, c.nom as client_nom FROM scans s
               JOIN clients c ON s.client_id = c.id
               WHERE s.client_id = ? ORDER BY s.cree_le DESC""",
            (client_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT s.*, c.nom as client_nom FROM scans s
               JOIN clients c ON s.client_id = c.id
               ORDER BY s.cree_le DESC""",
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_scan(scan_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_scan(scan_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
    conn.commit()
    conn.close()

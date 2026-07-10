"""The renter names and truck plates this shop actually uses.

Two jobs, and both need the list *curated* rather than derived:

  * it is the vocabulary the billet form autocompletes from, and
  * it is the authority an AI reading gets snapped against (api/ai.py::_history).

Derived on the fly — which is what the app did before — one bad invoice's junk
becomes an authority for good: a plate typed once as "S/O" is something every
future extraction gets pulled towards, and nobody can remove it without editing
an old invoice. Kept in a table, the user deletes it, hides it, or merges it
away, and can add a truck *before* its first billet, which is what stops
snap_plate rewriting a genuinely new plate into the old one it resembles.

Storage lives here; the table itself is created in database.init_db, so that
all schema stays in one place.
"""

import json
import sqlite3

from facturo.core import billet_fields
from facturo.core.database import get_conn

KINDS = ("chantier", "plaque")


class KnownValueError(Exception):
    """A curation request that cannot be honoured; the message is shown as-is."""


def usable(kind: str, value: str) -> str:
    """Normalise a value for storage, or return "" if it does not belong here.

    The two kinds fail differently. A plaque has a checkable shape, so anything
    that is not letters-then-digits is refused outright — "S/O", "0000", and
    the "10.75" that is really an hours value typed in the wrong box would
    otherwise become things the AI snaps real plates towards. A chantier has no
    shape to check, so only an obvious worksite address is refused; a junk name
    is for the user to delete, not for us to guess at.
    """
    if kind == "plaque":
        plate = billet_fields.tidy_plate(billet_fields.clean_plate(value))
        return plate if billet_fields.is_plate(plate) else ""
    name = billet_fields.tidy_chantier(billet_fields.clean_chantier(value))
    return "" if billet_fields.looks_like_address(name) else name


def _tidy(kind: str, value: str) -> str:
    """Tidy a value a person typed — no OCR-misread repairs, which they'd resent."""
    return (billet_fields.tidy_plate(value) if kind == "plaque"
            else billet_fields.tidy_chantier(value))


def seed(conn) -> None:
    """Build the initial vocabulary from every invoice already generated.

    Called once, by init_db, when the table is first created. Oldest invoice
    first so `last_used` ends up holding the most recent date for each value.
    """
    groups: dict[tuple[str, str], dict] = {}
    rows = conn.execute(
        "SELECT billets_json, date FROM factures ORDER BY cree_le ASC"
    ).fetchall()
    for row in rows:
        try:
            billets = json.loads(row["billets_json"] or "[]")
        except (ValueError, TypeError):
            continue
        for billet in billets:
            # A free-description billet bills its text, not its fields: any
            # chantier/plaque still on the object is a leftover from before the
            # user switched that row over, and was never billed.
            if billet.get("desc_libre"):
                continue
            for kind in KINDS:
                value = usable(kind, str(billet.get(kind) or ""))
                if not value:
                    continue
                group = groups.setdefault(
                    (kind, billet_fields.fold(value)),
                    {"spellings": {}, "last_used": ""},
                )
                group["spellings"][value] = group["spellings"].get(value, 0) + 1
                group["last_used"] = max(group["last_used"], str(row["date"] or ""))

    for (kind, cle), group in groups.items():
        spellings = list(group["spellings"].items())
        conn.execute(
            """INSERT INTO known_values (kind, valeur, cle, times_used, last_used)
               VALUES (?, ?, ?, ?, ?)""",
            (kind, billet_fields.canonical_spelling(spellings), cle,
             sum(n for _, n in spellings), group["last_used"]),
        )


def list_all(kind: str | None = None) -> list[dict]:
    """Every value, hidden ones and merged aliases included — the curation view."""
    conn = get_conn()
    sql = """SELECT k.*, a.valeur AS alias_valeur
             FROM known_values k
             LEFT JOIN known_values a ON k.alias_of = a.id"""
    params: tuple = ()
    if kind:
        sql += " WHERE k.kind = ?"
        params = (kind,)
    sql += " ORDER BY k.times_used DESC, k.last_used DESC, k.valeur ASC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def for_history(kind: str) -> list[str]:
    """The values the AI may snap towards, most used first.

    Hidden values and merged-away aliases are left out: hiding something is the
    user saying "stop suggesting this, and stop correcting towards it".
    """
    conn = get_conn()
    rows = conn.execute(
        """SELECT valeur FROM known_values
           WHERE kind = ? AND hidden = 0 AND alias_of IS NULL
           ORDER BY times_used DESC, valeur ASC""",
        (kind,),
    ).fetchall()
    conn.close()
    return [r["valeur"] for r in rows]


def add(kind: str, valeur: str) -> dict:
    """Add a value by hand, before any invoice has used it.

    This is how a newly bought truck gets protected: once its plate is on file,
    snap_plate's "already in the fleet" guard stops the AI rewriting it into
    the older plate it happens to resemble.
    """
    if kind not in KINDS:
        raise KnownValueError("Type invalide")
    value = _tidy(kind, valeur)
    if not value:
        raise KnownValueError("Valeur vide")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO known_values (kind, valeur, cle, curated) VALUES (?, ?, ?, 1)",
            (kind, value, billet_fields.fold(value)),
        )
        conn.commit()
        return dict(conn.execute(
            "SELECT * FROM known_values WHERE id = ?", (cur.lastrowid,)).fetchone())
    except sqlite3.IntegrityError:
        raise KnownValueError("Cette valeur existe déjà.") from None
    finally:
        conn.close()


def update(kv_id: int, valeur: str | None = None, hidden: bool | None = None) -> dict:
    """Rename and/or hide a value.

    Renaming marks the row curated, which is what stops the seeder's
    frequency-based spelling choice from ever overriding the user's.

    It does NOT rewrite past invoices. `billets_json` is the record of what was
    actually billed; editing it to match a later preference would be a
    different and much riskier feature.
    """
    conn = get_conn()
    row = conn.execute("SELECT * FROM known_values WHERE id = ?", (kv_id,)).fetchone()
    if not row:
        conn.close()
        raise KnownValueError("Valeur introuvable")
    try:
        if valeur is not None:
            value = _tidy(row["kind"], valeur)
            if not value:
                raise KnownValueError("Valeur vide")
            conn.execute(
                "UPDATE known_values SET valeur = ?, cle = ?, curated = 1 WHERE id = ?",
                (value, billet_fields.fold(value), kv_id),
            )
        if hidden is not None:
            conn.execute("UPDATE known_values SET hidden = ? WHERE id = ?",
                         (1 if hidden else 0, kv_id))
        conn.commit()
        return dict(conn.execute(
            "SELECT * FROM known_values WHERE id = ?", (kv_id,)).fetchone())
    except sqlite3.IntegrityError:
        raise KnownValueError("Cette valeur existe déjà.") from None
    finally:
        conn.close()


def remove(kv_id: int) -> None:
    """Drop a value. Anything merged into it is set loose rather than orphaned."""
    conn = get_conn()
    conn.execute("UPDATE known_values SET alias_of = NULL WHERE alias_of = ?", (kv_id,))
    conn.execute("DELETE FROM known_values WHERE id = ?", (kv_id,))
    conn.commit()
    conn.close()


def merge(src_id: int, dst_id: int) -> None:
    """Declare two values the same thing, keeping dst.

    Folding already merges spelling variants on its own — that is what collapses
    five spellings of one client into one row. What it cannot do is merge
    "Terral" into "Terra": different strings, and only a person knows they are
    one client. The alias row survives rather than being deleted, so typing the
    old spelling later still resolves, and credits the survivor.
    """
    if src_id == dst_id:
        raise KnownValueError("Impossible de fusionner une valeur avec elle-même")
    conn = get_conn()
    try:
        src = conn.execute(
            "SELECT * FROM known_values WHERE id = ?", (src_id,)).fetchone()
        dst = conn.execute(
            "SELECT * FROM known_values WHERE id = ?", (dst_id,)).fetchone()
        if not src or not dst:
            raise KnownValueError("Valeur introuvable")
        if src["kind"] != dst["kind"]:
            raise KnownValueError("Les deux valeurs doivent être du même type")
        if dst["alias_of"] is not None:
            raise KnownValueError("La valeur cible a déjà été fusionnée ailleurs")
        conn.execute("UPDATE known_values SET times_used = times_used + ? WHERE id = ?",
                     (src["times_used"], dst_id))
        # Anything already pointing at src follows it to its new home.
        conn.execute("UPDATE known_values SET alias_of = ? WHERE alias_of = ?",
                     (dst_id, src_id))
        conn.execute(
            "UPDATE known_values SET times_used = 0, alias_of = ?, curated = 1 "
            "WHERE id = ?", (dst_id, src_id))
        conn.commit()
    finally:
        conn.close()


def record(billets: list[dict], date: str = "") -> None:
    """Note the values an invoice just used, so the vocabulary keeps up.

    Only ever bumps counts. The stored spelling of an existing value is never
    overwritten, because that spelling is what the autocomplete offers and it
    must not shift under the user mid-job; choosing between variants is the
    seeder's one-time task, or the user's deliberate edit.

    `times_used` counts billet lines that ever carried the value — removing a
    line from an invoice later does not decrement it. It ranks suggestions; it
    is not an account of anything.
    """
    conn = get_conn()
    for billet in billets:
        if billet.get("desc_libre"):
            continue
        for kind in KINDS:
            value = usable(kind, str(billet.get(kind) or ""))
            if not value:
                continue
            cle = billet_fields.fold(value)
            row = conn.execute(
                "SELECT id, alias_of FROM known_values WHERE kind = ? AND cle = ?",
                (kind, cle)).fetchone()
            if row:
                conn.execute(
                    "UPDATE known_values SET times_used = times_used + 1, "
                    "last_used = ? WHERE id = ?", (date, row["alias_of"] or row["id"]))
            else:
                conn.execute(
                    """INSERT INTO known_values (kind, valeur, cle, times_used, last_used)
                       VALUES (?, ?, ?, 1, ?)""", (kind, value, cle, date))
    conn.commit()
    conn.close()

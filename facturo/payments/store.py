"""Persistence for payments (paiements, paiement_lignes).

CONTRACT (consumed by the invoice list, filters and invoice form):
  * paid_billets() -> {(facture_id, billet_index): {"paiement_id", "reference"}}

A ligne's stored (facture_id, billet_index) IS the link; only a "lie" ligne
ever holds one. Everything else a ligne reports — statut, doublon_paiement_id,
candidats — is computed at read time against the current invoices and links,
so unlinking or deleting a payment needs no bookkeeping. Links are positional,
so an invoice edit must call relink_after_invoice_edit() to re-seat them.

Auto-paid rule, applied in the same transaction as every link change: an
invoice whose billets are all linked becomes paye=1, paye_auto=1; one that
loses full coverage is reverted only if paye_auto=1 (the app set it). A manual
"payée" (paye=1, paye_auto=0) is never touched.
"""

from collections.abc import Iterable, Iterator, Mapping
from contextlib import closing, contextmanager
from sqlite3 import Connection, Row

from facturo.core import database as db
from facturo.core.billet_fields import tidy_billet_number
from facturo.payments import matcher
from facturo.payments.parser import ParsedDoc, ParsedLigne

_HEADER_FIELDS = (
    "emetteur", "reference", "date", "sous_total", "tps", "tvq", "escompte", "total", "notes",
)
_DETAIL_COLUMNS = (
    "id, client_id, emetteur, reference, date, sous_total, tps, tvq, escompte, total, "
    "notes, fichier, nom_original, cree_le"
)
_LIGNE_COLUMNS = (
    "id, paiement_id, numero_billet, date_billet, plaque, quantite, montant, "
    "facture_id, billet_index, methode"
)


class PaymentNotFound(LookupError):
    pass


class LigneNotFound(LookupError):
    pass


class InvalidBillet(ValueError):
    """The (facture_id, billet_index) a user picked does not exist."""


class LinkConflict(ValueError):
    """The billet is already linked to another ligne."""

    def __init__(self, paiement_id: int):
        super().__init__(f"Ce billet est déjà lié au paiement #{paiement_id}.")
        self.paiement_id = paiement_id


# ── Connections ───────────────────────────────────────────────────────────

@contextmanager
def _reading() -> Iterator[Connection]:
    with closing(db.get_conn()) as conn:
        yield conn


def _transaction():
    """One write transaction; reads inside it see a stable, locked snapshot.

    Shared with the invoice API (db.transaction), which runs an edit and its
    relink_after_invoice_edit() in one commit.
    """
    return db.transaction()


# ── Matching context (one query each, never per ligne) ────────────────────

class _Context:
    """Every invoiced billet and every current link, loaded once."""

    def __init__(self, conn: Connection):
        factures = conn.execute(
            "SELECT f.id, f.numero, f.billets_json, c.nom AS client_nom "
            "FROM factures f JOIN clients c ON c.id = f.client_id"
        ).fetchall()
        self.index = matcher.build_index([dict(f) for f in factures])
        self.refs = {(r.facture_id, r.billet_index): r for r in self.index}
        self.factures = {f["id"]: (f["numero"], f["client_nom"]) for f in factures}
        # (facture_id, billet_index) -> (paiement_id, ligne_id); oldest link wins.
        self.links: dict[tuple[int, int], tuple[int, int]] = {}
        for row in conn.execute(
            "SELECT id, paiement_id, facture_id, billet_index FROM paiement_lignes "
            "WHERE facture_id IS NOT NULL AND billet_index IS NOT NULL ORDER BY id"
        ):
            key = (row["facture_id"], row["billet_index"])
            if key in self.refs:
                self.links.setdefault(key, (row["paiement_id"], row["id"]))

    def links_except(self, ligne_id: int | None) -> dict[tuple[int, int], int]:
        return {k: pid for k, (pid, lid) in self.links.items() if lid != ligne_id}

    def billet_json(self, facture_id: int, billet_index: int, **extra) -> dict:
        ref = self.refs.get((facture_id, billet_index))
        numero, client_nom = self.factures.get(facture_id, ("", ""))
        return {
            "facture_id": facture_id, "billet_index": billet_index,
            "facture_numero": numero, "client_nom": client_nom,
            "numero_billet": ref.numero_billet if ref else "",
            "date_billet": ref.date_billet if ref else "",
            "plaque": ref.plaque if ref else "",
            **extra,
        }


def _as_parsed(row: Mapping) -> ParsedLigne:
    return ParsedLigne(
        numero_billet=row["numero_billet"],
        numero_candidates=(row["numero_billet"],),
        date_billet=row["date_billet"],
        plaque=row["plaque"],
        quantite=row["quantite"],
        prix=None,
        montant=row["montant"],
    )


def _ligne_json(row: Row, ctx: _Context) -> dict:
    base = {k: row[k] for k in (
        "id", "numero_billet", "date_billet", "plaque", "quantite", "montant",
    )}
    key = (row["facture_id"], row["billet_index"])
    if row["facture_id"] is not None and key in ctx.refs:
        numero, client_nom = ctx.factures.get(row["facture_id"], ("", ""))
        return {
            **base, "facture_id": key[0], "billet_index": key[1],
            "facture_numero": numero, "client_nom": client_nom,
            "methode": row["methode"], "statut": "lie",
            "doublon_paiement_id": None, "candidats": [],
        }
    result = matcher.match_ligne(_as_parsed(row), ctx.index, ctx.links_except(row["id"]))
    unlinked = {**base, "facture_id": None, "billet_index": None, "methode": "",
                "facture_numero": "", "client_nom": ""}
    if result.statut == "doublon":
        return {**unlinked, "statut": "doublon",
                "doublon_paiement_id": result.doublon_paiement_id,
                "candidats": [ctx.billet_json(result.facture_id, result.billet_index,
                                              raison="doublon")]}
    if result.statut == "lie":
        # A match is available but not held (the user unlinked it, or the
        # payment that held it was deleted): offer it, never re-link silently.
        return {**unlinked, "statut": "non_lie", "doublon_paiement_id": None,
                "candidats": [ctx.billet_json(result.facture_id, result.billet_index,
                                              raison=result.methode)]}
    return {**unlinked, "statut": "non_lie", "doublon_paiement_id": None,
            "candidats": [ctx.billet_json(c.facture_id, c.billet_index, raison=c.raison)
                          for c in result.candidats]}


def _statut_global(lignes: list[dict]) -> str:
    if any(ligne["statut"] != "lie" for ligne in lignes):
        return "a_verifier"
    return "complet" if lignes else "partiel"


# ── Auto-paid ─────────────────────────────────────────────────────────────

def _recompute_paid(conn: Connection, facture_ids: Iterable[int | None]) -> None:
    ids = sorted({fid for fid in facture_ids if fid is not None})
    if not ids:
        return
    marks = ",".join("?" * len(ids))
    factures = conn.execute(
        f"SELECT id, billets_json, paye, paye_auto FROM factures WHERE id IN ({marks})", ids,
    ).fetchall()
    linked: dict[int, set[int]] = {}
    for row in conn.execute(
        f"SELECT DISTINCT facture_id, billet_index FROM paiement_lignes "
        f"WHERE facture_id IN ({marks}) AND billet_index IS NOT NULL", ids,
    ):
        linked.setdefault(row["facture_id"], set()).add(row["billet_index"])
    for f in factures:
        n = len(matcher.build_index([dict(f)]))
        covered = len({i for i in linked.get(f["id"], set()) if 0 <= i < n})
        full = n > 0 and covered == n
        if f["paye_auto"]:
            if not full:
                conn.execute("UPDATE factures SET paye = 0, paye_auto = 0 WHERE id = ?", (f["id"],))
        elif full and not f["paye"]:
            conn.execute("UPDATE factures SET paye = 1, paye_auto = 1 WHERE id = ?", (f["id"],))


# ── Payments ──────────────────────────────────────────────────────────────

def _detail(conn: Connection, paiement_id: int, ctx: _Context | None = None) -> dict:
    row = conn.execute(
        f"SELECT {_DETAIL_COLUMNS} FROM paiements WHERE id = ?", (paiement_id,),
    ).fetchone()
    if not row:
        raise PaymentNotFound(paiement_id)
    ctx = ctx or _Context(conn)
    lignes = conn.execute(
        f"SELECT {_LIGNE_COLUMNS} FROM paiement_lignes WHERE paiement_id = ? ORDER BY id",
        (paiement_id,),
    ).fetchall()
    return {**dict(row), "lignes": [_ligne_json(ligne, ctx) for ligne in lignes]}


def _insert_ligne(conn: Connection, paiement_id: int, ligne: ParsedLigne,
                  ctx: _Context) -> tuple[int, int | None]:
    """Match and insert one ligne; returns (ligne_id, linked facture_id or None)."""
    result = matcher.match_ligne(ligne, ctx.index, ctx.links_except(None))
    numero, date, plaque, quantite = (
        ligne.numero_billet, ligne.date_billet, ligne.plaque, ligne.quantite,
    )
    fid = idx = None
    methode = ""
    if result.statut == "lie":
        fid, idx, methode = result.facture_id, result.billet_index, result.methode
        ref = ctx.refs[(fid, idx)]
        if methode == "numero":
            numero = ref.numero_billet  # the wrap candidate that actually matched
        date, plaque = date or ref.date_billet, plaque or ref.plaque
        quantite = ref.quantite if quantite is None else quantite
    cur = conn.execute(
        "INSERT INTO paiement_lignes (paiement_id, numero_billet, date_billet, plaque, "
        "quantite, montant, facture_id, billet_index, methode) VALUES (?,?,?,?,?,?,?,?,?)",
        (paiement_id, numero, date, plaque, quantite, ligne.montant, fid, idx, methode),
    )
    if fid is not None:
        ctx.links[(fid, idx)] = (paiement_id, cur.lastrowid)
    return cur.lastrowid, fid


def create_paiement(doc: ParsedDoc, texte: str, fichier: str, nom_original: str) -> dict:
    """Store a parsed proof of payment, link what matches, update paid invoices."""
    with _transaction() as conn:
        cur = conn.execute(
            "INSERT INTO paiements (emetteur, reference, date, sous_total, tps, tvq, "
            "escompte, total, fichier, nom_original, texte) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (doc.emetteur, doc.reference, doc.date, doc.sous_total, doc.tps, doc.tvq,
             doc.escompte, doc.total, fichier, nom_original, texte),
        )
        paiement_id = cur.lastrowid
        ctx = _Context(conn)
        linked = [_insert_ligne(conn, paiement_id, ligne, ctx)[1] for ligne in doc.lignes]
        _recompute_paid(conn, linked)
        return _detail(conn, paiement_id, ctx)


def get_paiement(paiement_id: int) -> dict:
    with _reading() as conn:
        return _detail(conn, paiement_id)


def list_paiements() -> list[dict]:
    """Every payment, newest first, with its matching summary (a fixed 4 queries)."""
    with _reading() as conn:
        ctx = _Context(conn)
        rows = conn.execute(
            "SELECT id, emetteur, reference, date, sous_total, escompte, total, "
            "nom_original, cree_le FROM paiements ORDER BY date DESC, id DESC"
        ).fetchall()
        by_paiement: dict[int, list[dict]] = {}
        for ligne in conn.execute(f"SELECT {_LIGNE_COLUMNS} FROM paiement_lignes ORDER BY id"):
            by_paiement.setdefault(ligne["paiement_id"], []).append(_ligne_json(ligne, ctx))
    summaries = []
    for row in rows:
        lignes = by_paiement.get(row["id"], [])
        summaries.append({
            **dict(row),
            "statut_global": _statut_global(lignes),
            "nb_lignes": len(lignes),
            "nb_lignes_liees": sum(ligne["statut"] == "lie" for ligne in lignes),
        })
    return summaries


def update_paiement(paiement_id: int, fields: Mapping) -> dict:
    """Edit header fields (whitelisted); unknown keys are ignored."""
    changes = {k: v for k, v in fields.items() if k in _HEADER_FIELDS}
    with _transaction() as conn:
        if not conn.execute("SELECT 1 FROM paiements WHERE id = ?", (paiement_id,)).fetchone():
            raise PaymentNotFound(paiement_id)
        if changes:
            # Column names come from the _HEADER_FIELDS whitelist, never from input.
            assignments = ", ".join(f"{k} = ?" for k in changes)
            conn.execute(
                f"UPDATE paiements SET {assignments} WHERE id = ?",
                (*changes.values(), paiement_id),
            )
        return _detail(conn, paiement_id)


def delete_paiement(paiement_id: int) -> str:
    """Delete a payment and its lignes; returns its stored file name."""
    with _transaction() as conn:
        row = conn.execute("SELECT fichier FROM paiements WHERE id = ?", (paiement_id,)).fetchone()
        if not row:
            raise PaymentNotFound(paiement_id)
        affected = [r["facture_id"] for r in conn.execute(
            "SELECT DISTINCT facture_id FROM paiement_lignes WHERE paiement_id = ?", (paiement_id,),
        )]
        conn.execute("DELETE FROM paiements WHERE id = ?", (paiement_id,))  # lignes cascade
        _recompute_paid(conn, affected)
        return row["fichier"]


# ── Lignes ────────────────────────────────────────────────────────────────

def _ligne_row(conn: Connection, ligne_id: int) -> Row:
    row = conn.execute(
        f"SELECT {_LIGNE_COLUMNS} FROM paiement_lignes WHERE id = ?", (ligne_id,),
    ).fetchone()
    if not row:
        raise LigneNotFound(ligne_id)
    return row


def add_ligne_manuelle(paiement_id: int, numero_billet: str) -> dict:
    """Add a billet the PDF did not list, matched by its number alone."""
    numero = tidy_billet_number(numero_billet)
    with _transaction() as conn:
        if not conn.execute("SELECT 1 FROM paiements WHERE id = ?", (paiement_id,)).fetchone():
            raise PaymentNotFound(paiement_id)
        ctx = _Context(conn)
        ligne = ParsedLigne(numero, (numero,), "", "", None, None, None)
        ligne_id, fid = _insert_ligne(conn, paiement_id, ligne, ctx)
        _recompute_paid(conn, [fid])
        return _ligne_json(_ligne_row(conn, ligne_id), ctx)


def link_ligne(ligne_id: int, facture_id: int, billet_index: int) -> dict:
    """Link a ligne to a billet the user picked (methode "manuel")."""
    with _transaction() as conn:
        row = _ligne_row(conn, ligne_id)
        ctx = _Context(conn)
        key = (facture_id, billet_index)
        if key not in ctx.refs:
            raise InvalidBillet(key)
        holder = ctx.links.get(key)
        if holder and holder[1] != ligne_id:
            raise LinkConflict(holder[0])
        conn.execute(
            "UPDATE paiement_lignes SET facture_id = ?, billet_index = ?, methode = 'manuel' "
            "WHERE id = ?", (facture_id, billet_index, ligne_id),
        )
        ctx.links = {k: v for k, v in ctx.links.items() if v[1] != ligne_id}
        ctx.links[key] = (row["paiement_id"], ligne_id)
        _recompute_paid(conn, [row["facture_id"], facture_id])
        return _ligne_json(_ligne_row(conn, ligne_id), ctx)


def unlink_ligne(ligne_id: int) -> dict:
    with _transaction() as conn:
        row = _ligne_row(conn, ligne_id)
        conn.execute(
            "UPDATE paiement_lignes SET facture_id = NULL, billet_index = NULL, methode = '' "
            "WHERE id = ?", (ligne_id,),
        )
        _recompute_paid(conn, [row["facture_id"]])
        return _ligne_json(_ligne_row(conn, ligne_id), _Context(conn))


def delete_ligne(ligne_id: int) -> None:
    with _transaction() as conn:
        row = _ligne_row(conn, ligne_id)
        conn.execute("DELETE FROM paiement_lignes WHERE id = ?", (ligne_id,))
        _recompute_paid(conn, [row["facture_id"]])


# ── Invoice edits ─────────────────────────────────────────────────────────

def _billet_as_ligne(billet) -> ParsedLigne | None:
    """An invoiced billet, shaped as a ligne so the matcher can look it up."""
    if not isinstance(billet, dict):
        return None
    ref = matcher.billet_ref(0, 0, billet)
    return ParsedLigne(ref.numero_billet, (ref.numero_billet,), ref.date_billet,
                       ref.plaque, ref.quantite, None, None)


def _resolve_after_edit(ligne: Row, old_billet: ParsedLigne | None,
                        index: list, taken: dict) -> tuple[int, int] | None:
    """Where a linked billet went: first by the billet's own previous identity
    (keeps manual links), then by what the payment itself says."""
    keys = [k for k in (old_billet, _as_parsed(ligne)) if k is not None]
    for key in keys:
        result = matcher.match_ligne(key, index, taken)
        if result.statut == "lie":
            return result.facture_id, result.billet_index
    return None


def _relink(conn: Connection, facture_ids: list[int], previous: Mapping[int, str]) -> None:
    marks = ",".join("?" * len(facture_ids))
    lignes = conn.execute(
        f"SELECT {_LIGNE_COLUMNS} FROM paiement_lignes WHERE facture_id IN ({marks}) ORDER BY id",
        facture_ids,
    ).fetchall()
    if lignes:
        factures = conn.execute(
            f"SELECT id, billets_json FROM factures WHERE id IN ({marks})", facture_ids,
        ).fetchall()
        index = matcher.build_index([dict(f) for f in factures])
        old_billets = {fid: matcher.billets_from_json(raw) for fid, raw in previous.items()}
        # Phase 1: release every link, so a swap never trips the unique index.
        conn.execute(
            f"UPDATE paiement_lignes SET facture_id = NULL, billet_index = NULL "
            f"WHERE facture_id IN ({marks})", facture_ids,
        )
        # Phase 2: re-seat each link on the billet it points at now, or drop it.
        taken: dict[tuple[int, int], int] = {}
        for ligne in lignes:
            olds = old_billets.get(ligne["facture_id"], [])
            idx = ligne["billet_index"]
            old = _billet_as_ligne(olds[idx]) if idx is not None and 0 <= idx < len(olds) else None
            target = _resolve_after_edit(ligne, old, index, taken)
            if target is None:
                conn.execute("UPDATE paiement_lignes SET methode = '' WHERE id = ?", (ligne["id"],))
                continue
            taken[target] = ligne["paiement_id"]
            conn.execute(
                "UPDATE paiement_lignes SET facture_id = ?, billet_index = ? WHERE id = ?",
                (*target, ligne["id"]),
            )
    _recompute_paid(conn, facture_ids)


def relink_after_invoice_edit(conn: Connection | None, facture_ids: Iterable[int],
                              previous: Mapping[int, str] | None = None) -> None:
    """Re-seat payment links after invoices' billets were rewritten.

    Links are positional (billet_index), so reordering, inserting or removing
    billets — or a split moving billets to new invoices — would otherwise point
    them at the wrong billet. `facture_ids` must cover every invoice the edit
    touched (the edited one plus any split created by the same request);
    `previous` maps facture_id -> billets_json BEFORE the edit, which lets a
    link (manual ones included) follow its billet. A billet that is gone is
    unlinked. Paid state is recomputed for every touched invoice.
    """
    ids = sorted({int(fid) for fid in facture_ids})
    if not ids:
        return
    if conn is not None:
        _relink(conn, ids, previous or {})
        return
    with _transaction() as tx:
        _relink(tx, ids, previous or {})


# ── Reverse lookups ───────────────────────────────────────────────────────

def factures_paiements(facture_id: int) -> dict | None:
    """Per-billet paid state of one invoice, plus the payments linked to its billets."""
    with _reading() as conn:
        facture = conn.execute(
            "SELECT id, billets_json FROM factures WHERE id = ?", (facture_id,),
        ).fetchone()
        if not facture:
            return None
        links: dict[int, dict] = {}
        for row in conn.execute(
            "SELECT l.billet_index, l.paiement_id, p.reference FROM paiement_lignes l "
            "JOIN paiements p ON p.id = l.paiement_id "
            "WHERE l.facture_id = ? AND l.billet_index IS NOT NULL ORDER BY l.id",
            (facture_id,),
        ):
            links.setdefault(row["billet_index"], {
                "paiement_id": row["paiement_id"], "reference": row["reference"],
            })
    count = len(matcher.billets_from_json(facture["billets_json"]))
    billets = []
    for i in range(count):
        link = links.get(i)
        billets.append({
            "index": i, "paye": link is not None,
            "paiement_id": link["paiement_id"] if link else None,
            "reference": link["reference"] if link else "",
        })
    paiements: dict[int, dict] = {}
    for b in billets:
        if b["paye"]:
            paiements.setdefault(b["paiement_id"], {
                "paiement_id": b["paiement_id"], "reference": b["reference"],
            })
    return {"billets": billets, "paiements": list(paiements.values())}


def paid_billets() -> dict[tuple[int, int], dict]:
    """{(facture_id, billet_index): {"paiement_id", "reference"}} — one query."""
    with _reading() as conn:
        rows = conn.execute(
            "SELECT l.facture_id, l.billet_index, l.paiement_id, p.reference "
            "FROM paiement_lignes l JOIN paiements p ON p.id = l.paiement_id "
            "WHERE l.facture_id IS NOT NULL AND l.billet_index IS NOT NULL ORDER BY l.id"
        ).fetchall()
    paid: dict[tuple[int, int], dict] = {}
    for r in rows:
        paid.setdefault((r["facture_id"], r["billet_index"]),
                        {"paiement_id": r["paiement_id"], "reference": r["reference"]})
    return paid

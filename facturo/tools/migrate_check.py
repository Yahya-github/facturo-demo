"""Migration dry run: prove schema.migrate() leaves every invoice total unchanged.

    python -m facturo.tools.migrate_check <path/to/data.db>

Works on a temporary copy (plus its -wal side file, if any): the given
database is only ever read. scripts/release.sh runs this before tagging.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from facturo.core import schema
from facturo.invoicing import discounts

TOLERANCE = 0.01


def _live_legacy_montant(facture: dict) -> float:
    """The v1 invoice-level fixed amount still in force on this row, else 0.

    It is in force when remise_type is "montant" and neither v2 field is set
    (before migration, v2 columns are absent or 0).
    """
    if facture.get("remise_type") != "montant":
        return 0.0
    if discounts._to_float(facture.get("remise_pct")) or discounts._to_float(
            facture.get("remise_montant")):
        return 0.0
    return max(0.0, discounts._to_float(facture.get("remise_valeur")))


def _invoice_total(row: sqlite3.Row) -> float:
    """TOTAL DÛ with the semantics of the version that wrote the row.

    v1 took an invoice-level fixed amount off EVERY billet, clamped to that
    billet's own net; v2 spends it once. Pricing v1 data with v2 math would
    flag a correct migration as a total change.
    """
    billets = json.loads(row["billets_json"] or "[]")
    facture = dict(row)
    montant = _live_legacy_montant(facture)
    if not montant:
        return discounts.invoice_totals(billets, facture).total
    base = sum(max(0.0, discounts.billet_net(b) - montant) for b in billets)
    return base * (1 + discounts.TPS_RATE + discounts.TVQ_RATE)


def _make_default_total(skipped: list[int]) -> Callable[[sqlite3.Connection], float]:
    """Sum of every invoice's TOTAL DÛ, as the app computes it.

    Rows whose billets cannot be priced (malformed JSON, missing fields) are
    counted in `skipped` for the report instead of silently adding 0.
    """

    def total(conn: sqlite3.Connection) -> float:
        conn.row_factory = sqlite3.Row
        grand, bad = 0.0, 0
        for row in conn.execute("SELECT * FROM factures ORDER BY id"):
            try:
                grand += _invoice_total(row)
            except (ValueError, TypeError, KeyError, AttributeError):
                bad += 1
        skipped.append(bad)
        return grand

    return total


def _copy_db(src: Path, dest_dir: Path) -> Path:
    dest = dest_dir / "data.db"
    shutil.copyfile(src, dest)
    wal = src.with_name(src.name + "-wal")
    if wal.exists():
        shutil.copyfile(wal, dest.with_name(dest.name + "-wal"))
    return dest


def check(db_path: Path, *, total_fn: Callable[[sqlite3.Connection], float] | None = None) -> dict:
    """Migrate a copy of `db_path` and compare invoice totals before/after."""
    skipped: list[int] = []
    if total_fn is None:
        total_fn = _make_default_total(skipped)

    with tempfile.TemporaryDirectory(prefix="facturo-migrate-check-") as tmp:
        copy = _copy_db(Path(db_path), Path(tmp))
        conn = sqlite3.connect(str(copy))
        try:
            before_total = float(total_fn(conn))
            schema.migrate(conn)
            after_total = float(total_fn(conn))
        finally:
            conn.close()

    diff = abs(before_total - after_total)
    ok = diff <= TOLERANCE
    if ok:
        message = f"Migration OK : total des factures {before_total:.2f} $ inchangé."
    else:
        message = (f"ÉCHEC : total des factures différent après migration "
                   f"(avant {before_total:.2f} $, après {after_total:.2f} $, écart {diff:.2f} $).")
    if skipped and any(skipped):
        message += f" {max(skipped)} facture(s) illisible(s) ignorée(s)."
    return {"ok": ok, "before_total": before_total, "after_total": after_total, "message": message}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("Usage : python -m facturo.tools.migrate_check <data.db>", file=sys.stderr)
        return 1
    db_path = Path(argv[0])
    if not db_path.is_file():
        print(f"Erreur : base de données introuvable : {db_path}", file=sys.stderr)
        return 1
    try:
        result = check(db_path)
    except (sqlite3.Error, OSError) as e:
        print(f"Erreur : vérification impossible ({e}).", file=sys.stderr)
        return 1
    print(result["message"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

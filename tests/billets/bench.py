"""Score ai_extract against the hand-verified billet ground truth.

The regression guard for extraction accuracy. Unit tests cover the pure field
parsing; this covers whether the model, the prompts, the crop bands and the
history snapping still read a real ticket correctly end to end. Any change to
prompts, schema field order, crop bands or snapping must be measured here
before it is believed.

    venv/bin/python tests/billets/bench.py                     # local, auto-picked model
    venv/bin/python tests/billets/bench.py qwen2.5vl:7b        # a specific local model
    venv/bin/python tests/billets/bench.py gemma4:31b-cloud    # hosted, via `ollama signin`
    venv/bin/python tests/billets/bench.py ground_truth_vrac.json qwen2.5vl:7b

Reads the pre-rendered pages/*.jpg — it never re-renders, so a scoring run
measures extraction only. Those images are real client tickets and are
gitignored; see .gitignore. Expected today: 36/36 on ground_truth.json and
24/24 on ground_truth_vrac.json with qwen2.5vl:7b.

Needs `ollama serve` running, and a GPU not busy with anything else — another
process holding ~900 MB of VRAM pushes a page from ~6 s to ~60 s.
"""
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from facturo.extraction import (
    ai_extract,  # noqa: E402
    scan_render,  # noqa: E402
)


def history() -> ai_extract.History:
    """Mirror app.py's _history so the bench scores the prod code path.

    Without it the bench never exercises _snap_chantier or _snap_plate, and so
    reports an accuracy the running app does not actually have."""
    from facturo.core import database as db
    chantiers: dict[str, int] = {}
    plaques: dict[str, int] = {}
    for facture in db.list_factures():
        try:
            billets = json.loads(facture.get("billets_json") or "[]")
        except (ValueError, TypeError):
            continue
        for b in billets:
            for key, counts in (("chantier", chantiers), ("plaque", plaques)):
                v = str(b.get(key) or "").strip()
                if v:
                    counts[v] = counts.get(v, 0) + 1
    return ai_extract.History(
        chantiers=sorted(chantiers, key=chantiers.get, reverse=True),
        plaques=sorted(plaques, key=plaques.get, reverse=True),
    )

SC = Path(__file__).parent
# argv[1] may name a ground-truth file (default: the RENTAL/OWN/LOC set).
_TRUTH_FILE = "ground_truth.json"
if len(sys.argv) > 1 and sys.argv[1].endswith(".json"):
    _TRUTH_FILE = sys.argv.pop(1)
TRUTH = json.loads((SC / _TRUTH_FILE).read_text())

FIELDS = ("numero_billet", "chantier", "plaque", "quantite", "taux", "date_billet")


def norm_text(s: str) -> str:
    """Loose compare: case/accent/punctuation insensitive (M-RIVARD == M. RIVARD,
    'La Henard' == 'La Hénard'). Accents are a transcription detail the user does
    not care about on a client name, so they must not count as an error."""
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s)


def match(field: str, got, want) -> bool:
    if field in ("quantite", "taux"):
        try:
            return abs(float(got or 0) - float(want or 0)) < 0.01
        except (TypeError, ValueError):
            return False
    return norm_text(got) == norm_text(want)


def main() -> None:
    # Target any host/model without touching ai_config.json, so benchmarking a
    # hosted model never changes what the installed app does. The key is read
    # from the environment and never printed.
    import os
    model = sys.argv[1] if len(sys.argv) > 1 else ""
    host = os.environ.get("BENCH_HOST", "http://127.0.0.1:11434")
    cfg = {"model": model, "host": host,
           "api_key": os.environ.get("OLLAMA_API_KEY", "")}
    if not model:
        cfg["model"] = ai_extract._pick_model(cfg)
    hist = history()
    where = "cloud" if cfg["api_key"] else "local"
    print(f"model: {cfg['model']} ({where} {cfg['host']})  |  history: "
          f"{len(hist.chantiers)} chantiers, {len(hist.plaques)} plaques\n")

    totals = {f: 0 for f in FIELDS}
    rows = []
    for case in TRUTH:
        img = (SC / "pages" / case["page"]).read_bytes()
        t0 = time.time()
        try:
            got = ai_extract.extract_from_jpeg(
                scan_render.image_to_jpeg(img), cfg, hist)
            err = None
        except Exception as e:  # noqa: BLE001
            got, err = {}, str(e)[:70]
        dt = time.time() - t0

        marks = []
        for f in FIELDS:
            ok = (not err) and match(f, got.get(f), case[f])
            totals[f] += ok
            marks.append("Y" if ok else "n")
        rows.append((case["page"], case["layout"], "".join(marks), dt, got, err, case))

    hdr = "  ".join(f[:9].rjust(9) for f in FIELDS)
    print(f"{'page':16s} {'lay':5s} {hdr}   sec")
    for page, lay, marks, dt, got, err, case in rows:
        cells = "  ".join(m.rjust(9) for m in marks)
        print(f"{page:16s} {lay:5s} {cells}  {dt:5.1f}")
        if err:
            print(f"    ERROR: {err}")
        else:
            for f, m in zip(FIELDS, marks, strict=True):
                if m == "n":
                    print(f"    {f}: got {got.get(f)!r} want {case[f]!r}")

    n = len(TRUTH)
    print()
    for f in FIELDS:
        print(f"  {f:14s} {totals[f]}/{n}")
    total = sum(totals.values())
    print(f"\n  OVERALL {total}/{n * len(FIELDS)} = {100 * total / (n * len(FIELDS)):.0f}%")


if __name__ == "__main__":
    main()

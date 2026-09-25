#!/usr/bin/env python3
"""Fill a running Facturo server with fictional demo data.

Usage (server already running, e.g. `python -m facturo` or uvicorn):

    python scripts/seed_demo.py                      # http://127.0.0.1:8000
    python scripts/seed_demo.py --base http://127.0.0.1:8123

Creates 5 fictional clients, 25 invoices spread over the last six months
(some paid, some partly paid, some unpaid) and three proofs of payment.
Everything goes through the public HTTP API, so the data is exactly what the
UI would have produced. Standard library only.

Safe to run twice: clients are matched by ref, invoices by number and
payments by reference, and anything that already exists is left alone.
Amounts are deterministic; dates count back from today.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta

CLIENTS = [
    # ref, prefix, name, address, hourly rate
    ("NWE", "nwe", "Northwind Excavation", "12 chemin des Carrières, Laval, QC", 118.0),
    ("BEL", "bel", "Béton Élan Inc", "480 boulevard Industriel, Terrebonne, QC", 124.0),
    ("TLA", "tla", "Transport Laurent", "77 rue du Dépôt, Saint-Jérôme, QC", 112.0),
    ("VRH", "vrh", "Vrac Horizon", "3 route 158, Joliette, QC", 121.0),
    ("ABM", "abm", "Asphalte Bellevue Média", "905 rue des Ormes, Longueuil, QC", 116.0),
]
SITES = [
    "Chantier Pont Rivière-Claire", "Carrière du Nord", "Lot 14 Domaine des Pins",
    "Réfection rue Principale", "Entrepôt Delta", "Bassin de rétention Est",
    "Prolongement boulevard Sud", "Stationnement Centre Sportif",
]
PLATES = ["L 482913", "L 517204", "L 630881", "G 204417", "G 351290", "L 709446"]
N_INVOICES = 25
DAYS_BACK = 180
FIRST_TICKET = 71000


def call(base: str, method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path, data=data, method=method, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        sys.exit(f"{method} {path} -> HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"Cannot reach {base} ({e.reason}). Start the app first.")


def ensure_clients(base: str) -> dict[str, dict]:
    existing = {c["ref"]: c for c in call(base, "GET", "/api/clients")}
    out = {}
    for ref, prefix, nom, adresse, taux in CLIENTS:
        if ref in existing:
            out[ref] = existing[ref]
            continue
        out[ref] = call(base, "POST", "/api/clients", {
            "ref": ref, "prefix": prefix, "nom": nom, "adresse": adresse, "taux_defaut": taux,
        })
        print(f"client  {nom}")
    return out


def plan_invoices(today: date) -> list[dict]:
    """The deterministic list of invoices to create, oldest first."""
    rng = random.Random(2026)
    per_client = {c[0]: 0 for c in CLIENTS}
    ticket = FIRST_TICKET
    plans = []
    for i in range(N_INVOICES):
        ref, prefix, _nom, _adr, taux = rng.choices(CLIENTS, (5, 4, 3, 3, 2))[0]
        per_client[ref] += 1
        day = today - timedelta(days=DAYS_BACK - round(i * (DAYS_BACK - 4) / (N_INVOICES - 1)))
        billets = []
        for _ in range(rng.choice([1, 2, 2, 3, 4])):
            ticket += 1
            when = day - timedelta(days=rng.randint(0, 5))
            billets.append({
                "date_billet": when.isoformat(),
                "chantier": rng.choice(SITES),
                "plaque": rng.choice(PLATES),
                "numero_billet": str(ticket),
                "quantite": float(rng.choice([4, 5, 6, 7.5, 8, 9, 10, 12, 16, 24])),
                "taux": taux,
            })
        plans.append({
            "ref": ref, "numero": f"{prefix}{per_client[ref]:03d}", "date": day.isoformat(),
            "billets": billets,
        })
    return plans


def create_invoices(base: str, clients: dict[str, dict], plans: list[dict]) -> None:
    have = {f["numero"] for f in call(base, "GET", "/api/factures")}
    for p in plans:
        if p["numero"] in have:
            continue
        call(base, "POST", "/api/factures/generate", {
            "client_id": clients[p["ref"]]["id"], "numero": p["numero"],
            "date": p["date"], "billets": p["billets"],
        })
        print(f"facture {p['numero']}  {p['date']}  {len(p['billets'])} billet(s)")


def mark_paid(base: str, plans: list[dict]) -> None:
    """Older invoices are paid outright (about 60%), the rest stay open.
    The newest six are never marked, so Accueil shows unpaid amounts."""
    by_numero = {f["numero"]: f for f in call(base, "GET", "/api/factures")}
    for i, p in enumerate(plans[: N_INVOICES - 6]):
        f = by_numero.get(p["numero"])
        if f and i % 5 in (0, 1, 3) and not f.get("paye"):
            call(base, "PATCH", f"/api/factures/{f['id']}/paye", {"paye": True})


def text_pdf(lines: list[str]) -> bytes:
    """A one-page PDF with a real text layer (same layout as the test helper)."""
    parts = ["BT", "/F1 11 Tf", "14 TL", "50 750 Td"]
    for i, line in enumerate(lines):
        esc = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        parts += (["T*"] if i else []) + [f"({esc}) Tj"]
    parts.append("ET")
    content = "\n".join(parts).encode("latin-1", "replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for n, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)


def upload_pdf(base: str, name: str, raw: bytes) -> None:
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{name}\"\r\nContent-Type: application/pdf\r\n\r\n"
    ).encode() + raw + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        base + "/api/paiements", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        urllib.request.urlopen(req, timeout=60).read()
    except urllib.error.HTTPError as e:
        print(f"paiement {name}: HTTP {e.code} {e.read().decode(errors='replace')[:200]}")


def fr(n: float) -> str:
    return f"{n:,.2f}".replace(",", " ").replace(".", ",") + " $"


def payment_lines(issuer: str, ref: str, when: date, client: str, billets: list[dict]) -> list[str]:
    lines = [when.strftime("%d-%m-%Y"), issuer, "1 rue Fictive", "Montréal, QC H0H 0H0",
             f"Quittance # {ref}", "BILLET DATE IMMAT CLIENT / CHANTIER / NOTES QTE PRIX EXT"]
    total = 0.0
    for b in billets:
        amount = b["quantite"] * b["taux"]
        total += amount
        d = date.fromisoformat(b["date_billet"]).strftime("%d-%m-%Y")
        qty = f"{b['quantite']:g}".replace(".", ",")
        lines.append(f"{client} / {b['chantier']} {qty} {fr(b['taux'])} {fr(amount)}")
        lines.append(f"{b['numero_billet']} {d} {b['plaque'].replace(' ', '').lower()}")
    lines.append(f"TOTAL: {fr(total)}")
    return lines


def import_payments(base: str, plans: list[dict]) -> None:
    """Three proofs of payment: one covering a whole invoice, two covering only
    the first billet of a multi-billet invoice (those show as partly paid)."""
    known = {p.get("reference") for p in call(base, "GET", "/api/paiements")}
    by_numero = {f["numero"]: f for f in call(base, "GET", "/api/factures")}
    open_multi = [p for p in plans[: N_INVOICES - 6]
                  if len(p["billets"]) >= 2 and not by_numero.get(p["numero"], {}).get("paye")]
    for idx, plan in enumerate(open_multi[:3]):
        ref = f"700-{idx + 1:03d}"
        if ref in known:
            continue
        chosen = plan["billets"] if idx == 0 else plan["billets"][:1]
        client = next(c[2] for c in CLIENTS if c[0] == plan["ref"])
        when = date.fromisoformat(plan["date"]) + timedelta(days=21)
        lines = payment_lines("Groupe Fictif Matériaux Inc.", ref, when, client, chosen)
        upload_pdf(base, f"quittance-{ref}.pdf", text_pdf(lines))
        print(f"paiement {ref}  {len(chosen)} ligne(s) -> {plan['numero']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="server URL")
    base = ap.parse_args().base.rstrip("/")
    clients = ensure_clients(base)
    plans = plan_invoices(date.today())
    create_invoices(base, clients, plans)
    mark_paid(base, plans)
    import_payments(base, plans)
    print("done")


if __name__ == "__main__":
    main()

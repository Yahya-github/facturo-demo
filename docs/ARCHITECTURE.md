# Facturo v2 Architecture

**Schema version:** 2 (current)

## Overview

Facturo is a single-user local invoicing app. The backend (FastAPI) runs on `127.0.0.1` with zero authentication. The frontend (vanilla JS) communicates via HTTP from the same machine. All persistent data lives in SQLite. Multi-device sync flows through a separate private data repository on GitHub, never through the app source repo.

## Modules & responsibilities

| Module | Responsibility | Key exports |
|--------|-----------------|-------------|
| `paths.py` | All filesystem paths (data dir, DB, assets); handles dev vs. frozen exe | `app_dir()`, `db_path()`, `bundle_dir()`, `IS_FROZEN` |
| `server.py` | FastAPI app factory, middleware setup, router mounting | `app` (FastAPI instance) |
| `local_guard.py` | Middleware blocking non-127.0.0.1 requests | `LocalGuardMiddleware` |
| `version.py` | Current app version string | `__version__` |
| **core/** | | |
| `database.py` | SQLite connection pooling, CRUD for all tables, backups | `init_db()`, `get_facture()`, `list_factures()`, etc. |
| `schema.py` | Table definitions, idempotent migrations, versioning | `SCHEMA_VERSION`, `migrate()`, `is_newer_than_app()` |
| `billet_fields.py` | Billet normalization: plates, numbers, dates | `tidy_plate()`, `tidy_billet_number()`, `normalize_date()` |
| `known_values.py` | Seeding & CRUD for truck plates, sites autocomplete | `seed()`, `sync_known_values()` |
| **api/** | | |
| `factures.py` | Invoice CRUD: create, read, update, delete, set paid flag | `POST/GET/PATCH /api/factures/...` |
| `invoice_list.py` | List & summaries (with discounts math), filters by status/client/date/text | `GET /api/factures?filter=...` |
| `clients.py` | Client CRUD, autocomplete | `GET/POST /api/clients` |
| `scans.py` | Receipt upload, retrieval by ID | `POST/GET /api/scans/...` |
| `ai.py` | OCR extraction via Ollama (batch billet extraction from image) | `POST /api/ai/extract` |
| `known_values.py` | Autocomplete endpoint for plates & sites | `GET /api/known-values` |
| `payments.py` | Import PDFs, store payment records & their lines, list with filters | `POST/GET/PUT/DELETE /api/paiements/...` |
| `settings.py` | App settings (locale, data dir), sync & update config | `GET/PATCH /api/settings` |
| `sync.py` | Recevoir (pull from data repo), Envoyer (push), backups | `POST /api/sync/pull`, `POST /api/sync/push` |
| `updates.py` | Check version, download & install exe, status | `GET/POST /api/updates/check`, `POST /api/updates/install` |
| **invoicing/** | | |
| `discounts.py` | Invoice-total math (percent + fixed discounts at billet & invoice level, taxes TPS/TVQ, legacy migration) | `invoice_totals()`, `billet_net()`, `Totals` dataclass |
| `excel_generator.py` | .xlsx export (invoice detail, line-by-line, taxes, company logo) | `generate_xlsx()` |
| **extraction/** | | |
| `ai_extract.py` | OCR batch job via Ollama REST | `extract_billets()` |
| `scan_render.py` | PDF/image → text via pypdfium2 | `render_to_text()` |
| **payments/** | | |
| `store.py` | Query paid billets, link management (add/remove/confirm links) | `paid_billets()`, `factures_paiements()` |
| `pdf_text.py` | Extract text layer from PDF via pypdfium2 | `extract_text()` |
| `parser.py` | Parse header, totals, billet rows from text | `parse()`, `ParsedDoc` dataclass |
| `matcher.py` | Match parsed lines to invoice billets (numero, date+plate+qty) | `match_lignes()`, `MatchResult` dataclass |
| **services/** | | |
| `sync.py` | GitHub data repo sync (dulwich): push/pull, schema guard, backup | `pull()`, `push()`, `load_config()` |

## Data model

### Invoices table (`factures`)

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Unique invoice ID |
| client_id | INTEGER FK | References `clients(id)` |
| numero | TEXT | Invoice number (e.g. "CLI-001") |
| date | TEXT | ISO date (YYYY-MM-DD) |
| fichier | TEXT | Excel filename (e.g. "CLI-001.xlsx") |
| billets_json | TEXT | JSON array of work-order line items |
| cree_le | TEXT | ISO datetime, created |
| remise_pct | REAL | Invoice-level % discount (percent, >= 0) — v2 |
| remise_montant | REAL | Invoice-level fixed discount (dollars, >= 0) — v2 |
| paye | INTEGER | 1 = marked paid (0 = unpaid) |
| paye_auto | INTEGER | 1 = paid state was set automatically (all billets covered) — v2 |

**Billet JSON structure** (each item in `billets_json` array):
```json
{
  "id": "uuid",
  "numero": "123",
  "date": "2026-09-20",
  "chantier": "Site Name",
  "plaque": "ABC123",
  "description": "Work description",
  "quantite": 8.5,
  "taux": 100.0,
  "remise_pct": 0.0,
  "remise_montant": 0.0
}
```

**Legacy discount fields** (v1, cleared during v2 migration):
- `remise_type` (TEXT: "percent" | "montant" | "")
- `remise_valeur` (REAL)

The v1 invoice-level fixed discount was applied per billet; v2 applies it once. Migration converts each invoice's legacy montant into an effective per-billet cut, preserving total invoice amounts.

### Payments tables (v2 schema)

**`paiements`** — one proof of payment (quittance / bill):

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Unique payment ID |
| client_id | INTEGER FK | NULL OK (payment may not name a known client) |
| emetteur | TEXT | Company name (who issued the payment) |
| reference | TEXT | Payment reference ("Quittance #...", "INVOICE #...") |
| date | TEXT | ISO date |
| sous_total | REAL | Subtotal (before tax) |
| tps | REAL | GST (5%) |
| tvq | REAL | QST (9.975%) |
| escompte | REAL | Discount/short payment (positive magnitude) |
| total | REAL | Total due |
| notes | TEXT | User notes |
| fichier | TEXT | Stored PDF filename |
| nom_original | TEXT | Original upload filename |
| texte | TEXT | Extracted text from PDF |
| cree_le | TEXT | ISO datetime |

**`paiement_lignes`** — one line (billet reference) on a payment:

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Line ID |
| paiement_id | INTEGER FK | References `paiements(id)` ON DELETE CASCADE |
| numero_billet | TEXT | Billet number as parsed |
| date_billet | TEXT | Billet date (ISO) |
| plaque | TEXT | Truck plate |
| quantite | REAL | Hours/units |
| montant | REAL | Amount (if present) |
| facture_id | INTEGER FK | NULL = unlinked; references `factures(id)` ON DELETE SET NULL |
| billet_index | INTEGER | Position in that facture's `billets_json` array; NULL = unlinked |
| methode | TEXT | Matching method: "" (none), "numero", "date_plaque", "manuel" |

A unique index ensures each billet is held by at most one line:
```sql
UNIQUE INDEX ON paiement_lignes(facture_id, billet_index) WHERE facture_id IS NOT NULL
```

A payment links billets only, never a whole invoice: `paiement_lignes` is the
single source of every link.

Lookup indexes `idx_paiement_lignes_facture` (`paiement_lignes(facture_id)`) and
`idx_factures_client_cree` (`factures(client_id, cree_le)`) belong to schema 2.
`migrate()` creates them with `CREATE INDEX IF NOT EXISTS` on every start, so v2
databases created before them gain them without a version change.

### Client & known-values tables

**`clients`**

| Column | Type |
|--------|------|
| id | INTEGER PK |
| ref | TEXT | Short code (e.g. "CLI") |
| prefix | TEXT | Invoice number prefix |
| nom | TEXT | Full name |
| adresse | TEXT | Address |
| next_numero | INTEGER | Next invoice number counter |

**`known_values`** — truck plates & sites (autocomplete, curated):

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| kind | TEXT | "plaque" or "chantier" |
| valeur | TEXT | User-facing value |
| cle | TEXT | Fold-normalized key (case/accent/space insensitive) |
| times_used | INTEGER | Hit count |
| last_used | TEXT | ISO datetime |
| curated | INTEGER | 1 = manually approved |
| hidden | INTEGER | 1 = hidden from autocomplete |
| alias_of | INTEGER FK | NULL or points to canonical entry |

## Request flow examples

### Create & export an invoice

1. Frontend: `POST /api/factures` with billets, discounts
2. `factures.py` validates via Pydantic, stores in DB
3. Frontend: `GET /api/factures/{id}`
4. `factures.py` fetches row; `discounts.invoice_totals()` computes Totals
5. Frontend: user clicks "Télécharger"
6. `factures.py` → `excel_generator.generate_xlsx()` (uses `facture_template.xlsx` from assets, writes `output/{invoice_number}.xlsx`)
7. Frontend downloads via `GET /api/factures/{id}/file`

### Import a payment PDF and mark billets as paid

1. Frontend: `POST /api/paiements` with PDF file
2. `payments.py`:
   - Validates PDF (magic bytes, size < 25 MB)
   - Calls `pdf_text.extract_text(bytes)` (via pypdfium2)
   - Calls `parser.parse(text)` → `ParsedDoc` (header, totals, lines)
   - Checks for a bill addressed to the company itself (reject with 422)
   - Stores `paiements` row + file
3. `payments.py` calls `matcher.match_lignes()` with parsed lines & index of all invoices' billets
   - Tries exact numero match
   - Falls back to date + plate + qty (±0.01)
   - Returns `MatchResult` per line (status: "lie" / "à vérifier" / "doublon")
4. `payments.py` automatically sets `paye=1, paye_auto=1` if all billets of an invoice are now covered
5. Frontend shows payment detail; user can link unmatched lines manually via `PUT /api/paiements/lignes/{ligne_id}`
6. On any link change, auto-paid flag is recomputed: reverts only if `paye_auto==1`

### Sync data to another device

1. Frontend: Paramètres → "Recevoir"
2. `sync.py::pull()`:
   - Opens private `facturo_data` repo with sync token
   - Pulls `data.db`, `output/`, `scans/`, `paiements/`, company logo
   - Validates schema guard: if pulled DB version > app version, raises error
   - Runs `schema.migrate()` on the pulled DB
   - On success, replaces local files
3. UI shows "✓ Synchronisé" or error toast

## Security model

- **Localhost only:** `LocalGuardMiddleware` rejects requests from `Host != 127.0.0.1`. Origin header checked if present.
- **No authentication:** Single-user desktop app. Token storage (sync, updates) is per-user in `update_config.json` / `sync_config.json`, never logged.
- **Input validation:** All user input (billets, files, searches) validated/sanitized before use. PDF uploads size-capped at 25 MB. Path traversal prevented (filename only, no `../`).
- **Schema versioning:** Pulling a DB from a newer app version is blocked; user is prompted to update.
- **File paths:** Assets read from bundle (trusted). Data files stored under `app_dir()` only. Sync pulls only allowed tree entries.

## Paths & directory layout

**Development (`python -m facturo`):**
```
data/
  data.db                      SQLite database
  output/                      Generated Excel files
  scans/                       Uploaded receipt PDFs
  paiements/                   Imported payment PDFs
  company_logo.png             Company logo (if uploaded)
  backups/                     Pre-sync/update backups
  sync_config.json             Sync token & settings (gitignored)
  update_config.json           Update token (gitignored)
```

**Frozen (Windows `Factures.exe`):**
```
C:\Users\Client\...\
  Factures.exe                 App executable
  data.db                      (same as dev)
  output/
  scans/
  paiements/
  company_logo.png
  backups/
  (+ configs, .old/.new variants during update)
```

**Assets (bundled in exe):**
```
facturo/
  assets/
    facture_template.xlsx      Excel invoice template
  web/
    templates/index.html       SPA shell
    static/
      css/                     app.css, filters.css, payments.css
      js/                      core.js, facture.js, …, payments.js
      img/                     Icons
```

## Frontend globals & conventions

**`window.state`** — single source of truth:
```javascript
{
  currentPage: 'home',          // 'home', 'facture', 'history', 'scans', 'payments', 'settings'
  editingId: null,              // invoice ID if editing
  filters: {status, client, ...},
  pageParams: {},               // per-page state (paiementId, etc.)
  // … other state per page
}
```

**Script load order** (from `index.html`):
1. `core.js` — API helpers, toast, money formatting, global state
2. `home.js`, `facture.js`, `history.js`, `scans.js`, `payments.js`, `settings.js` — page modules
3. `autocomplete.js` — shared widget

Each script defines functions matching the page name (e.g., `home.js` has `render()`, `init()`).

---

**Next:** See `DISCOUNTS.md` for discount math details, `PAYMENTS.md` for payment import logic.

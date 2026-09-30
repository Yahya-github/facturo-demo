# Testing

Every name, plate, address and amount in the test suite is fictional. The
company the app invoices for is `Demo Transport Inc.` (`facturo/brand.py`,
overridable with `FACTURO_COMPANY_NAME`).

## Running the suites

```bash
python -m pytest                                   # unit + integration + e2e (Playwright)
# On a machine with the pytest-django plugin installed, add `-p no:django`,
# or the live-server e2e tests are skipped silently.
python -m pytest --ignore=tests/e2e                # without a browser
python -m pytest --cov=facturo --cov-report=term   # with coverage
node --test tests/js/*.mjs                         # JS/Python parity checks
ruff check .                                       # lint
```

The e2e suite needs `playwright install chromium` once.

## What is covered

| Area | Tests | Notes |
|------|-------|-------|
| Discount math | `test_discounts.py`, `test_discount_api.py`, `tests/js/discounts.test.mjs` | Python and JS run the same `tests/fixtures/discount_cases.json`, so the two implementations cannot drift apart |
| v1 to v2 discount migration | `test_discount_migration.py` | A frozen copy of the v1 math acts as the oracle. Migrated totals must match it to the cent, and running the migration twice changes nothing |
| Invoice list and filters | `test_invoice_list.py`, `tests/e2e/test_filters.py` | Totals, payment status, and search that ignores accents |
| Payments | `test_payment_parser.py`, `test_payment_matcher.py`, `test_payment_api.py`, `test_payment_api_errors.py`, `test_payment_relink.py`, `tests/e2e/test_payments.py` | Parser tests use synthetic text fixtures in `tests/fixtures/payments/text/`: a quittance plus two supplier-bill layouts |
| Billet normalisation and AI snapping | `test_billet_fields.py`, `test_known_values.py`, `test_ai_extract.py`, `test_scan_api.py` | Dates, plates, hours notation, and edit-distance snapping against a curated vocabulary. No GPU or Ollama needed |
| Sync | `test_sync_hardening.py`, `test_migration_safety.py` | URL allow-list, backups before reset, schema guard |
| Updates and releases | `test_updater.py`, `test_updater_hardening.py`, `test_updates_api.py`, `test_release_tooling.py`, `test_smoke_flag.py`, `tests/e2e/test_updates_ui.py` | SHA-256 verification, redirect handling that drops the auth header, swap and rollback script, `release.sh` |
| Local API guard | `test_local_guard.py` | Rejects a non-loopback `Host` and cross-site writes |
| Write safety | `test_invoice_write_safety.py` | Unreadable billets are never silently overwritten |

## Figures (Linux, Python 3.12+)

- 778 pytest tests collected. 764 pass, and 14 are skipped when optional real
  sample PDFs are missing (they are gitignored) or the machine isn't Windows
  (DPAPI). About 120 of them are Playwright e2e tests (`tests/e2e/`), which
  cover the interface: accessibility, overflow at 390/768 px, offline
  loading, command palette, dialogs and toasts, and every page in both
  languages. The shared `page` fixture starts in French and `page_en` in
  English (the default); see [I18N.md](I18N.md).
- `test_release_tooling.py` (9 tests) clones the working tree with git, so
  it needs the project to be a git checkout.
- Backend line coverage is about 79% overall (Python only; the JavaScript UI
  is covered by the e2e and node tests). `discounts.py` 99%, `matcher.py` 100%,
  `pdf_text.py` 100%, `store.py` 99%, `parser.py` 96%, `updater.py` 95%,
  `known_values.py` 93%, `billet_fields.py` 92%, `excel_generator.py` 82%,
  `services/sync.py` 57% (its network paths are mocked).
- JS: 9 node test files (71 tests: discount and money parity, chart data,
  fuzzy matcher, floating placement, utilities, the language engine and the
  English/French key parity of every locale file), all passing.

## Billet extraction bench (manual)

`tests/billets/bench.py` runs the AI extraction against hand-checked ground
truth (`ground_truth.json`, `ground_truth_vrac.json`) and scores each field.
It needs a running Ollama server and the billet page images, which aren't
shipped. It's a tuning tool and isn't part of CI.

## Optional parity check against a real legacy database

Set `FACTURO_LEGACY_DB=/path/to/copy-of-v1.db` to run the whole-database
migration parity tests against your own data. The file is copied first and
never modified. Without it, those tests use a synthetic v1 database.

## CI

`.github/workflows/ci.yml` runs `ruff check .` and the full pytest suite,
Playwright included, on every push and pull request. `release.yml` builds the
Windows exe, runs a smoke test and a swap/rollback check, and publishes the
release.

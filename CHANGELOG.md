# Changelog

Format: one `## [X.Y.Z] - YYYY-MM-DD` section per release. Add notes under
`## [Unreleased]`. `scripts/release.sh` moves them into a dated release section,
and that section becomes the GitHub Release description shown in the app.

This public snapshot has no earlier release history. The section below lists
what the snapshot contains.

## [Unreleased]

### Added
- `facturo/` package layout. Runtime data (database, invoices, scans, payments) lives outside the source tree.
- Invoices built from billets (hours × rate), exported to Excel and PDF, with an option to split by worksite.
- Dual discounts: a percentage and/or a fixed amount, per billet and per invoice, before TPS/TVQ. Includes a migration from the v1 single-discount model, checked against a frozen oracle.
- Invoice history with filters (client, payment status, dates), accent-insensitive search and sorting.
- Paiements tab: import proof-of-payment PDFs (pypdfium2 text layer) and parse headers, totals and billet rows.
  - Matching by billet number, with date + plate + quantity as the fallback.
  - Duplicate detection. An invoice is marked paid automatically once all its billets are covered.
  - Manual linking and unlinking, and two-way links between payments and invoices.
  - Bills addressed to the company itself are refused, since they aren't proofs of payment.
- AI billet extraction through Ollama (local or cloud) for photos, HEIC and scanned PDFs, with deterministic post-processing of dates, plates, hours and billet numbers.
- Curated known values (worksites, plates) used for autocomplete and for snapping AI reads. Values can be renamed, hidden and merged.
- Company name configurable through `facturo/brand.py` / `FACTURO_COMPANY_NAME`. The default is `Demo Transport Inc.`
- Multi-device sync through a private GitHub data repo (dulwich). It backs up before every reset, checks the URL against an allow-list, and refuses to sync with a database from a newer app version.
- In-app updates from GitHub Releases, verified by SHA-256, with an exe swap, a health check and automatic rollback.
- Release tooling: `scripts/release.sh` (semver check, tests, lint, migration dry run, version bump, CHANGELOG roll, tag), plus CI and release workflows on GitHub Actions.
- Security: listens on loopback only, a local guard middleware rejects foreign `Host` headers and cross-site writes, and tokens are encrypted at rest on Windows (DPAPI) or stored with 0600 permissions elsewhere.
- Tests: pytest unit/API suites, Playwright e2e, node parity tests for the shared discount math.

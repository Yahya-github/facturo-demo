# Releases and in-app updates

A version is released by tagging it with `scripts/release.sh`. The `v*` tag runs
`.github/workflows/release.yml`, which publishes `Factures.exe` to the private repo
`your-github-user/facturo-releases`. The client's app downloads it from there
(`facturo/services/updater.py`).

The release repo holds only exes, checksums and notes, so the client's read-only
token can never read the source repo.

> **Status — not yet proven on Windows.** As of this writing no `v*` tag exists
> and `release.yml` is not on GitHub yet (only `main` is pushed), so it has
> never run. The update helper swap/rollback
> (`update_helper.cmd`, exercised only by the `swap-rollback` CI job) and DPAPI
> token encryption (only a Windows-only test in the `unit-tests` job) have never
> been executed on Windows. Treat the first rc as the proof.

## Versions

`facturo/version.py` holds the **last released** version (`1.0.0` today; v1 was
never versioned). Only `release.sh` changes it. Format `X.Y.Z` or `X.Y.Z-rcN`
(leading `v` tolerated when comparing). Order: `2.0.0-rc1 < 2.0.0-rc2 < 2.0.0 <
2.0.1`; rc numbers compare numerically (`rc9 < rc10`).

First v2 release: `scripts/release.sh 2.0.0-rc1`, test, then `scripts/release.sh 2.0.0`.

## `scripts/release.sh X.Y.Z[-rcN] [--push]`

Run from a clean checkout of the branch to release. In order:
1. working tree clean (else stops);
2. version matches `X.Y.Z` or `X.Y.Z-rcN`;
3. version strictly greater than `facturo/version.py`;
4. `CHANGELOG.md` has a non-empty `## [Unreleased]` section;
5. `python -m pytest -q` (whole suite, e2e included — needs Playwright's chromium)
   and `ruff check .`;
6. migration dry run `python -m facturo.tools.migrate_check data/data.db`, skipped
   when that file does not exist;
7. writes the version into `facturo/version.py`;
8. moves the `[Unreleased]` notes under `## [X.Y.Z] - YYYY-MM-DD` (an empty
   `[Unreleased]` heading stays on top);
9. commits `chore: release vX.Y.Z` and creates annotated tag `vX.Y.Z`;
10. with `--push`: `git push origin HEAD vX.Y.Z`; otherwise prints that command.

A failure in steps 1–6 leaves nothing changed. Environment: `PYTHON` (interpreter
with `requirements-dev.txt`, default `python3`), `DATA_DB` (database for step 6).
`FACTURO_RELEASE_SELFTEST=1` skips step 5's tests and is reserved for
`tests/test_release_tooling.py` — never set it for a real release.

## CI

**`ci.yml`** — every push and pull request, job `test` on ubuntu, Python 3.12:
install `requirements-dev.txt`, `playwright install --with-deps chromium`,
`ruff check .`, `pytest`.

**`release.yml`** — on tags `v*`, four jobs:

| Job | Runner | Needs | Does |
|-----|--------|-------|------|
| `unit-tests` | windows-latest | — | `pytest --ignore=tests/e2e` (no ruff here) |
| `build` | windows-latest | unit-tests | tag must equal `v` + `facturo/version.py`; `pyinstaller packaging/Factures.spec`; `dist\Factures.exe --smoke-test`; writes `Factures.exe.sha256`; uploads both as artifact `factures-exe` |
| `swap-rollback` | windows-latest | unit-tests | builds 0.0.1, a healthy 0.0.2 and a broken 0.0.3 (`FACTURO_BUILD_BROKEN=1`); checks the broken one fails `--smoke-test`; runs `packaging/ci_swap_rollback.py` (real helper: update N→N+1, then failed update → rollback, data.db unchanged) |
| `release` | ubuntu-latest | build, swap-rollback | `sha256sum --check`; notes = the version's CHANGELOG section (`packaging/release_notes.py`, fails if empty); `gh release create vX.Y.Z Factures.exe Factures.exe.sha256` in `your-github-user/facturo-releases` with secret `RELEASES_TOKEN`; `-rc` tags are marked prerelease |

`RELEASES_TOKEN` must be a repo secret of the Facturo repo: fine-grained PAT,
only `facturo-releases`, Contents: Read and write. `facturo-releases` needs one
initial commit so `gh` can create tags there. Setup clicks: `docs/SETUP.md` §2.

## In-app update (client)

Paramètres → **Mises à jour** card:
- **Jeton GitHub (lecture seule)** + **Enregistrer le jeton**: the token is first
  checked against GitHub, then saved. If no update token is saved, the sync token
  is tried instead (it normally lacks access to `facturo-releases` → "Dépôt
  introuvable ou jeton sans accès.").
- **Inclure les versions de test**: also offer `-rc` prereleases. Leave off on
  work PCs.
- **Vérifier** (`GET /api/updates/check`, cached 1 h). The frozen app also checks
  once per browser session in the background when a token is configured; a dot
  on "Paramètres" signals an update.
- **Installer** → **Confirmer l'installation** (`POST /api/updates/install`).
  Only in `Factures.exe`: in dev mode the button is disabled.

`install()` then:
1. refuses if: dev mode; the exe folder is not writable ("Déplacez le dossier
   hors de « Program Files »"); the exe is not named `Factures.exe`; a sync is
   running; no newer release; the release lacks the exe;
2. checkpoints and copies `data.db` to `backups/data.db.<YYYYmmdd-HHMMSS>.pre-update.bak`;
3. downloads `Factures.exe` next to the running exe (HTTPS only, ≤ 400 MB, token
   sent only to `api.github.com`, never forwarded on redirects), verifies it against
   `Factures.exe.sha256`, and names it `Factures.exe.new`;
4. writes `update_helper.cmd` in the exe folder and starts it detached;
5. the app exits 1.5 s after answering. The page shows "Mise à jour en cours… une
   nouvelle fenêtre va s'ouvrir.", polls `/api/version` and reloads when another
   version answers (after 3 min it adds a "tarde à répondre" hint).

### `update_helper.cmd` (Windows)

1. Waits up to ~60 s for the old process to exit (else `OLD_PROCESS_STILL_RUNNING`,
   nothing changed).
2. Moves `Factures.exe` → `Factures.old.exe` (30 retries; else
   `RENAME_CURRENT_FAILED`, old version restarted).
3. Moves `Factures.exe.new` → `Factures.exe` (30 retries; else
   `ACTIVATE_NEW_FAILED`, old version restored).
4. Starts the new exe with `--port <same port> --no-browser`
   (`PYINSTALLER_RESET_ENVIRONMENT=1`) and records its PID.
5. Health check: up to 30 probes about 1 s apart of
   `http://127.0.0.1:<port>/api/version?expect=<new version>` — 200 only when
   exactly that version runs (409 otherwise).
6. Healthy: deletes `Factures.old.exe`, `Factures.failed.exe`, the PID file and itself.
7. Unhealthy (`HEALTH_CHECK_FAILED`): kills only the PID it started, renames the
   new exe to `Factures.failed.exe`, restores `Factures.old.exe`, writes
   `update_failed.txt` (`ROLLBACK <REASON>`), restarts the old version on the same port.

Log: `update_helper.log` in the exe folder.

### At the next start (frozen app)

- If `update_failed.txt` exists: it is read and deleted, leftovers are removed at
  once, and a French message ("La mise à jour a échoué : …") is returned once by
  `GET /api/updates/status`, shown as a toast and in the Mises à jour card.
- Otherwise, 120 s after start: removes `Factures.exe.new`, `Factures.failed.exe`,
  `Factures.old.exe`, `update_helper.cmd`, `update_new_pid.txt` and partial downloads.

## Token storage (`update_config.json`, next to the exe, never synced)

- Windows: saved as `token_dpapi` (DPAPI, bound to the Windows user, fixed
  entropy); a plaintext `token` found on disk is re-saved encrypted. A file copied
  to another user/PC is unreadable → the token must be pasted again.
- Other OSes: plaintext `token`, file mode 0600.
- Also stored: `include_prereleases`.
- The token is never logged and never returned by an endpoint.

## Endpoints

`GET /api/version[?expect=X]`, `GET /api/updates/status`, `POST /api/updates/config`
(`token`, `include_prereleases`), `GET /api/updates/check`,
`POST /api/updates/install` (`port`).

## Error messages (from `updater.py`)

| Message | Meaning |
|---------|---------|
| Aucun jeton configuré… | No update token and no sync token |
| Jeton GitHub refusé ou expiré. | 401/403: expired/revoked token |
| Dépôt introuvable ou jeton sans accès. | 404: token not scoped to `facturo-releases` |
| Connexion impossible… | Network |
| Échec de la vérification SHA-256… | Download does not match the published checksum |
| Impossible d'écrire dans le dossier de Factures.exe… | Folder under Program Files or read-only |
| Une synchronisation est en cours… | Wait for Recevoir/Envoyer to finish |
| La mise à jour a échoué : … Retour à la version précédente. | Helper rolled back (reasons above) |

Tests: `tests/test_updater.py`, `test_updater_hardening.py`, `test_updates_api.py`,
`test_release_tooling.py`, `test_smoke_flag.py`, `tests/e2e/test_updates_ui.py`.

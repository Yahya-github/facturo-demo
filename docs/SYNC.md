# Multi-device sync (Recevoir / Envoyer)

Optional. Data moves between PCs through a **private GitHub repo used only for
data** (here called `facturo_data`; any empty private repo works). Code:
`facturo/services/sync.py` (dulwich, so Git need not be installed),
endpoints in `facturo/api/sync.py`.

Model: one device at a time, **no merging** (SQLite is binary).
- **Envoyer** (push): this device's data becomes the version on GitHub.
- **Recevoir** (pull): GitHub's version replaces this device's data.

## Repos

| Repo | Holds | Used by |
|------|-------|---------|
| `Yahya-github/facturo-demo` | Source code | Developer, CI |
| `your-github-user/facturo-releases` | Published `Factures.exe` + `.sha256` + notes | In-app updater (`docs/UPDATES_AND_RELEASES.md`) |
| `facturo_data` | Data only | Sync |

Connecting refuses a repo whose tree contains anything besides `.gitignore`,
`data.db`, `company_logo.png`, `output/`, `scans/`, `paiements/` — e.g. the source
repo — so a Recevoir can never dump code next to the exe.

## What is synced

Synced: `data.db`, `company_logo.png`, `output/` (generated invoices), `scans/`,
`paiements/` (imported payment PDFs). The repo's `.gitignore` ignores everything
else: the exe, `sync_config.json`, `update_config.json`, `ai_config.json`,
`backups/`, `*.bak`, SQLite side files.

Where the sync git repo lives: the exe folder itself (installed app), or
`data/.sync_data/` (dev mode, files are copied in and out of `data/`).

## Configuration

Paramètres → Synchronisation: URL du dépôt GitHub, Jeton d'accès (token),
Branche (default `main`) → **Connecter** (`POST /api/sync/configure`; checks the
URL and token against GitHub and the data-only rule above).

Stored in `sync_config.json` next to the data (gitignored, never synced), keys
`remote_url`, `branch`, `token` (or `token_dpapi` on Windows), `last_synced`, `last_action`.
The token is stored **encrypted with DPAPI on Windows**, or **in plain text with 0600
file permissions** (owner-read-write only) elsewhere. The token is injected into
the remote URL only at call time, never written to `.git/config`.

Token: fine-grained PAT, Repository access → only `facturo_data`,
Contents: Read and write.

"Déconnecter cet appareil" deletes `sync_config.json` only; data is kept.

## Envoyer (`POST /api/sync/push`)

1. **Schema guard:** if `data.db` carries a schema newer than this app
   (`PRAGMA user_version` > `SCHEMA_VERSION`), refuse:
   "Cette base de données a été créée par une version plus récente de Factures.
   Mettez à jour l'application avant d'envoyer."
2. Checkpoint the WAL, commit the data files.
3. Fetch the remote; if it has commits this device does not have, refuse:
   "… un autre appareil a synchronisé). Cliquez « Recevoir » avant d'envoyer."
   Never force-pushes.
4. Push; record `last_synced`.

No backup is made on Envoyer.

## Recevoir (`POST /api/sync/pull`)

1. Fetch; empty remote → "Le dépôt distant est vide. Cliquez « Envoyer » depuis
   l'appareil qui possède déjà les données."
2. Checkpoint, then copy the current database to `data.db.<YYYYmmdd-HHMMSS>.bak`
   **in the data folder** (exe folder, or `data/` in dev). If that copy or the
   removal of the SQLite side files fails, the pull is aborted before anything
   is overwritten.
3. Hard-reset the data files to the remote version.
4. Run the schema migration (`db.init_db()`): an older database is brought up to
   date; a **newer** one is left untouched.

There is **no guard on Recevoir**: pulling a database from a newer app version
succeeds, then the app shows a red banner ("Cette base de données provient d'une
version plus récente — mettez à jour l'application.") and Envoyer is blocked until
the app is updated.

Concurrent operations inside one app are serialized by a lock; the updater
refuses to install while a sync is running.

## Schema changes and rollout

v2 (schema 2) adds `remise_pct`, `remise_montant`, `paye_auto` to `factures`,
the `paiements`, `paiement_lignes` tables, and converts v1
discounts (clearing `remise_type` / `remise_valeur`).

**v1 has no schema guard.** A v1 app that receives a v2 database would open it,
lose the converted discounts (it only reads the legacy fields) and could Envoyer
over it. So: **update every device to v2 before any device syncs again.** Order
in `docs/SETUP.md` §6. The same rule holds for any future schema bump; from v2
on, the guard above at least blocks Envoyer.

The v2 schema is the one that requires every device to update together. Changes
that stay compatible (such as the lookup indexes, created on every start when
missing) do not bump the schema version and need no coordinated rollout.

Tests: `tests/test_sync_hardening.py`.

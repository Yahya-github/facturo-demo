# Setup Guide — Complete step-by-step

This guide covers dev machine setup, GitHub token creation, releasing an update, and client first install.

## 1. Your dev machine

### Clone & create virtual environment

```bash
git clone https://github.com/your-github-user/facturo facturo-dev
cd facturo-dev
python -m venv venv

# On macOS/Linux:
. venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### Install dependencies

```bash
pip install -r requirements-dev.txt
```

### Run the app

```bash
python -m facturo
```

Opens at `http://127.0.0.1:8000`. Data saved to `data/` (gitignored).

### Run tests

```bash
python -m pytest
```

Target: 80%+ coverage. Full output: `python -m pytest --cov`.

### Lint

```bash
ruff check .
```

## 2. GitHub one-time setup

### Create the releases repository (one-time)

1. Go to **https://github.com/new**
2. **Repository name:** `facturo-releases`
3. **Visibility:** Private
4. **Initialize:** Add `README.md`
5. Click **Create repository**

### Create the releases publishing token (one-time)

This token lets CI push new releases to `facturo-releases`.

1. Go to **https://github.com/settings/personal-access-tokens/new** (or GitHub Settings → Developer settings → Personal access tokens → Fine-grained tokens → New token)
2. **Token name:** `facturo-releases-push`
3. **Expiration:** 90 days (set a calendar reminder to refresh before expiration)
4. **Resource owner:** `your-github-user`
5. **Repository access:** Only select repositories → `facturo-releases`
6. **Permissions:**
   - Contents: `Read and write`
7. Click **Generate token**, copy immediately (shown only once)
8. Go to **https://github.com/your-github-user/facturo/settings/secrets/actions** (this repo's Secrets)
9. Click **New repository secret**
   - **Name:** `RELEASES_TOKEN`
   - **Secret:** Paste the token from step 7
10. Click **Add secret**

### Create the client's update token (one-time)

This token lets the client's app check for and download updates from `facturo-releases`.

1. Go to **https://github.com/settings/personal-access-tokens/new**
2. **Token name:** `facturo-client-updater`
3. **Expiration:** 1 year (or less; set reminder 2 months before expiry)
4. **Resource owner:** `your-github-user`
5. **Repository access:** Only select repositories → `facturo-releases`
6. **Permissions:**
   - Contents: `Read-only`
7. Click **Generate token**, copy
8. **Give this token to the client** (they paste it once in their app, Paramètres → Mises à jour)

### Confirm data sync token

The client has a sync token for `facturo_data` (from the original setup). Verify it has:
- **Contents:** Read and write
- **Repository access:** `facturo_data` only
- **Not expired**

If expired, create a new one using the same process as the updater token (steps 1–7 above), but for `facturo_data` with Read+write permission.

### Enable Actions

Go to **https://github.com/your-github-user/facturo/settings/actions** and ensure:
- Actions is enabled
- Workflow permissions: "Read and write permissions" is selected

## 3. Releasing an update

### Edit CHANGELOG

Edit `CHANGELOG.md`:
1. Add your changes under `## [Unreleased]`
2. Format:
   ```markdown
   ## [Unreleased]

   ### Added
   - Payment import & linking (Paiements tab)

   ### Fixed
   - Invoice totals precision issue

   ### Changed
   - Dual discounts (percent + fixed)
   ```

### Run release script

```bash
scripts/release.sh 2.1.0-rc1
```

or with `--push`:

```bash
scripts/release.sh 2.1.0-rc1 --push
```

The script:
1. Validates clean working tree, semver, version bump, CHANGELOG
2. Runs tests & lint
3. Runs migration dry-run (if `data/data.db` exists)
4. Bumps version, rolls CHANGELOG, commits, tags
5. Prints: `Run: git push origin HEAD --tags` (unless `--push` was passed)

### Watch the Actions workflow

Push the tag:

```bash
git push origin HEAD --tags
```

Go to **https://github.com/your-github-user/facturo/actions** and watch the `release` workflow:
1. Windows build
2. Smoke test (exe boots, hits `/api/version`, exits 0)
3. Release published with exe + SHA-256 + notes

### Test the RC

Download `Factures.exe` from the release, test on a scratch folder:

```bash
mkdir ~/test_rc
cd ~/test_rc
# Copy Factures.exe here
./Factures.exe
# In app: Paramètres → Mises à jour → enter update token → Vérifier
# Should see "Mise à jour disponible v2.1.0-rc1"
# Click Installer → update works → app restarts at new version
# Verify key features (Factures, Paiements, Recevoir/Envoyer)
```

If RC is solid:

```bash
scripts/release.sh 2.1.0
scripts/release.sh 2.1.0 --push
```

If RC has issues, fix them, then:

```bash
scripts/release.sh 2.1.0-rc2
```

### If the workflow fails

1. Check the GitHub Actions log for errors
2. Fix the issue (e.g., test failure, build error)
3. Create a new commit and push again
4. Do **not** re-use the same tag — delete it and create a new `-rc` or `-rc+1`

## 4. Client first install (bootstrap v2)

**One-time setup for each device.** The client's current exe has no updater, so you must copy v2 once by hand.

1. Go to the client's releases: **https://github.com/your-github-user/facturo-releases/releases**
2. Download the latest `Factures.exe` (v2.0.0 or later, not an RC)
3. Create a folder (e.g., `C:\Factures\`) — **Not under Program Files** (no admin needed)
4. Copy `Factures.exe` and `LibreOfficePortable/` folder into it
5. Run `Factures.exe`
6. Go to Paramètres (Settings):
   - **Sync token:** Paste the client's sync token for `facturo_data`
   - **Update token:** Paste the client's updater token for `facturo-releases`
   - **Inclure les versions de test:** Unchecked (unless you're testing RCs)
7. Click "Recevoir" to pull the existing data

From this point on, updates are one-click (Mises à jour → Installer button).

## 5. Client day-to-day

### Create invoices

1. Home page: Click "Nouvelle facture"
2. Select client, add billets (hourly rows)
3. Review taxes & discounts
4. Save & Export to Excel

### Import payments

1. Paiements tab: Drag-drop or pick PDF files
2. App auto-parses & matches billets
3. Review matches (statut: lié / à vérifier / doublon)
4. Manually link unmatched lines if needed
5. Invoices with 100% coverage marked "Payé" automatically

### Sync data

1. Paramètres → "Recevoir" (pull from other devices)
2. Paramètres → "Envoyer" (push changes)

Before `Envoyer`, a backup of `data.db` is created in `backups/`.

### Check for updates

1. Paramètres → Mises à jour
2. Click "Vérifier"
3. If "Mise à jour disponible" appears, click "Installer"
4. App updates with automatic rollback on failure

## 6. Multi-device rollout

### Schema migrations: update every device together

**Rule for the v2 schema (and any future schema bump):** All devices must be updated to v2 before any device syncs again.

**WHY:** Old versions don't understand new schemas. If Device A (old version) pulls a database created by Device B (new version), Device A is blocked ("Mettez à jour l'application"). The only safe sequence is: update all devices first, then sync.

### Rollout process

When rolling out v2 to multiple devices:

**DO THIS FIRST:**
1. Update **all devices** to v2.0.0 via bootstrap copy from dev machine (as in step 4 above)
2. Only then can any device `Recevoir` or `Envoyer`

**Example: Rolling out v2 to three devices**

1. Device 1: Update to v2.0.0, test thoroughly
2. Device 1: `Envoyer` (push the migrated database to GitHub)
3. Device 2 and Device 3: Update to v2.0.0
4. Device 2 and Device 3: `Recevoir` to pull Device 1's data

## 7. Troubleshooting

### Setup & development

| Problem | Solution |
|---------|----------|
| `ImportError: No module named facturo` | Run `pip install -r requirements-dev.txt` in your venv |
| `python -m facturo` fails with database error | Delete `data/data.db` and restart; it will re-initialize |
| Tests fail after code changes | Run `python -m pytest --cache-clear` to clear cached data |
| Port 8000 already in use | App tries the next available port; check with `netstat -an` or `lsof -i :8000` |

### GitHub token issues

| Problem | Solution |
|---------|----------|
| "Aucun jeton configuré" when testing updates | Create the update token in GitHub Settings (§2, step 1–7) and enter it in `Paramètres → Mises à jour` |
| "Jeton refusé" (401/403) | Token expired: create a new one. Check that token has `Contents: Read-only` scope on correct repo. |
| "Dépôt introuvable" (404) | Verify token covers the correct repo (`facturo-releases` for updates, `facturo_data` for sync). Check repo exists and is private. |

### Release & sync

| Problem | Solution |
|---------|----------|
| `scripts/release.sh` fails with "des modifications non commitées" | Run `git status` and commit or stash all changes before releasing |
| "CHANGELOG.md n'a pas de section [Unreleased]" | Edit `CHANGELOG.md`, add `## [Unreleased]` header and at least one bullet point describing changes |
| `Recevoir` blocked with "Mettez à jour l'application" | Device's data.db was created by a newer app version. Update the app first, then sync. |
| `Envoyer` fails with "Une synchronisation est en cours" | Another device is currently syncing. Wait and retry in a few seconds. |

### Client deployment

| Problem | Solution |
|---------|----------|
| Client sees "Mode développement" (no Install button) | Client is running dev version. Copy the `Factures.exe` from a release (§4, step 2) to the client machine. |
| Update fails with "Mise à jour échouée" banner | Check disk space, antivirus locks, folder permissions. Retry. See `UPDATES_AND_RELEASES.md` for detailed troubleshooting. |
| Client can't sync after v2 update | Confirm sync token is set (`Paramètres → Recevoir`). If first sync, Device 1 must push first; other devices pull after. |

For detailed update and sync troubleshooting, see `UPDATES_AND_RELEASES.md`. For client usage questions, see `CLIENT_GUIDE_FR.md`.

---

**Support:** Check `docs/UPDATES_AND_RELEASES.md` troubleshooting table for common errors. Check `docs/CLIENT_GUIDE_FR.md` for French user guide.

# Factures v2 — Installation Windows

Goal: the client double-clicks one thing and **everything works** — invoices, payments, sync, updates — on a brand-new Windows PC with nothing installed (no Python, no LibreOffice).

There are two parts: **you** build + package the app once; the **client** just copies a folder and double-clicks. After first install, in-app updates handle all future versions (no manual exe copies).

---

## Part A — You: build the full package (once, on a Windows PC)

You need a Windows machine with **Python 3.12+** installed
(from [python.org](https://www.python.org/downloads/) — **tick "Add Python to
PATH"** during install).

### Step 1 — Build the exe

1. Clone the repo on Windows
2. Create and activate a venv:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements-dev.txt
   ```
3. From the repo root, run:
   ```bash
   python packaging/build.py
   ```
   or double-click **`packaging\build.bat`**
4. Wait ~2–3 min. You get `dist\Factures.exe`

### Step 2 — Add LibreOffice Portable (for PDF export)

Excel export works everywhere. PDF export (optional) needs LibreOffice.

1. Download **"LibreOffice Portable"** from
   [portableapps.com/apps/office/libreoffice_portable](https://portableapps.com/apps/office/libreoffice_portable)
2. Extract to the repo root:
   ```
   LibreOfficePortable\App\libreoffice\program\soffice.exe
   ```
   (Do this once; reuse for all future builds)

### Step 3 — Package

From the repo root:
```bash
python packaging/package.py
```
or double-click **`packaging\package.bat`**

Output:
```
dist\Factures\
├── Factures.exe
└── LibreOfficePortable\        (~400 MB, bundled)
```

The `dist\Factures\` folder is complete. The client just copies it.

> Rebuild when code changes: re-run build then package.
> LibreOffice (step 2) only needs doing once.

---

## Part B — Developer: prepare for release

1. Edit `CHANGELOG.md` under `## [Unreleased]`
2. Run:
   ```bash
   scripts/release.sh 2.0.1-rc1
   git push origin HEAD --tags
   ```
3. Watch GitHub Actions build and publish to `facturo-releases`
4. Test locally before tagging the final release

See `docs/SETUP.md` for detailed steps.

---

## Part C — Client: install & run

### First install (one-time manual copy)

1. Go to **https://github.com/your-github-user/facturo-releases/releases**
2. Download latest `Factures.exe` (v2.0.0+)
3. Copy the `Factures\` folder (with `Factures.exe` + `LibreOfficePortable\`) to a normal location
   - **Not under Program Files** (needs write access)
   - e.g., `C:\Factures\`
4. Double-click `Factures.exe`
5. Go to **Paramètres:**
   - Paste sync token (Recevoir/Envoyer)
   - Paste update token (Mises à jour)
6. Click **Recevoir** to pull existing data

### Data folder

```
C:\Factures\
├── Factures.exe
├── LibreOfficePortable\        (do not delete; PDF needs it)
├── data.db                     (invoice & client database — back this up!)
├── backups\                    (pre-sync/update backups)
├── output\                     (generated Excel files)
├── scans\                      (uploaded receipt PDFs)
├── paiements\                  (imported payment PDFs)
├── company_logo.png            (if set in Paramètres)
├── sync_config.json            (sync token, per-device, gitignored)
└── update_config.json          (update token, per-device, gitignored)
```

**Back up regularly:** Copy `data.db`, `company_logo.png`, `output/`, `scans/`, `paiements/`.

### Updates (automatic!)

1. Go to **Paramètres → Mises à jour**
2. Click **Vérifier**
3. If "Mise à jour disponible" → click **Installer**
4. App shuts down, updates, restarts — **all automatic**
5. On failure: auto-rollback to previous version

No manual exe copying. Just one click.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Windows protected your PC" (SmartScreen) | Click **More info → Run anyway** (unsigned exe) |
| Browser doesn't open automatically | Check the black console window for the actual port (may not be 5000), then open manually |
| PDF button grayed out or says "LibreOffice" missing | Keep `LibreOfficePortable\` folder next to `Factures.exe` |
| Antivirus blocks the exe | False positive (unsigned PyInstaller exes are common). Add an exception in your antivirus. |
| "Mise à jour échouée" banner | App rolled back automatically. Check disk space, close other programs, retry. |
| "Jeton refusé" on sync/update | Token expired. Create a new one in GitHub Settings, paste in Paramètres. |

---

See `docs/SETUP.md` for full developer workflow and `docs/CLIENT_GUIDE_FR.md` for the French user guide.

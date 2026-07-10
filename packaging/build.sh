#!/usr/bin/env bash
# ============================================================
#  Build the Factures binary (run this once, on a Linux machine)
#  Produces: dist/Factures  -- a single file you can copy
#  to the client's PC.
#
#  Dev-mode sync is isolated in data/.sync_data/; the built binary
#  syncs from its own folder.
# ============================================================
set -e
cd "$(dirname "$0")/.."

# PyInstaller needs a Python built with --enable-shared (libpythonX.Y.so). The
# bare `python3` on PATH sometimes resolves to a statically-linked build (e.g.
# /usr/local/bin/python3) that PyInstaller rejects, even when a perfectly good
# shared build is available elsewhere on the system — so probe a few
# candidates instead of trusting PATH order blindly.
find_python() {
    for candidate in /usr/bin/python3 python3 python; do
        if command -v "$candidate" &>/dev/null && \
           "$candidate" -c "import sysconfig, sys; sys.exit(0 if sysconfig.get_config_var('Py_ENABLE_SHARED') else 1)" 2>/dev/null; then
            echo "$candidate"
            return
        fi
    done
    echo "ERREUR: Aucun Python avec bibliotheque partagee (--enable-shared) trouve, requis par PyInstaller" >&2
    exit 1
}

PYTHON=$(find_python)

echo "[1/3] Création de l'environnement de build..."
"$PYTHON" -m venv build_venv

echo "[2/3] Installation des dépendances + PyInstaller..."
./build_venv/bin/python -m pip install --upgrade pip >/dev/null
./build_venv/bin/pip install -r requirements-build.txt

echo "[3/3] Construction de l'exécutable..."
./build_venv/bin/pyinstaller --noconfirm --clean packaging/Factures.spec

echo
echo "============================================================"
echo " TERMINÉ. Votre application : dist/Factures"
echo " Copiez ce fichier sur le PC du client."
echo "============================================================"

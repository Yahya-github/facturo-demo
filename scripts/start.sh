#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

# Find a Python with sqlite3 support
find_python() {
    for candidate in /usr/bin/python3 python3 python; do
        if command -v "$candidate" &>/dev/null && "$candidate" -c "import sqlite3" 2>/dev/null; then
            echo "$candidate"
            return
        fi
    done
    echo "ERREUR: Aucun Python avec sqlite3 trouvé" >&2
    exit 1
}

PYTHON=$(find_python)

if [ ! -d "venv" ]; then
    echo "Installation en cours..."
    "$PYTHON" -m venv venv
    ./venv/bin/python -m pip install -q -r requirements.txt
fi

echo "Démarrage du serveur... (le navigateur s'ouvre automatiquement)"
echo "Pour arrêter : Ctrl+C ici, ou exécutez scripts/stop.sh depuis un autre terminal."

echo $$ > .server.pid
trap 'rm -f .server.pid' EXIT

exec ./venv/bin/python -m facturo

#!/usr/bin/env bash
cd "$(dirname "$0")/.."

if [ ! -f .server.pid ]; then
    echo "Aucun serveur en cours (fichier .server.pid introuvable)."
    exit 0
fi

PID=$(cat .server.pid)

if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "Serveur arrêté (PID $PID)."
else
    echo "Le serveur n'était déjà plus en cours d'exécution."
fi

rm -f .server.pid

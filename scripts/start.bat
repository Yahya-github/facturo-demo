@echo off
cd /d "%~dp0.."

if not exist "venv" (
    echo Installation en cours...
    python -m venv venv
    venv\Scripts\python -m pip install -q -r requirements.txt
)

echo Demarrage du serveur... (le navigateur s'ouvre automatiquement)
venv\Scripts\python -m facturo

@echo off
REM ============================================================
REM  Build Factures.exe  (run this once, on a Windows machine)
REM  Produces: dist\Factures.exe  -- a single file you can copy
REM  to the client's PC.
REM ============================================================
cd /d "%~dp0.."

echo [1/3] Creation de l'environnement de build...
python -m venv build_venv || goto :error

echo [2/3] Installation des dependances + PyInstaller...
build_venv\Scripts\python -m pip install --upgrade pip >nul
build_venv\Scripts\pip install -r requirements-build.txt || goto :error

echo [3/3] Construction de l'executable...
build_venv\Scripts\pyinstaller --noconfirm --clean packaging\Factures.spec || goto :error

echo.
echo ============================================================
echo  TERMINE. Votre application : dist\Factures.exe
echo  Copiez ce fichier sur le PC du client.
echo ============================================================
pause
exit /b 0

:error
echo.
echo ERREUR pendant la construction. Verifiez que Python est installe
echo (coche "Add Python to PATH") puis relancez build.bat.
pause
exit /b 1

@echo off
REM ============================================================
REM  Package the FULL distributable: Factures.exe + LibreOffice
REM  portable, so PDF export works on a brand-new Windows PC
REM  with NOTHING installed.
REM
REM  Prerequisites (do these once):
REM    1) Run build.bat            -> creates dist\Factures.exe
REM    2) Download "LibreOffice Portable" from portableapps.com
REM       and install/extract it into:  vendor\LibreOfficePortable
REM       (so vendor\LibreOfficePortable\App\libreoffice\program\
REM        soffice.exe exists)
REM
REM  Output: dist\Factures\  (copy this WHOLE folder to the client)
REM ============================================================
cd /d "%~dp0.."

if not exist "dist\Factures.exe" (
    echo ERREUR: dist\Factures.exe introuvable.
    echo Lancez d'abord build.bat
    pause
    exit /b 1
)

set "SOFFICE=vendor\LibreOfficePortable\App\libreoffice\program\soffice.exe"
if not exist "%SOFFICE%" (
    echo ERREUR: LibreOffice portable introuvable dans vendor\LibreOfficePortable
    echo.
    echo  1. Telechargez "LibreOffice Portable" sur portableapps.com
    echo  2. Installez/extrayez-le dans:  vendor\LibreOfficePortable
    echo     ^(le fichier %SOFFICE% doit exister^)
    echo  3. Relancez package.bat
    pause
    exit /b 1
)

set "OUT=dist\Factures"
echo [1/3] Nettoyage de %OUT% ...
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%"

echo [2/3] Copie de Factures.exe ...
copy /y "dist\Factures.exe" "%OUT%\Factures.exe" >nul

echo [3/3] Copie de LibreOffice portable (~400 Mo, patientez)...
xcopy /e /i /q /y "vendor\LibreOfficePortable" "%OUT%\LibreOfficePortable" >nul

echo.
echo ============================================================
echo  TERMINE. Distribuable complet : %OUT%\
echo  Copiez TOUT le dossier "%OUT%" sur le PC du client.
echo  L'export Excel ET PDF fonctionnent sans aucune installation.
echo ============================================================
pause
exit /b 0

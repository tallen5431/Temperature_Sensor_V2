@echo off
REM Build a standalone Temperature Hub executable (Windows).
REM Result: dist\temperature-hub.exe
setlocal
set "HERE=%~dp0"
cd /d "%HERE%.."

set "PY=python"
echo [build] Using:
%PY% --version
%PY% -m pip install --upgrade pip -q
%PY% -m pip install -r requirements.txt pyinstaller -q

echo [build] Refreshing THIRD-PARTY-LICENSES.md from the installed versions...
%PY% packaging\gen_third_party_licenses.py

echo [build] Running PyInstaller (onedir)...
%PY% -m PyInstaller --clean --noconfirm packaging\temperature_hub.spec
if errorlevel 1 (
    echo [build] FAILED
    exit /b 1
)

REM Surface the licences at the top of the distribution folder for visibility.
copy /Y LICENSE dist\temperature-hub\LICENSE >nul
copy /Y THIRD-PARTY-LICENSES.md dist\temperature-hub\THIRD-PARTY-LICENSES.md >nul

echo.
echo [build] Done -^> dist\temperature-hub\
echo [build] Run dist\temperature-hub\temperature-hub.exe, then open http://localhost:8088

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

echo [build] Running PyInstaller...
%PY% -m PyInstaller --clean --noconfirm packaging\temperature_hub.spec
if errorlevel 1 (
    echo [build] FAILED
    exit /b 1
)

echo.
echo [build] Done -^> dist\temperature-hub.exe
echo [build] Run it, then open http://localhost:8088

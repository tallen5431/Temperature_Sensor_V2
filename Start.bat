@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Temperature Sensor Hub
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

echo.

:: ── 1. Locate Python 3.9+ ─────────────────────────────────────────────────
set "PYTHON_BIN="

:: Try the Windows Python Launcher first (most reliable on Windows)
where py >nul 2>&1
if %errorlevel% == 0 (
    for /f "delims=" %%v in ('py -c "import sys; print(sys.version_info >= (3,9))" 2^>nul') do set "VER_OK=%%v"
    if "!VER_OK!" == "True" set "PYTHON_BIN=py"
)

:: Fall back to python3 then python
if "!PYTHON_BIN!" == "" (
    where python3 >nul 2>&1
    if %errorlevel% == 0 (
        for /f "delims=" %%v in ('python3 -c "import sys; print(sys.version_info >= (3,9))" 2^>nul') do set "VER_OK=%%v"
        if "!VER_OK!" == "True" set "PYTHON_BIN=python3"
    )
)

if "!PYTHON_BIN!" == "" (
    where python >nul 2>&1
    if %errorlevel% == 0 (
        for /f "delims=" %%v in ('python -c "import sys; print(sys.version_info >= (3,9))" 2^>nul') do set "VER_OK=%%v"
        if "!VER_OK!" == "True" set "PYTHON_BIN=python"
    )
)

if "!PYTHON_BIN!" == "" (
    echo ╔══════════════════════════════════════════════════════════╗
    echo ║  Python 3.9 or newer is required but was not found.     ║
    echo ║                                                          ║
    echo ║  Download it from: https://python.org/downloads         ║
    echo ║  Make sure to tick "Add Python to PATH" during setup.   ║
    echo ╚══════════════════════════════════════════════════════════╝
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%v in ('!PYTHON_BIN! -c "import sys; print(\"%%d.%%d\" %% sys.version_info[:2])"') do set "PY_VER=%%v"
echo [INFO] Using Python %PY_VER% (!PYTHON_BIN!)

:: ── 2. Create / reuse virtual environment ──────────────────────────────────
set "VENV_DIR=%APP_DIR%\.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [SETUP] Creating virtual environment...
    !PYTHON_BIN! -m venv "%VENV_DIR%"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment. Please check your Python installation.
        pause
        exit /b 1
    )
)

echo [SETUP] Installing / verifying dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel -q
if exist "%APP_DIR%requirements.txt" "%PYTHON_EXE%" -m pip install -r "%APP_DIR%requirements.txt" -q

:: ── 3. Resolve host / port ─────────────────────────────────────────────────
if "%HOST%" == "" set "HOST=0.0.0.0"
if "%PORT%" == "" set "PORT=8088"

:: ── 4. Open browser once server is ready ───────────────────────────────────
:: Launch a detached helper that polls until the port is open, then opens the browser.
start "" /b cmd /c ^
    "for /l %%i in (1,1,30) do (timeout /t 1 /nobreak >nul & ^
      "%PYTHON_EXE%" -c "import socket,sys;s=socket.socket();s.settimeout(1);r=s.connect_ex(('127.0.0.1',%PORT%));s.close();sys.exit(r)" ^
      2>nul && start \"\" \"http://localhost:%PORT%\" && exit)" ^
    2>nul

:: ── 5. Start the hub ───────────────────────────────────────────────────────
echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║  Temperature Hub is starting...                         ║
echo ║  Open http://localhost:%PORT% in your browser.         ║
echo ║  Close this window or press Ctrl+C to stop.            ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

"%PYTHON_EXE%" "%APP_DIR%app.py"
pause

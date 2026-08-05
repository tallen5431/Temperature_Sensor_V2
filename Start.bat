@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Setpoint Hub
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

echo.

REM  Deliberately plain ASCII throughout. A .bat is read by the console host in
REM  whatever code page the machine happens to be on (437 or 1252 on a default
REM  Windows install), so the box-drawing characters this file used to print
REM  came out as mojibake -- the first thing a customer ever saw from Setpoint.
REM  "chcp 65001" would fix the rendering but changes the code page of the
REM  window it inherits; staying inside ASCII needs no such trade.

REM  ---- 1. Locate Python 3.9+ ------------------------------------------------
REM  Every errorlevel test below uses "if errorlevel N" or !errorlevel!, never
REM  %errorlevel%. Inside a parenthesised block cmd substitutes %errorlevel% when
REM  it PARSES the block, so it reads the value from before the block ran. That
REM  is why this used to give up on any machine without the "py" launcher (a
REM  Microsoft Store or Anaconda install): the python3 and python fallbacks were
REM  testing the exit code of the "py" probe that had already failed, so they
REM  never ran and the script reported "Python not found" with Python installed.
set "PYTHON_BIN="

REM  The Windows Python Launcher first -- most reliable when it is present.
where py >nul 2>&1
if not errorlevel 1 (
    set "VER_OK="
    for /f "delims=" %%v in ('py -c "import sys; print(sys.version_info >= (3,9))" 2^>nul') do set "VER_OK=%%v"
    if "!VER_OK!" == "True" set "PYTHON_BIN=py"
)

if "!PYTHON_BIN!" == "" (
    where python3 >nul 2>&1
    if not errorlevel 1 (
        set "VER_OK="
        for /f "delims=" %%v in ('python3 -c "import sys; print(sys.version_info >= (3,9))" 2^>nul') do set "VER_OK=%%v"
        if "!VER_OK!" == "True" set "PYTHON_BIN=python3"
    )
)

if "!PYTHON_BIN!" == "" (
    where python >nul 2>&1
    if not errorlevel 1 (
        set "VER_OK="
        for /f "delims=" %%v in ('python -c "import sys; print(sys.version_info >= (3,9))" 2^>nul') do set "VER_OK=%%v"
        if "!VER_OK!" == "True" set "PYTHON_BIN=python"
    )
)

if "!PYTHON_BIN!" == "" (
    echo  ----------------------------------------------------------
    echo   Python 3.9 or newer is required but was not found.
    echo.
    echo   Download it from: https://python.org/downloads
    echo   Tick "Add Python to PATH" during setup.
    echo  ----------------------------------------------------------
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%v in ('!PYTHON_BIN! -c "import sys; print(\"%%d.%%d\" %% sys.version_info[:2])"') do set "PY_VER=%%v"
echo [INFO] Using Python !PY_VER! (!PYTHON_BIN!)

REM  ---- 2. Create / reuse the virtual environment ----------------------------
set "VENV_DIR=%APP_DIR%.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [SETUP] Creating virtual environment...
    !PYTHON_BIN! -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment.
        echo         Check that Python is installed for your user account and
        echo         that this folder is writable, then run Start.bat again.
        pause
        exit /b 1
    )
)

if not exist "%PYTHON_EXE%" (
    echo [ERROR] The virtual environment is incomplete -- "%PYTHON_EXE%" is missing.
    echo         Delete the .venv folder next to this file and run Start.bat again.
    pause
    exit /b 1
)

REM  ---- 3. Dependencies -----------------------------------------------------
REM  Only reinstall when requirements.txt has changed since the last successful
REM  install, so day-to-day launches are fast and work with no internet.
set "REQ_FILE=%APP_DIR%requirements.txt"
set "REQ_LOCK=%VENV_DIR%\requirements.lock"
set "NEED_INSTALL=1"
if exist "%REQ_LOCK%" (
    fc /b "%REQ_FILE%" "%REQ_LOCK%" >nul 2>&1
    if not errorlevel 1 set "NEED_INSTALL=0"
)
if "!NEED_INSTALL!" == "1" (
    if exist "%REQ_FILE%" (
        echo [SETUP] Installing / verifying dependencies...
        "%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel -q
        "%PYTHON_EXE%" -m pip install --no-compile -r "%REQ_FILE%" -q
        if errorlevel 1 (
            echo [WARN] Some dependencies did not install. Starting anyway --
            echo        if the hub fails to open, connect to the internet and
            echo        run Start.bat again.
        ) else (
            copy /y "%REQ_FILE%" "%REQ_LOCK%" >nul
        )
    )
) else (
    echo [INFO] Dependencies up to date - skipping install.
)

REM  ---- 4. Host / port ------------------------------------------------------
if "%HOST%" == "" set "HOST=0.0.0.0"
if "%PORT%" == "" set "PORT=8088"
set "OPEN_BROWSER=1"

REM  ---- 5. Start the hub ----------------------------------------------------
echo.
echo  ----------------------------------------------------------
echo   Setpoint Hub is starting...
echo   Open http://localhost:%PORT% in your browser.
echo   Close this window or press Ctrl+C to stop.
echo  ----------------------------------------------------------
echo.

"%PYTHON_EXE%" "%APP_DIR%app.py"
set "EXIT_CODE=!errorlevel!"
if not "!EXIT_CODE!" == "0" (
    echo.
    echo [ERROR] The hub stopped with exit code !EXIT_CODE!.
    echo         The lines above say why. logs\hub.log has the full record.
)
echo.
pause
exit /b !EXIT_CODE!

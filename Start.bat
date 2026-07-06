@echo off
setlocal EnableExtensions
title ThermaHub - Temperature Monitoring Hub
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

set "VENV_DIR=%APP_DIR%.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

rem First-run setup only: create the venv and install dependencies ONCE.
if not exist "%PYTHON_EXE%" (
    echo [SETUP] First run: creating environment and installing dependencies...
    py -m venv "%VENV_DIR%"
    "%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel >nul
    if exist "%APP_DIR%requirements.txt" "%PYTHON_EXE%" -m pip install -r "%APP_DIR%requirements.txt"
)

if "%HOST%"=="" set "HOST=0.0.0.0"
if "%PORT%"=="" set "PORT=8080"

echo [RUN] Starting ThermaHub at http://localhost:%PORT%
start "" "http://localhost:%PORT%"
"%PYTHON_EXE%" "%APP_DIR%app.py"
pause

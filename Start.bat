@echo off
setlocal EnableExtensions
title Temperature Sensor (ESP32 Dashboard)
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

set "VENV_DIR=%APP_DIR%\.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [SETUP] Creating virtual environment...
    py -m venv "%VENV_DIR%"
)

echo [SETUP] Installing dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel >nul
if exist "%APP_DIR%requirements.txt" "%PYTHON_EXE%" -m pip install -r "%APP_DIR%requirements.txt"

if "%HOST%"=="" set "HOST=0.0.0.0"
if "%PORT%"=="" set "PORT=8080"

echo [RUN] Starting ESP32 Temperature Dashboard at http://%HOST%:%PORT%
"%PYTHON_EXE%" "%APP_DIR%app.py"
pause

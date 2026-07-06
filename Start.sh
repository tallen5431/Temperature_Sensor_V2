#!/usr/bin/env bash
# Re-exec with bash if invoked via sh.
if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -eu
set -o pipefail 2>/dev/null || true

# ThermaHub — Temperature Monitoring Hub

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

VENV_DIR="$APP_DIR/.venv"
PYTHON_EXE="$VENV_DIR/bin/python"

# First-run setup only: create the venv and install dependencies ONCE. Later
# launches start instantly instead of re-running pip every time.
if [[ ! -x "$PYTHON_EXE" ]]; then
  echo "[SETUP] First run: creating environment and installing dependencies..."
  python3 -m venv "$VENV_DIR"
  "$PYTHON_EXE" -m pip install --upgrade pip setuptools wheel >/dev/null
  "$PYTHON_EXE" -m pip install -r "$APP_DIR/requirements.txt"
fi

: "${HOST:=0.0.0.0}"
: "${PORT:=8080}"

# Open the dashboard in the default browser shortly after startup.
( sleep 3; (xdg-open "http://localhost:${PORT}" || open "http://localhost:${PORT}") >/dev/null 2>&1 || true ) &

echo "[RUN] Starting ThermaHub at http://localhost:${PORT}"
"$PYTHON_EXE" "$APP_DIR/app.py"

if [[ -t 0 ]]; then
  read -r -p "Press Enter to exit..."
fi

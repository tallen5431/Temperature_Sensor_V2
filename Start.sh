#!/usr/bin/env bash
# If invoked as `sh Start.sh` or by a runner that uses /bin/sh, re-exec with bash.
if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -eu
set -o pipefail 2>/dev/null || true

# Temperature Sensor (ESP32 Dashboard)

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

VENV_DIR="$APP_DIR/.venv"
PYTHON_EXE="$VENV_DIR/bin/python"

if [[ ! -x "$PYTHON_EXE" ]]; then
  echo "[SETUP] Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

echo "[SETUP] Installing dependencies..."
"$PYTHON_EXE" -m pip install --upgrade pip setuptools wheel >/dev/null

if [[ -f "$APP_DIR/requirements.txt" ]]; then
  "$PYTHON_EXE" -m pip install -r "$APP_DIR/requirements.txt"
fi

: "${HOST:=0.0.0.0}"
: "${PORT:=8080}"

echo "[RUN] Starting ESP32 Temperature Dashboard at http://${HOST}:${PORT}"
"$PYTHON_EXE" "$APP_DIR/app.py"

# Optional pause when run interactively
if [[ -t 0 ]]; then
  read -r -p "Press Enter to exit..."
fi

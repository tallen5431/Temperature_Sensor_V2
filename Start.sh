#!/usr/bin/env bash
# If invoked as `sh Start.sh` or by a runner that uses /bin/sh, re-exec with bash.
if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -eu
set -o pipefail 2>/dev/null || true

# ── Temperature Sensor Hub ──────────────────────────────────────────────────

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

# ── 1. Locate Python 3.9+ ───────────────────────────────────────────────────
PYTHON_BIN=""
for candidate in python3 python3.13 python3.12 python3.11 python3.10 python3.9; do
  if command -v "$candidate" &>/dev/null; then
    ver=$("$candidate" -c "import sys; print(sys.version_info >= (3,9))" 2>/dev/null)
    if [[ "$ver" == "True" ]]; then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo ""
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║  Python 3.9 or newer is required but was not found.     ║"
  echo "║                                                          ║"
  echo "║  Download it from: https://python.org/downloads         ║"
  echo "╚══════════════════════════════════════════════════════════╝"
  echo ""
  read -r -p "Press Enter to exit..."
  exit 1
fi

PY_VER=$("$PYTHON_BIN" -c "import sys; print('%d.%d' % sys.version_info[:2])")
echo "[INFO] Using Python $PY_VER ($PYTHON_BIN)"

# ── 2. Create / reuse virtual environment ───────────────────────────────────
VENV_DIR="$APP_DIR/.venv"
PYTHON_EXE="$VENV_DIR/bin/python"

if [[ ! -x "$PYTHON_EXE" ]]; then
  echo "[SETUP] Creating virtual environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "[SETUP] Installing / verifying dependencies..."
"$PYTHON_EXE" -m pip install --upgrade pip setuptools wheel -q

if [[ -f "$APP_DIR/requirements.txt" ]]; then
  "$PYTHON_EXE" -m pip install --no-compile -r "$APP_DIR/requirements.txt" -q
fi

# ── 3. Resolve host / port ───────────────────────────────────────────────────
: "${HOST:=0.0.0.0}"
: "${PORT:=8088}"

# ── 4. Open browser automatically via Python's webbrowser module ─────────────
export OPEN_BROWSER=1

# ── 5. Start the hub ─────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Temperature Hub is starting…                           ║"
echo "║  Open http://localhost:$PORT in your browser.          ║"
echo "║  Press Ctrl+C to stop.                                  ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

"$PYTHON_EXE" "$APP_DIR/app.py"

# Optional pause when run interactively
if [[ -t 0 ]]; then
  read -r -p "Press Enter to exit..."
fi

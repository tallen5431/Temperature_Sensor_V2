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
    # `|| ver=""` is load-bearing under `set -e`: a BARE assignment from a
    # command substitution takes the command's exit status, so one broken
    # `python3` on PATH -- a Microsoft Store stub, a dangling pyenv shim, a
    # half-removed install -- killed the launcher HERE, before the loop could
    # try python3.12, and before the "Python 3.9 or newer is required" banner
    # that exists to explain it. The customer saw a window open and close.
    ver=$("$candidate" -c "import sys; print(sys.version_info >= (3,9))" 2>/dev/null) || ver=""
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

PY_VER=$("$PYTHON_BIN" -c "import sys; print('%d.%d' % sys.version_info[:2])") || PY_VER="unknown"
echo "[INFO] Using Python $PY_VER ($PYTHON_BIN)"

# ── 2. Create / reuse virtual environment ───────────────────────────────────
VENV_DIR="$APP_DIR/.venv"
PYTHON_EXE="$VENV_DIR/bin/python"

if [[ ! -x "$PYTHON_EXE" ]]; then
  echo "[SETUP] Creating virtual environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# Only (re)install dependencies when requirements.txt has changed since the last
# successful install.  This keeps day-to-day launches fast and offline-friendly.
REQ_FILE="$APP_DIR/requirements.txt"
REQ_STAMP="$VENV_DIR/.requirements.sha"
if [[ -f "$REQ_FILE" ]]; then
  # Same hazard, plus `pipefail`: on a box with neither sha256sum nor shasum
  # both halves fail and the assignment would abort the launcher rather than
  # simply reinstalling dependencies.
  REQ_HASH=$( (sha256sum "$REQ_FILE" 2>/dev/null || shasum -a 256 "$REQ_FILE" 2>/dev/null) | awk '{print $1}') || REQ_HASH=""
  if [[ ! -f "$REQ_STAMP" || "$(cat "$REQ_STAMP" 2>/dev/null)" != "$REQ_HASH" ]]; then
    echo "[SETUP] Installing / verifying dependencies..."
    "$PYTHON_EXE" -m pip install --upgrade pip setuptools wheel -q
    if "$PYTHON_EXE" -m pip install --no-compile -r "$REQ_FILE" -q; then
      echo "$REQ_HASH" > "$REQ_STAMP"
    else
      echo "[WARN] Dependency install failed; continuing with what is available."
    fi
  else
    echo "[INFO] Dependencies up to date — skipping install."
  fi
fi

# ── 3. Resolve host / port ───────────────────────────────────────────────────
# EXPORTED, not just assigned. `: "${PORT:=8088}"` sets a shell variable that
# app.py never sees, so the banner below and the port the hub actually binds
# were two independent defaults that happened to agree — until one moved.
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8088}"

# ── 4. Open browser automatically via Python's webbrowser module ─────────────
export OPEN_BROWSER=1

# ── 5. Start the hub ─────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Setpoint Hub is starting…                              ║"
echo "║  Open http://localhost:$PORT in your browser.          ║"
echo "║  Press Ctrl+C to stop.                                  ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# `set -e` would abort the script the moment app.py exits non-zero, so the
# pause below never ran and a crash message vanished with the window on anyone
# who launched this by double-clicking. Take the exit code by hand instead.
exit_code=0
"$PYTHON_EXE" "$APP_DIR/app.py" || exit_code=$?

# 130 is Ctrl+C — the normal way to stop the hub, not a fault, and not worth
# making someone press a key for.
if [[ "$exit_code" -ne 0 && "$exit_code" -ne 130 ]]; then
  echo ""
  echo "[ERROR] The hub stopped with exit code $exit_code."
  echo "        The lines above say why. logs/hub.log has the full record."
  if [[ -t 0 ]]; then
    read -r -p "Press Enter to exit..."
  fi
fi
exit "$exit_code"

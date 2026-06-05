#!/usr/bin/env bash
# Build a standalone Temperature Hub executable (Linux/macOS).
# Result: dist/temperature-hub
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
echo "[build] Using $($PY --version)"
$PY -m pip install --upgrade pip -q
$PY -m pip install -r requirements.txt pyinstaller -q

echo "[build] Running PyInstaller..."
$PY -m PyInstaller --clean --noconfirm packaging/temperature_hub.spec

echo ""
echo "[build] Done -> $ROOT/dist/temperature-hub"
echo "[build] Run it, then open http://localhost:8088"

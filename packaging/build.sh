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

echo "[build] Refreshing THIRD-PARTY-LICENSES.md from the installed versions..."
$PY packaging/gen_third_party_licenses.py

echo "[build] Running PyInstaller (onedir)..."
$PY -m PyInstaller --clean --noconfirm packaging/temperature_hub.spec

# Surface the licences at the top of the distribution folder, not just inside
# _internal/, so they travel with the product and are easy to find.
cp LICENSE THIRD-PARTY-LICENSES.md dist/temperature-hub/

echo ""
echo "[build] Done -> $ROOT/dist/temperature-hub/"
echo "[build] Run dist/temperature-hub/temperature-hub, then open http://localhost:8088"

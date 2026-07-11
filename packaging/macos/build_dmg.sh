#!/usr/bin/env bash
# Build TempSensor.app with PyInstaller and package it into a .dmg. Signs with a
# Developer ID and notarizes with Apple ONLY if the relevant env vars are set —
# otherwise it produces a working but UNSIGNED .dmg (users bypass Gatekeeper with
# right-click -> Open). Run on macOS.
#
#   TEMPSENSOR_VERSION=2.4.0 ./packaging/macos/build_dmg.sh
#
# Signing / notarization (optional) env vars:
#   APPLE_SIGN_IDENTITY   e.g. "Developer ID Application: Your Name (TEAMID)"
#   APPLE_API_KEY_PATH    path to the App Store Connect API .p8 key
#   APPLE_API_KEY_ID      the key's ID
#   APPLE_API_ISSUER      the issuer UUID
#
# Output: dist/installer/TempSensor-<version>.dmg
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT"

VERSION="${TEMPSENSOR_VERSION:-0.0.0}"
APP="dist/TempSensor.app"
OUT_DIR="dist/installer"
DMG="$OUT_DIR/TempSensor-$VERSION.dmg"
ENTITLEMENTS="$HERE/entitlements.plist"
PY="${PYTHON:-python3}"

echo "[dmg] Building TempSensor.app (v$VERSION)"
$PY -m pip install --upgrade pip -q
$PY -m pip install -r requirements.txt pyinstaller -q
$PY packaging/gen_third_party_licenses.py
TEMPSENSOR_VERSION="$VERSION" $PY -m PyInstaller --clean --noconfirm packaging/temperature_hub.spec
[ -d "$APP" ] || { echo "[dmg] ERROR: $APP was not produced"; exit 1; }
mkdir -p "$OUT_DIR"

if [ -n "${APPLE_SIGN_IDENTITY:-}" ]; then
  echo "[dmg] Codesigning app (hardened runtime)…"
  codesign --force --deep --options runtime --timestamp \
    --entitlements "$ENTITLEMENTS" --sign "$APPLE_SIGN_IDENTITY" "$APP"
  codesign --verify --strict --verbose=2 "$APP"
else
  echo "[dmg] APPLE_SIGN_IDENTITY not set — producing an UNSIGNED app."
fi

echo "[dmg] Creating $DMG …"
rm -f "$DMG"
hdiutil create -volname "TempSensor" -srcfolder "$APP" -ov -format UDZO "$DMG"

if [ -n "${APPLE_SIGN_IDENTITY:-}" ]; then
  codesign --force --timestamp --sign "$APPLE_SIGN_IDENTITY" "$DMG"
fi

if [ -n "${APPLE_API_KEY_PATH:-}" ] && [ -n "${APPLE_API_KEY_ID:-}" ] && [ -n "${APPLE_API_ISSUER:-}" ]; then
  echo "[dmg] Notarizing with Apple (this can take a few minutes)…"
  xcrun notarytool submit "$DMG" --key "$APPLE_API_KEY_PATH" \
    --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER" --wait
  echo "[dmg] Stapling ticket…"
  xcrun stapler staple "$DMG"
else
  echo "[dmg] Notary creds not set — skipping notarization."
fi

echo "[dmg] Done -> $DMG"

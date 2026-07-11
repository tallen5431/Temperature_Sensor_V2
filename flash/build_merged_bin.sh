#!/usr/bin/env bash
#
# Build the ThermaProbe firmware and produce ONE merged .bin that both
# ESP Web Tools (browser flashing, see flash/index.html) and esptool can flash
# at offset 0x0.
#
# Requires: arduino-cli (with the esp32 core installed) and esptool.
#   arduino-cli core install esp32:esp32
#   pip install esptool
#
# Run from the repository root:  ./flash/build_merged_bin.sh
#
# NOTE: like every firmware step in this repo, the produced binary MUST be
# validated on real ESP32 hardware (build + flash + QC per docs/QC_CHECKLIST.md)
# before you ship it. This script has not been run on hardware here.
set -euo pipefail

SKETCH_DIR="esp32_temp_probe"
SKETCH_NAME="esp32_temp_probe"
# Adjust FQBN to your exact board if needed (e.g. esp32:esp32:esp32doit-devkit-v1).
FQBN="${FQBN:-esp32:esp32:esp32}"
OUT="flash/thermaprobe-esp32.merged.bin"

command -v arduino-cli >/dev/null || { echo "arduino-cli not found — see the header."; exit 1; }
command -v esptool >/dev/null 2>&1 || command -v esptool.py >/dev/null 2>&1 || {
  echo "esptool not found (pip install esptool)."; exit 1; }
ESPTOOL="$(command -v esptool || command -v esptool.py)"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

echo "==> Compiling $SKETCH_DIR for $FQBN"
arduino-cli compile --fqbn "$FQBN" --output-dir "$BUILD_DIR" "$SKETCH_DIR"

APP="$BUILD_DIR/${SKETCH_NAME}.ino.bin"
BOOT="$BUILD_DIR/${SKETCH_NAME}.ino.bootloader.bin"
PART="$BUILD_DIR/${SKETCH_NAME}.ino.partitions.bin"
# boot_app0.bin ships with the esp32 core (path varies by OS/install).
BOOTAPP0="$(find "${HOME}/.arduino15" "${HOME}/Library/Arduino15" -name boot_app0.bin 2>/dev/null | head -1 || true)"

for f in "$APP" "$BOOT" "$PART" "$BOOTAPP0"; do
  [ -n "$f" ] && [ -f "$f" ] || { echo "Missing build artifact: '$f'"; exit 1; }
done

echo "==> Merging into $OUT"
mkdir -p "$(dirname "$OUT")"
# Standard ESP32 flash layout: bootloader @0x1000, partitions @0x8000,
# boot_app0 @0xe000, application @0x10000.
"$ESPTOOL" --chip esp32 merge_bin -o "$OUT" \
  --flash_mode dio --flash_freq 40m --flash_size 4MB \
  0x1000 "$BOOT" \
  0x8000 "$PART" \
  0xe000 "$BOOTAPP0" \
  0x10000 "$APP"

echo "==> Done: $OUT"
echo "    Keep flash/manifest.json 'version' in sync with FW_VERSION, then host the"
echo "    flash/ folder over HTTPS (e.g. GitHub Pages) so buyers can flash from Chrome."

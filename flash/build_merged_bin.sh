#!/usr/bin/env bash
#
# Build the Setpoint firmware and produce ONE merged .bin that both
# ESP Web Tools (browser flashing, see flash/index.html) and esptool can flash
# at offset 0x0.
#
# Target hardware: ESP32-C3 with the "No OTA (2MB APP / 2MB SPIFFS)" partition
# scheme — the layout the firmware is shipped/flashed with. (The sketch is too
# large for the default partition scheme, so this MUST match.)  Browser flashing
# does NOT require OTA: ESP Web Tools writes the whole image — bootloader,
# partition table and app — over USB serial, so a no-OTA build flashes fine.
# OTA only concerns *wireless* updates after deployment, which this product
# doesn't use.
#
# Requires: arduino-cli (with the esp32 core installed) and esptool.
#   arduino-cli core install esp32:esp32
#   pip install esptool
#
# Run from the repository root:  ./flash/build_merged_bin.sh
# Override the board with e.g.  FQBN=esp32:esp32:esp32c3:PartitionScheme=huge_app ./flash/build_merged_bin.sh
#
# NOTE: like every firmware step in this repo, the produced binary MUST be
# validated on real ESP32-C3 hardware (build + flash + QC per
# docs/QC_CHECKLIST.md) before you ship it. This script has not been run on
# hardware here.
set -euo pipefail

SKETCH_DIR="esp32_temp_probe"
SKETCH_NAME="esp32_temp_probe"
# ESP32-C3 with the No-OTA (2MB APP / 2MB SPIFFS) partition scheme — the scheme
# the firmware is flashed with. Change the board here if your unit differs.
FQBN="${FQBN:-esp32:esp32:esp32c3:PartitionScheme=no_ota}"
OUT="flash/setpoint-esp32c3.merged.bin"
# Chip passed to esptool for the fallback manual merge.
CHIP="${CHIP:-esp32c3}"

command -v arduino-cli >/dev/null || { echo "arduino-cli not found — see the header."; exit 1; }
command -v esptool >/dev/null 2>&1 || command -v esptool.py >/dev/null 2>&1 || {
  echo "esptool not found (pip install esptool)."; exit 1; }
ESPTOOL="$(command -v esptool || command -v esptool.py)"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

echo "==> Compiling $SKETCH_DIR for $FQBN"
arduino-cli compile --fqbn "$FQBN" --output-dir "$BUILD_DIR" "$SKETCH_DIR"

mkdir -p "$(dirname "$OUT")"

# Preferred path: the esp32 Arduino core already emits a single, chip-correct
# merged image (right bootloader offset for the C3, right partition table for the
# selected scheme, boot_app0 included). Use it verbatim — no manual offsets to
# get wrong, and it automatically reflects the no-OTA scheme.
CORE_MERGED="$BUILD_DIR/${SKETCH_NAME}.ino.merged.bin"
if [ -f "$CORE_MERGED" ]; then
  echo "==> Using core-produced merged image"
  cp "$CORE_MERGED" "$OUT"
else
  # Fallback for older cores that don't emit .merged.bin: merge by hand. The C3
  # bootloader lives at 0x0 (unlike classic ESP32's 0x1000).
  echo "==> Core merged image not found; merging manually for $CHIP"
  APP="$BUILD_DIR/${SKETCH_NAME}.ino.bin"
  BOOT="$BUILD_DIR/${SKETCH_NAME}.ino.bootloader.bin"
  PART="$BUILD_DIR/${SKETCH_NAME}.ino.partitions.bin"
  # boot_app0.bin ships with the esp32 core (path varies by OS/install).
  BOOTAPP0="$(find "${HOME}/.arduino15" "${HOME}/Library/Arduino15" -name boot_app0.bin 2>/dev/null | head -1 || true)"
  for f in "$APP" "$BOOT" "$PART" "$BOOTAPP0"; do
    [ -n "$f" ] && [ -f "$f" ] || { echo "Missing build artifact: '$f'"; exit 1; }
  done
  "$ESPTOOL" --chip "$CHIP" merge_bin -o "$OUT" \
    --flash_mode dio --flash_freq 80m --flash_size 4MB \
    0x0     "$BOOT" \
    0x8000  "$PART" \
    0xe000  "$BOOTAPP0" \
    0x10000 "$APP"
fi

echo "==> Done: $OUT"
echo "    Keep flash/manifest.json 'version' in sync with FW_VERSION, then host the"
echo "    flash/ folder over HTTPS (e.g. GitHub Pages) so buyers can flash from Chrome."

#!/usr/bin/env python3
"""factory_flash.py -- guided flash + QC helper for one TempSensor unit.

The shipping firmware is the Arduino sketch
    esp32_temp_probe/esp32_temp_probe.ino
(the deep-sleep battery firmware). This helper:

  1. Flashes the sketch with `arduino-cli compile` + `arduino-cli upload`.
     (The old PlatformIO `pio run -t upload` path is gone with main.cpp.)
  2. Captures the unit's identity from the boot serial log's machine-readable
     line, which the firmware prints on every boot:
         [label] probe_id=TempSensor-XXXXXX ap_ssid=TempSensor-XXXXXX ap_pass=none
     probe_id/ap_ssid are derived from the DS18B20 sensor ROM (or the ESP32
     efuse MAC when no sensor is present) and are PERSISTED in NVS. The setup AP
     is OPEN (no password), so ap_pass is always `none`; this serial line -- not
     the MAC -- is the source of truth for the label.
  3. Optionally reads the ESP32 MAC (esptool) purely to record it in the batch log.
  4. Prints the unit label + a QC checklist for the operator to tick before boxing.

Pure standard library + subprocess (pyserial optional, used to auto-capture the
[label] line). Degrades gracefully: if a tool is missing it prints how to proceed
instead of crashing.

BENCH VALIDATION NOTE: the arduino-cli FQBN and partition-scheme option below
still need to be confirmed against your exact board + installed esp32 core
version (see run_flash()). They are the documented defaults, not yet verified on
hardware in this environment.

Usage:
    python factory_flash.py                       # flash, capture label, QC
    python factory_flash.py --no-flash            # just capture label + QC (already flashed)
    python factory_flash.py --port /dev/ttyUSB0   # serial port for arduino-cli/esptool/pyserial
    python factory_flash.py --fqbn esp32:esp32:esp32c3
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time

# Canonical sketch, resolved relative to this file (firmware/ -> ../esp32_temp_probe).
THIS_DIR   = os.path.dirname(os.path.abspath(__file__))
SKETCH_DIR = os.path.normpath(os.path.join(THIS_DIR, "..", "esp32_temp_probe"))

# Default board target -- NEEDS BENCH VALIDATION for your board + esp32 core:
#   * ESP32-C3 dev board -> FQBN "esp32:esp32:esp32c3" (the shipping hardware)
#   * Partition scheme "No OTA (2MB APP/2MB SPIFFS)" gives the ~2 MB LittleFS the
#     offline buffer expects (and the sketch is too big for the default scheme);
#     expressed as a board option below. Confirm the exact option key/value with
#     `arduino-cli board details --fqbn esp32:esp32:esp32c3`.
DEFAULT_FQBN     = "esp32:esp32:esp32c3"
PARTITION_OPTION = "PartitionScheme=no_ota"   # verify key/value for your core version

# Documentation only -- kept identical to firmware/src/protocol.h. The real
# values come from the firmware's [label] serial line, NOT from the MAC.
PROBE_ID_PREFIX    = "TempSensor-"
FW_VERSION         = "2.4.0"

# Matches the firmware's machine-readable boot line. The setup AP is open, so
# ap_pass is always `none`; it is still captured so the format stays stable.
#   [label] probe_id=<id> ap_ssid=<id> ap_pass=none
LABEL_RE = re.compile(r"\[label\]\s+probe_id=(\S+)\s+ap_ssid=(\S+)\s+ap_pass=(\S+)")


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def run_flash(port: str | None, fqbn: str) -> bool:
    """Compile + upload the sketch with arduino-cli. Returns True on success.

    NOTE: FQBN + partition option need bench validation for your board/core.
    """
    if not _have("arduino-cli"):
        print("!! arduino-cli not found.")
        print("   Install it: https://arduino.github.io/arduino-cli/  then set up esp32:")
        print("     arduino-cli core update-index")
        print("     arduino-cli core install esp32:esp32")
        print("     arduino-cli lib install WiFiManager ArduinoJson OneWire DallasTemperature")
        print(f"   Then flash manually from {SKETCH_DIR}:")
        print(f"     arduino-cli compile --fqbn {fqbn} .")
        print(f"     arduino-cli upload -p <PORT> --fqbn {fqbn} .")
        return False

    fqbn_full = f"{fqbn}:{PARTITION_OPTION}" if PARTITION_OPTION else fqbn

    compile_cmd = ["arduino-cli", "compile", "--fqbn", fqbn_full, SKETCH_DIR]
    print("==> Compiling:", " ".join(compile_cmd))
    try:
        if subprocess.call(compile_cmd) != 0:
            print("!! Compile failed.")
            return False
    except Exception as e:  # noqa: BLE001
        print(f"!! Compile failed to launch: {e}")
        return False

    upload_cmd = ["arduino-cli", "upload", "--fqbn", fqbn_full, SKETCH_DIR]
    if port:
        upload_cmd += ["-p", port]
    print("==> Uploading:", " ".join(upload_cmd))
    try:
        return subprocess.call(upload_cmd) == 0
    except Exception as e:  # noqa: BLE001
        print(f"!! Upload failed to launch: {e}")
        return False


def read_mac(port: str | None) -> str | None:
    """Return the chip MAC as 'AA:BB:CC:DD:EE:FF' via esptool, or None.

    Recorded in the batch log only -- the probe_id is NO LONGER derived from the
    MAC (it comes from the DS18B20 ROM and is read off the [label] serial line).
    """
    candidates = []
    if _have("esptool.py"):
        candidates.append(["esptool.py"])
    candidates.append([sys.executable, "-m", "esptool"])

    args = ["read_mac"]
    if port:
        args = ["--port", port] + args

    for base in candidates:
        try:
            out = subprocess.run(base + args, capture_output=True, text=True, timeout=60)
        except Exception:  # noqa: BLE001
            continue
        text = (out.stdout or "") + "\n" + (out.stderr or "")
        m = re.search(r"MAC:\s*([0-9A-Fa-f:]{17})", text)
        if m:
            return m.group(1).upper()
    return None


def capture_label(port: str | None, timeout: float = 30.0) -> dict | None:
    """Capture probe_id / ap_ssid / ap_pass from the boot serial '[label]' line.

    The firmware prints this line on every boot/wake. Needs pyserial + a known
    --port. Returns {'probe_id','ap_ssid','ap_pass'} or None (then the operator
    reads the line by hand from the serial monitor; tap the board's EN/reset
    button to make it re-print).
    """
    if not port:
        return None
    try:
        import serial  # pyserial
    except Exception:
        return None
    try:
        with serial.Serial(port, 115200, timeout=1) as ser:
            deadline = time.time() + timeout
            while time.time() < deadline:
                line = ser.readline().decode("utf-8", "ignore")
                m = LABEL_RE.search(line)
                if m:
                    return {"probe_id": m.group(1),
                            "ap_ssid":  m.group(2),
                            "ap_pass":  m.group(3)}
    except Exception:  # noqa: BLE001
        return None
    return None


def print_label(label: dict | None, mac: str | None) -> None:
    pid  = label["probe_id"] if label else "(read from serial '[label]' line)"
    ssid = label["ap_ssid"]  if label else pid
    line = "=" * 56
    print("\n" + line)
    print("  TEMPSENSOR UNIT LABEL  (write on the enclosure / QR)")
    print(line)
    print(f"  Probe ID      : {pid}")
    print(f"  Setup Wi-Fi   : {ssid}   (open -- no password)")
    print(f"  mDNS / .local : {pid}.local")
    if mac:
        print(f"  MAC (log only): {mac}")
    print(f"  Firmware      : {FW_VERSION} / proto 1")
    print(line)
    if not label:
        print("  NOTE: pyserial/--port unavailable -- read the identity from the boot")
        print("        serial line (tap EN/reset to re-print it):")
        print("        [label] probe_id=... ap_ssid=... ap_pass=none")
    print()


def print_qc_checklist(label: dict | None) -> None:
    pid  = label["probe_id"] if label else "<probe_id from [label] line>"
    ssid = label["ap_ssid"]  if label else pid
    print("QC CHECKLIST -- verify each before boxing the unit:")
    steps = [
        f"[ ] Serial boots and prints:  [label] probe_id={pid} ap_ssid={ssid} ap_pass=none",
        f"[ ] probe_id ({pid}) is not already used in the batch serial log (unique)",
        f"[ ] SoftAP \"{ssid}\" is visible on a phone and is OPEN (joins with no password)",
        "[ ] Captive portal / http://192.168.4.1 shows the WiFiManager setup page",
        f"[ ] After joining bench Wi-Fi, GET /whoami returns id == {pid} and fw_version == {FW_VERSION}",
        "[ ] GET /status shows a plausible last_c (room temp; not 85.0 / -127 / NaN)",
        "[ ] One live bench ingest: a fresh row for this probe_id lands in the hub telemetry CSV",
        "[ ] Probe appears in TempSensor's dashboard probe list",
        "[ ] probe_id and SoftAP SSID are recorded on the label + serial log",
    ]
    for s in steps:
        print("   " + s)
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Flash + QC one TempSensor unit (esp32_temp_probe.ino).")
    ap.add_argument("--no-flash", action="store_true",
                    help="skip flashing; only capture the [label] line + print label/QC")
    ap.add_argument("--port", default=None,
                    help="serial port for arduino-cli/esptool/pyserial (e.g. /dev/ttyUSB0, COM5)")
    ap.add_argument("--fqbn", default=DEFAULT_FQBN,
                    help=f"arduino-cli board FQBN (default {DEFAULT_FQBN}; needs bench validation)")
    args = ap.parse_args()

    if not args.no_flash:
        if not run_flash(args.port, args.fqbn):
            print("!! Flashing did not complete. Fix the above, then re-run.")
            # Still try to capture the label + print QC so the operator can proceed.

    # The [label] line is the authoritative identity source; capture it first
    # (this releases the serial port before esptool resets the chip below).
    label = capture_label(args.port)
    if not label:
        print("!! Could not auto-capture the [label] line (needs pyserial + --port).")
        print("   Open a serial monitor @115200 and read it from the boot line")
        print("   (tap the board's EN/reset button to re-print it):")
        print("     [label] probe_id=... ap_ssid=... ap_pass=none")

    mac = read_mac(args.port)   # optional -- for the batch-log 'mac' column only

    print_label(label, mac)
    print_qc_checklist(label)
    return 0 if label else 1


if __name__ == "__main__":
    raise SystemExit(main())

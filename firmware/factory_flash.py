#!/usr/bin/env python3
"""factory_flash.py -- guided flash + QC helper for one ThermaProbe unit.

For a small maker producing units on a bench. It:

  1. Flashes the firmware with `pio run -t upload`.
  2. Reads the ESP32 factory MAC (via esptool) and computes the SAME label
     identity the firmware derives at boot:
         probe_id    = "ThermaProbe-" + UPPERCASE hex of last 3 MAC bytes
         hostname    = "thermaprobe-" + lowercase(hex)
         SoftAP SSID = probe_id
     (Derivation mirrors firmware/src/protocol.h -- keep the two in sync.)
  3. Captures the per-unit RANDOM SoftAP password from the boot serial log's
     "[label] ... ap_password=..." line (the firmware generates it once and
     stores it in NVS; it is deliberately NOT derivable from the MAC).
  4. Prints the unit label + a QC checklist for the operator to tick before boxing.

Pure standard library + subprocess (pyserial optional, only for auto-capturing
the SoftAP password). Degrades gracefully: if a tool is missing it prints how to
proceed instead of crashing.

Usage:
    python factory_flash.py                # flash, read MAC, capture pass, QC
    python factory_flash.py --no-flash     # just read MAC + capture pass + label/QC
    python factory_flash.py --port COM5    # serial port for pio/esptool/pyserial
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time

# Kept identical to firmware/src/protocol.h
PROBE_ID_PREFIX = "ThermaProbe-"
HOSTNAME_PREFIX = "thermaprobe-"


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def run_flash(port: str | None) -> bool:
    """Flash the firmware via PlatformIO. Returns True on success."""
    if not _have("pio"):
        print("!! PlatformIO CLI ('pio') not found.")
        print("   Install it:  pip install platformio")
        print("   Then re-run, or flash manually:  pio run -t upload")
        return False
    cmd = ["pio", "run", "-t", "upload"]
    if port:
        cmd += ["--upload-port", port]
    print("==> Flashing firmware:", " ".join(cmd))
    try:
        return subprocess.call(cmd) == 0
    except Exception as e:  # noqa: BLE001
        print(f"!! Flash failed to launch: {e}")
        return False


def read_mac(port: str | None) -> str | None:
    """Return the chip MAC as 'AA:BB:CC:DD:EE:FF' using esptool, or None."""
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


def read_ap_password(port: str | None, timeout: float = 25.0) -> str | None:
    """Capture the per-unit random SoftAP password from the boot serial log.

    Best-effort: needs pyserial and a known --port. Returns the password (e.g.
    'TP-…') or None. On None, the operator reads it from the serial monitor's
    '[label]' line manually (see the printed guidance).
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
                m = re.search(r"\[label\].*ap_password=(\S+)", line)
                if m:
                    return m.group(1)
    except Exception:
        return None
    return None


def identity_from_mac(mac: str) -> dict:
    """Compute the MAC-derived label identity from a 'AA:BB:CC:DD:EE:FF' string.

    (The SoftAP password is NOT derived here — it is random per unit; see
    read_ap_password.)
    """
    parts = [p for p in mac.split(":") if p]
    if len(parts) != 6:
        raise ValueError(f"unexpected MAC format: {mac!r}")
    b = [p.upper() for p in parts]
    hex6 = "".join(b[3:6])                       # last 3 bytes
    return {
        "mac": ":".join(b),
        "probe_id": PROBE_ID_PREFIX + hex6,
        "hostname": HOSTNAME_PREFIX + hex6.lower(),
        "ap_ssid": PROBE_ID_PREFIX + hex6,
    }


def print_label(idy: dict, ap_password: str | None) -> None:
    pw = ap_password or "(read from serial '[label]' line)"
    line = "=" * 52
    print("\n" + line)
    print("  THERMAPROBE UNIT LABEL  (write on the enclosure / QR)")
    print(line)
    print(f"  MAC          : {idy['mac']}")
    print(f"  Probe ID     : {idy['probe_id']}")
    print(f"  Hostname     : {idy['hostname']}.local")
    print(f"  Setup Wi-Fi  : {idy['ap_ssid']}")
    print(f"  Setup pass   : {pw}")
    print(line)
    if not ap_password:
        print("  NOTE: pyserial/--port unavailable — capture the SoftAP password from")
        print("        the boot serial monitor line:  [label] ... ap_password=TP-XXXX")
    print()


def print_qc_checklist(idy: dict, ap_password: str | None) -> None:
    pw = ap_password or "<the ap_password from serial>"
    print("QC CHECKLIST -- verify each before boxing the unit:")
    steps = [
        f"[ ] Serial boots and prints probe_id = {idy['probe_id']}",
        f"[ ] SoftAP \"{idy['ap_ssid']}\" is visible on a phone (WPA2, pass {pw})",
        "[ ] Captive portal / http://192.168.4.1 shows the setup page",
        "[ ] After joining bench Wi-Fi, GET /whoami returns the same probe_id",
        "[ ] GET /status shows sensor_ok=true and a plausible temperature_c",
        "[ ] One successful bench ingest POST: /status last_post_ok=true, "
        "last_post_code=200",
        "[ ] Probe appears in ThermaHub's dashboard probe list",
        "[ ] The SoftAP password is recorded on the label and the serial log",
    ]
    for s in steps:
        print("   " + s)
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Flash + QC one ThermaProbe unit.")
    ap.add_argument("--no-flash", action="store_true",
                    help="skip flashing; only read MAC + capture pass + print label/QC")
    ap.add_argument("--port", default=None,
                    help="serial port for pio/esptool/pyserial (e.g. COM5, /dev/ttyUSB0)")
    args = ap.parse_args()

    if not args.no_flash:
        if not run_flash(args.port):
            print("!! Flashing did not complete. Fix the above, then re-run.")
            # Still try to read MAC + print the label so QC can proceed manually.

    mac = read_mac(args.port)
    if not mac:
        print("!! Could not read the chip MAC via esptool.")
        print("   Install esptool:  pip install esptool")
        print("   Or read it from the boot serial log ('mac=' line) and compute")
        print("   the label by hand:")
        print("     probe_id = ThermaProbe-<UPPER hex of last 3 MAC bytes>")
        print("   The SoftAP password is on the serial '[label]' line (random per unit).")
        return 1

    idy = identity_from_mac(mac)
    ap_password = read_ap_password(args.port)
    print_label(idy, ap_password)
    print_qc_checklist(idy, ap_password)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

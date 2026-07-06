#!/usr/bin/env python3
"""factory_flash.py -- guided flash + QC helper for one ThermaProbe unit.

For a small maker producing units on a bench. It:

  1. Flashes the firmware with `pio run -t upload`.
  2. Reads the ESP32 factory MAC (via esptool) and computes the SAME label
     identity the firmware derives at boot:
         probe_id    = "ThermaProbe-" + UPPERCASE hex of last 3 MAC bytes
         hostname    = "thermaprobe-" + lowercase(hex)
         SoftAP SSID = probe_id
         AP password = "TP-" + UPPERCASE hex of last 4 MAC bytes
     (Derivation mirrors firmware/src/protocol.h -- keep the two in sync.)
  3. Prints a QC checklist for the operator to tick before boxing the unit.

Pure standard library + subprocess. Degrades gracefully: if pio or esptool are
missing it prints how to install them instead of crashing.

Usage:
    python factory_flash.py                # flash, then compute label, then QC
    python factory_flash.py --no-flash     # just read MAC + print label/QC
    python factory_flash.py --port COM5    # pass a serial port through to tools
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys

# Kept identical to firmware/src/protocol.h
PROBE_ID_PREFIX = "ThermaProbe-"
HOSTNAME_PREFIX = "thermaprobe-"
AP_PASSWORD_PREFIX = "TP-"


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
    # esptool ships as the 'esptool.py' console script and/or 'python -m esptool'.
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


def identity_from_mac(mac: str) -> dict:
    """Compute the label identity from a 'AA:BB:CC:DD:EE:FF' MAC string."""
    parts = [p for p in mac.split(":") if p]
    if len(parts) != 6:
        raise ValueError(f"unexpected MAC format: {mac!r}")
    b = [p.upper() for p in parts]
    hex6 = "".join(b[3:6])                       # last 3 bytes
    pass8 = "".join(b[2:6])                       # last 4 bytes
    return {
        "mac": ":".join(b),
        "probe_id": PROBE_ID_PREFIX + hex6,
        "hostname": HOSTNAME_PREFIX + hex6.lower(),
        "ap_ssid": PROBE_ID_PREFIX + hex6,
        "ap_password": AP_PASSWORD_PREFIX + pass8,
    }


def print_label(idy: dict) -> None:
    line = "=" * 52
    print("\n" + line)
    print("  THERMAPROBE UNIT LABEL  (write on the enclosure / QR)")
    print(line)
    print(f"  MAC          : {idy['mac']}")
    print(f"  Probe ID     : {idy['probe_id']}")
    print(f"  Hostname     : {idy['hostname']}.local")
    print(f"  Setup Wi-Fi  : {idy['ap_ssid']}")
    print(f"  Setup pass   : {idy['ap_password']}")
    print(line + "\n")


def print_qc_checklist(idy: dict) -> None:
    print("QC CHECKLIST -- verify each before boxing the unit:")
    steps = [
        f"[ ] Serial boots and prints probe_id = {idy['probe_id']}",
        f"[ ] SoftAP \"{idy['ap_ssid']}\" is visible on a phone (WPA2, "
        f"pass {idy['ap_password']})",
        "[ ] Captive portal / http://192.168.4.1 shows the setup page",
        "[ ] After joining bench Wi-Fi, GET /whoami returns the same probe_id",
        "[ ] GET /status shows sensor_ok=true and a plausible temperature_c",
        "[ ] One successful bench ingest POST: /status last_post_ok=true, "
        "last_post_code=200",
        "[ ] Probe appears in ThermaHub's dashboard probe list",
    ]
    for s in steps:
        print("   " + s)
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Flash + QC one ThermaProbe unit.")
    ap.add_argument("--no-flash", action="store_true",
                    help="skip flashing; only read MAC and print label/QC")
    ap.add_argument("--port", default=None,
                    help="serial port to pass to pio/esptool (e.g. COM5, /dev/ttyUSB0)")
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
        print("     probe_id    = ThermaProbe-<UPPER hex of last 3 MAC bytes>")
        print("     ap_password = TP-<UPPER hex of last 4 MAC bytes>")
        return 1

    idy = identity_from_mac(mac)
    print_label(idy)
    print_qc_checklist(idy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Post readings to a running hub as a fake probe — to test alerts without hardware.

The hub secures its mutating API with an auto-generated device token, so this
reads it from the hub's config.json by default (override with --token).

Examples
--------
  # One reading of 99 C from a probe called "fridge-test" (trips a HIGH alert if
  # that probe's max is below 99 on the Devices page):
  python scripts/simulate_probe.py --probe fridge-test --temp 99

  # Ramp 20 -> 60 C, one reading every 5 s, to watch an alert fire then recover:
  python scripts/simulate_probe.py --probe fridge-test --from 20 --to 60 --step 5 --interval 5

  # Stop sending and wait to trigger an OFFLINE alert (set "Offline after" to 1 min).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _default_token() -> str:
    """Best-effort read of provision_token from the hub's per-user config.json."""
    candidates = []
    if os.getenv("DATA_DIR"):
        candidates.append(Path(os.environ["DATA_DIR"]) / "config.json")
    if sys.platform == "win32" and os.getenv("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"]) / "Setpoint" / "config.json")
    elif sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Application Support" / "Setpoint" / "config.json")
    else:
        candidates.append(Path.home() / ".local" / "share" / "Setpoint" / "config.json")
    candidates.append(Path(__file__).resolve().parent.parent / "config.json")  # dev checkout
    for c in candidates:
        try:
            if c.exists():
                return json.loads(c.read_text(encoding="utf-8")).get("provision_token", "") or ""
        except Exception:
            pass
    return ""


def post_reading(url: str, token: str, probe: str, temp: float) -> int:
    body = json.dumps({"temperature_c": temp, "probe_id": probe}).encode("utf-8")
    headers = {"Content-Type": "application/json", "X-Probe-ID": probe}
    if token:
        headers["X-Token"] = token
    req = urllib.request.Request(url.rstrip("/") + "/api/ingest", data=body,
                                 method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main() -> None:
    ap = argparse.ArgumentParser(description="Simulate a probe posting readings to the hub.")
    ap.add_argument("--url", default="http://localhost:8088", help="hub base URL")
    ap.add_argument("--probe", default="sim-probe", help="probe id to report as")
    ap.add_argument("--token", default=None, help="device token (default: read from config.json)")
    ap.add_argument("--temp", type=float, help="post a single reading at this °C, then exit")
    ap.add_argument("--from", dest="t_from", type=float, help="ramp start °C")
    ap.add_argument("--to", dest="t_to", type=float, help="ramp end °C")
    ap.add_argument("--step", type=float, default=1.0, help="°C change per reading in a ramp")
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between readings")
    args = ap.parse_args()

    token = args.token if args.token is not None else _default_token()

    def _note(code: int) -> str:
        if code == 401:
            return "  (401 = token required/mismatch; pass --token <provision_token from config.json>)"
        if code == 400:
            return "  (400 = value rejected; must be finite and within -60..150 C)"
        return ""

    if args.temp is not None:
        code = post_reading(args.url, token, args.probe, args.temp)
        print(f"{args.probe}: {args.temp} C -> HTTP {code}{_note(code)}")
        return

    if args.t_from is not None and args.t_to is not None:
        step = abs(args.step) if args.t_to >= args.t_from else -abs(args.step)
        t = args.t_from
        try:
            while (step > 0 and t <= args.t_to) or (step < 0 and t >= args.t_to):
                code = post_reading(args.url, token, args.probe, round(t, 2))
                print(f"{args.probe}: {round(t, 2)} C -> HTTP {code}{_note(code)}")
                t += step
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nstopped.")
        return

    ap.print_help()


if __name__ == "__main__":
    main()

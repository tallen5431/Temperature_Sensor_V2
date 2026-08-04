#!/usr/bin/env python3
"""Read-only snapshot of what a hub holds, per site — the multi-site check tool.

Answers the question you actually have while setting up or debugging a roll-up:
*is head office receiving my store's readings, or is something else going on?*

    python3 scripts/site_report.py

Opens the database **read-only** and never writes. That matters more than it
sounds: the obvious one-liner, ``sqlite3.connect('temperature_log.db')``, CREATES
an empty database when run from the wrong directory, so a mistyped path reports
"no such table: readings" and leaves a junk file behind. This refuses instead.

Run it on either hub:

* On a **store** hub, every row should show site ``(local)`` — its own probes.
* On a **head-office** hub, forwarded rows carry their store's label. A row
  showing ``(local)`` on an HQ hub means a probe is posting to it *directly*,
  which usually means two hubs on one LAN are fighting over it — see
  docs/MULTI_SITE.md.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _candidates() -> list:
    """Where a hub keeps its database, most likely first."""
    out = []
    if os.getenv("DATA_DIR"):
        out.append(Path(os.environ["DATA_DIR"]) / "temperature_log.db")
    if os.getenv("DB_FILE"):
        out.append(Path(os.environ["DB_FILE"]))
    out.append(REPO / "temperature_log.db")            # running from source
    if sys.platform == "win32" and os.getenv("LOCALAPPDATA"):
        out.append(Path(os.environ["LOCALAPPDATA"]) / "Setpoint" / "temperature_log.db")
    elif sys.platform == "darwin":
        out.append(Path.home() / "Library" / "Application Support" / "Setpoint"
                   / "temperature_log.db")
    else:
        out.append(Path.home() / ".local" / "share" / "Setpoint" / "temperature_log.db")
    return out


def _find_db() -> Path:
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        if not p.exists():
            sys.exit(f"No database at {p}")
        return p
    for c in _candidates():
        if c.exists():
            return c
    # By far the most common reason, and the one worth naming: the hub has not
    # been started since the database was created or deleted. It is made on
    # startup, so "no database" usually means "no hub running", not "wrong path".
    sys.exit("No database found — has the hub been started yet?\n"
             "It is created on first run, so a hub that has never started (or one\n"
             "whose database was just deleted) has none until you start it again.\n"
             "\nIf it lives somewhere else, pass the path:\n"
             "  python3 scripts/site_report.py /path/to/temperature_log.db\n"
             "\nLooked in:\n  " + "\n  ".join(str(c) for c in _candidates()))


def _config_for(db_path: Path) -> dict:
    for p in (db_path.parent / "config.json", REPO / "config.json"):
        try:
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a missing/bad config is not fatal here
            pass
    return {}


def main() -> None:
    db_path = _find_db()
    print(f"database : {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT site, probe_id, COUNT(*) AS n, MAX(ts) AS newest "
            "FROM readings GROUP BY site, probe_id ORDER BY site, probe_id").fetchall()
    except sqlite3.OperationalError as e:
        sys.exit(f"Could not read readings from {db_path}: {e}")

    total = sum(r[2] for r in rows)
    print(f"readings : {total:,}\n")
    if not rows:
        print("  (no readings yet)")
    else:
        print(f"  {'site':<20} {'probe':<24} {'rows':>10}   newest")
        print(f"  {'-'*20} {'-'*24} {'-'*10}   {'-'*19}")
        for site, pid, n, newest in rows:
            label = site if site else "(local)"
            print(f"  {label:<20} {(pid or '(none)'):<24} {n:>10,}   {str(newest)[:19]}")

    sites = sorted({r[0] for r in rows if r[0]})
    local = sum(r[2] for r in rows if not r[0])
    print()
    if sites:
        print(f"forwarded from : {', '.join(sites)}")
    print(f"local readings : {local:,}"
          + ("   <- probes posting directly to THIS hub" if local and sites else ""))

    # Alerts are a separate record from readings: what each hub's own engine
    # decided against its own thresholds. Worth its own line, because "head
    # office has the temperatures but not the alerts" is a distinct failure.
    try:
        ev = conn.execute("SELECT site, kind, COUNT(*) FROM events "
                          "GROUP BY site, kind ORDER BY site, kind").fetchall()
    except sqlite3.OperationalError:
        ev = []
    if ev:
        print("\nalert events   :")
        for site, kind, n in ev:
            print(f"  {(site or '(local)'):<20} {kind:<24} {n:>10,}")

    # --- this hub's own forwarding settings, if any --------------------------
    up = (_config_for(db_path).get("upstream") or {})
    if up.get("enabled"):
        try:
            cur = int(conn.execute(
                "SELECT v FROM meta WHERE k='forwarder.last_id'").fetchone()[0])
        except Exception:  # noqa: BLE001
            cur = 0
        try:
            pending = conn.execute(
                "SELECT COUNT(*) FROM readings WHERE id > ? AND (site IS NULL OR site = '')",
                (cur,)).fetchone()[0]
        except sqlite3.OperationalError:
            pending = "?"
        print(f"\nforwarding     : ON -> {up.get('url','?')} as \"{up.get('site','?')}\"")
        print(f"  sent so far  : up to row {cur:,}")
        print(f"  still to send: {pending:,}" if isinstance(pending, int)
              else f"  still to send: {pending}")
    elif "upstream" in _config_for(db_path):
        print("\nforwarding     : off")
    conn.close()


if __name__ == "__main__":
    main()

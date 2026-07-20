"""Build a single diagnostics snapshot of the running hub.

Used by the Diagnostics page and the ``/api/diagnostics`` endpoint so a customer
or support engineer can see the whole picture — version, data store, probes,
retention, notification channels — without touching the command line.  Contains
no secrets (notification channels report only on/off, never hosts/URLs/tokens).
"""
from __future__ import annotations

import datetime
import os
import shutil
from typing import Any, Dict, List, Optional

from core.applog import HEALTH, PROCESS_START
from core.status import probe_fresh_window


def _int(v: Any, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def db_size_bytes(path: Optional[str]) -> Optional[int]:
    """Total on-disk size of the SQLite store, including the -wal/-shm sidecars."""
    if not path:
        return None
    total = 0
    found = False
    for suffix in ("", "-wal", "-shm"):
        try:
            total += os.path.getsize(path + suffix)
            found = True
        except OSError:
            pass
    return total if found else None


def human_size(n: Optional[int]) -> str:
    if not n:
        return "0 B" if n == 0 else "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for u in units:
        if size < 1024 or u == units[-1]:
            return f"{size:.0f} {u}" if u == "B" else f"{size:.1f} {u}"
        size /= 1024
    return f"{n} B"


def build_diagnostics(cfg, db, finder, public_base: str, version: str,
                      product: str, now: Optional[float] = None) -> Dict[str, Any]:
    now = datetime.datetime.now().timestamp() if now is None else now

    try:
        probes = list((finder.list_probes() or {}).values())
    except Exception:
        probes = []
    timeout = _int(cfg.get("probe_online_timeout_sec", 60), 60)

    probe_list: List[Dict[str, Any]] = []
    online = 0
    for p in probes:
        get = (lambda k, d=None: (p.get(k, d) if isinstance(p, dict) else getattr(p, k, d)))
        props = get("properties", {}) or {}
        pid = props.get("id") or get("probe_id") or get("name")
        last = get("last_seen")
        age = round(now - float(last), 1) if isinstance(last, (int, float)) else None
        is_online = age is not None and age <= timeout
        online += 1 if is_online else 0
        probe_list.append({"name": get("name"), "probe_id": pid, "ip": get("ip"),
                           "age_sec": age, "online": is_online})

    # Probes freshly REPORTING to the database — matches the dashboard's
    # "Connected Probes". A deep-sleep (or otherwise non-mDNS-visible) probe that
    # keeps posting still counts here even though it never appears in the mDNS
    # discovery list above, so this figure agrees with the dashboard/footer.
    reporting = None
    try:
        # Judge each probe against its OWN interval-aware freshness window — the
        # exact function the dashboard/footer use — so "reporting" here can never
        # disagree with the dashboard's "Connected Probes" for the same probe.
        epochs = db.last_reading_epoch_per_probe(window_seconds=None) or {}
        reporting = sum(1 for pid_, ep in epochs.items()
                        if pid_ and (now - float(ep)) <= probe_fresh_window(cfg, pid_))
    except Exception:
        reporting = None

    try:
        readings = db.count()
    except Exception:
        readings = None
    try:
        newest = (db.latest() or {}).get("timestamp")
    except Exception:
        newest = None

    notif = cfg.get("notifications", {}) or {}
    email = notif.get("email", {}) or {}
    webhook = notif.get("webhook", {}) or {}

    # --- System health: is the appliance actually recording, and is there room? --
    health = HEALTH.snapshot()
    db_path = getattr(db, "path", None)
    disk_free = None
    try:
        if db_path:
            disk_free = shutil.disk_usage(os.path.dirname(str(db_path)) or ".").free
    except OSError:
        disk_free = None
    try:
        readings_24h = db.window_stats(86400).get("count")
    except Exception:
        readings_24h = None

    return {
        "product": product,
        "version": version,
        "time": datetime.datetime.fromtimestamp(now).isoformat(timespec="seconds"),
        "server": {"base": public_base},
        "database": {
            "readings": readings,
            "size_bytes": db_size_bytes(getattr(db, "path", None)),
            "newest_reading": newest,
            },
        "probes": {"total": len(probe_list), "online": online,
                   "reporting": reporting, "list": probe_list},
        "health": {
            "healthy": health["healthy"],
            "uptime_sec": max(0, int(now - PROCESS_START)),
            "disk_free_bytes": disk_free,
            "readings_24h": readings_24h,
            "rows_written": health["rows_written"],
            "ingest_rejected": health["ingest_rejected"],
            "write_failures": health["write_failures"],
            "last_write_age_sec": health["last_write_age_sec"],
        },
        "retention_days": _int(cfg.get("retention_days", 0), 0),
        "notifications": {
            "enabled": bool(notif.get("enabled")),
            "email": bool(email.get("enabled")),
            "webhook": bool(webhook.get("enabled")),
            "offline_alerts": bool(notif.get("offline_alerts")),
        },
    }

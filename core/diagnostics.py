"""Build a single diagnostics snapshot of the running hub.

Used by the Diagnostics page and the ``/api/diagnostics`` endpoint so a customer
or support engineer can see the whole picture — version, data store, probes,
retention, notification channels — without touching the command line.  Contains
no secrets (notification channels report only on/off, never hosts/URLs/tokens).
"""
from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional


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

    return {
        "product": product,
        "version": version,
        "time": datetime.datetime.fromtimestamp(now).isoformat(timespec="seconds"),
        "server": {"base": public_base},
        "database": {
            "readings": readings,
            "size_bytes": db_size_bytes(getattr(db, "path", None)),
            "newest_reading": newest,
            "path": getattr(db, "path", None),
        },
        "probes": {"total": len(probe_list), "online": online, "list": probe_list},
        "retention_days": _int(cfg.get("retention_days", 0), 0),
        "notifications": {
            "enabled": bool(notif.get("enabled")),
            "email": bool(email.get("enabled")),
            "webhook": bool(webhook.get("enabled")),
            "offline_alerts": bool(notif.get("offline_alerts")),
        },
    }

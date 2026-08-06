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
from core.probes import discovered_probes
from core.status import (REPORTING_LOOKBACK_SEC, hub_health_window,
                         reporting_probe_ids)


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

    probes = discovered_probes(finder)
    timeout = _int(cfg.get("probe_online_timeout_sec", 60), 60)

    # Probes freshly REPORTING to the database — matches the dashboard's
    # "Connected Probes". Computed once, then overlaid on each per-probe row
    # below (mirroring the /api/probes overlay), so a deep-sleep probe that
    # keeps posting reads online even when mDNS last saw it minutes ago, and a
    # non-mDNS-visible probe still counts — this figure can never disagree with
    # the dashboard/footer, which use the same interval-aware helper.
    try:
        reporting_ids = reporting_probe_ids(cfg, db, now=now)
        reporting = len(reporting_ids)
    except Exception:
        reporting_ids, reporting = set(), None

    # The name the OPERATOR gave this probe, not the one the firmware announces.
    # The shipping firmware advertises its TXT `name` equal to the probe id, so
    # the Name column rendered the id a second time — two identical columns, and
    # no way to tell from this page which physical unit a row is. The point of
    # this snapshot is that someone can read it and act; "Setpoint-4B71E0 is
    # offline" and "Chest Freezer is offline" are not the same sentence. The id
    # column stays exactly as it is, because that is what support asks for.
    names = cfg.get("probe_names", {}) or {}

    def _label(pid, announced=""):
        return names.get(pid) or announced or pid

    probe_list: List[Dict[str, Any]] = []
    online = 0
    seen = set()
    for p in probes:
        pid = p["probe_id"] or p["name"]
        last = p["last_seen"]
        age = round(now - last, 1) if last is not None else None
        is_online = (age is not None and age <= timeout) or (pid in reporting_ids)
        online += 1 if is_online else 0
        if pid:
            seen.add(pid)
        probe_list.append({"name": _label(pid, p["name"]), "probe_id": pid,
                           "ip": p["ip"], "age_sec": age, "online": is_online})

    # Probes known only from ingest — a deep-sleep battery probe keeps its radio
    # off between readings, so it is never mDNS-discovered. The summary line
    # already counted them under "reporting", but the table below it did not list
    # them: a support engineer reading this snapshot saw "3 reporting" above a
    # table of one, with no way to tell which two were missing. /api/probes has
    # always appended them; this is the same overlay, on the same rule.
    for pid in sorted(reporting_ids - seen):
        probe_list.append({"name": _label(pid), "probe_id": pid, "ip": None,
                           "age_sec": None, "online": True, "source": "readings"})
        online += 1
        seen.add(pid)

    # ...and the probes that have STOPPED. Everything above lists only what is
    # currently fresh or currently visible over mDNS, so when a site went dark
    # the table emptied completely: "0 reporting · none discovered yet" above a
    # blank space, on the page whose entire purpose is that a customer can copy it
    # and send it to support. The page was least informative exactly when
    # something was wrong, and the one fact support needs first — WHICH probes
    # exist and when each was last heard from — was the fact it dropped.
    #
    # The reporting/online counts above are unchanged: these are listed as
    # offline, with their real age, which is the whole point.
    try:
        recent = db.last_reading_epoch_per_probe(window_seconds=REPORTING_LOOKBACK_SEC) or {}
    except Exception:  # noqa: BLE001 - a snapshot must never fail to render
        recent = {}
    for pid, epoch in sorted(recent.items()):
        if not pid or pid in seen:
            continue
        try:
            age = round(now - float(epoch), 1)
        except (TypeError, ValueError):
            age = None
        probe_list.append({"name": _label(pid), "probe_id": pid, "ip": None,
                           "age_sec": age, "online": False, "source": "readings"})

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
    # Interval-aware bound, not the flat 120 s default: a slow-cadence fleet
    # writes less often than that and would render "Needs attention" directly
    # above its own probe table showing those probes online.
    # A hub holding no readings at all is new, not broken — see
    # HealthState.snapshot's expect_data.
    health = HEALTH.snapshot(hub_health_window(cfg),
                             expect_data=bool(readings))
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
            "size_bytes": db_size_bytes(db_path),
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
            # HealthState documents this as surfaced here; it wasn't. A probe on
            # a stale device token 401s on every wake and is otherwise
            # indistinguishable from "hub down".
            "unauthorized": health["unauthorized"],
            "last_unauthorized_age_sec": health["last_unauthorized_age_sec"],
        },
        "retention_days": _int(cfg.get("retention_days", 0), 0),
        "notifications": {
            "enabled": bool(notif.get("enabled")),
            "email": bool(email.get("enabled")),
            "webhook": bool(webhook.get("enabled")),
            "offline_alerts": bool(notif.get("offline_alerts")),
            # Whether alerts are configured is not the same question as whether
            # they are ARRIVING. A dead SMTP server leaves every flag above true
            # while nothing reaches anyone, so report delivery beside intent.
            "failed": health["notify_failures"],
            "dropped": health["notify_dropped"],
            "last_failure_age_sec": health["last_notify_failure_age_sec"],
        },
        # Multi-site forwarding. Same principle as notifications above: whether
        # it is CONFIGURED is a different question from whether readings are
        # ARRIVING, and "head office can't see my store" is the support ticket
        # this has to answer. `pending` climbing with a `last_error` set is the
        # whole diagnosis. The token is deliberately absent — this blob is meant
        # to be pasted into an email.
        "upstream": _upstream_diag(cfg, now),
    }


def _upstream_diag(cfg, now: float) -> Dict[str, Any]:
    up = cfg.get("upstream", {}) or {}
    out: Dict[str, Any] = {
        "enabled": bool(up.get("enabled")),
        "url": str(up.get("url") or ""),
        "site": str(up.get("site") or ""),
        "interval_sec": _int(up.get("interval_sec", 30), 30),
    }
    if not out["enabled"]:
        return out
    try:
        from core.forwarder import FORWARDER
        st = FORWARDER.status()
        out["pending"] = st["pending"]
        out["last_send_age_sec"] = (round(now - st["last_sent_epoch"], 1)
                                    if st["last_sent_epoch"] else None)
        out["last_error"] = st["last_error"]
    except Exception:  # noqa: BLE001 - diagnostics must never raise
        pass
    return out

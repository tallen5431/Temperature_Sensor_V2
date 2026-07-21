"""Live hub status, derived from the discovery list and the database.

Pure and side-effect free so it can be unit-tested without a UI or network.
The Dash footer maps the returned state to display text/colour.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable

# A probe counts as "connected" if seen within this many seconds (mDNS default).
ONLINE_TIMEOUT_SEC = 60

# A probe is "fresh" until it has been silent for this many times its own
# reporting interval — so a deep-sleep probe that wakes every few minutes is not
# flagged stale between wakes.
STALE_INTERVAL_MULTIPLIER = 2.5

# Fallback offline threshold, matching alert_monitor's ``offline_after_sec``
# default (5 min). Shared by the dashboard, footer, Devices grid and Diagnostics
# so every surface agrees on when a probe is "offline".
OFFLINE_AFTER_SEC = 300


def probe_fresh_window(cfg, probe_id) -> float:
    """Seconds a probe may be silent before it counts as stale/offline.

    The larger of: the configured online timeout, the alert monitor's offline
    threshold (so the dashboard and the alerting engine agree on "offline"), and
    ~2.5x this probe's reporting interval (so a slow deep-sleep cadence doesn't
    read as offline between wakes). The 5-min floor means a typical battery probe
    counts as connected out of the box, with no per-probe configuration.

    This is the single source of truth for "is this probe fresh?" — the dashboard
    KPI/cards/alerts, the footer, the Devices grid and the Diagnostics page all
    call it so they can never disagree on the same screen.
    """
    base = ONLINE_TIMEOUT_SEC
    for key, default in (("probe_online_timeout_sec", ONLINE_TIMEOUT_SEC),
                         ("offline_after_sec", OFFLINE_AFTER_SEC)):
        try:
            base = max(base, int(cfg.get(key, default) or default))
        except (TypeError, ValueError):
            pass
    try:
        intervals = cfg.get("probe_intervals", {}) or {}
        interval = float(intervals.get(probe_id, cfg.get("interval_sec", 5) or 5))
    except (TypeError, ValueError):
        interval = 5.0
    return max(base, interval * STALE_INTERVAL_MULTIPLIER)


def reporting_probe_ids(cfg, db, now: float | None = None) -> set:
    """Set of probe ids whose most recent DB reading is within their own fresh
    window (see :func:`probe_fresh_window`).

    This is the single source of truth for "which probes are currently
    reporting". The dashboard's "Connected Probes" KPI, the Diagnostics page,
    the ``/api/probes`` + ``/api/health`` online counts and the Prometheus
    ``/metrics`` gauges all derive from it, so no surface can disagree with the
    others for the same probe — a deep-sleep probe on a slow cadence reads
    connected on every screen or none. Judged off ingest (the database), not
    mDNS, so a probe whose radio sleeps between readings still counts.
    Returns an empty set if the store can't be read.
    """
    now = time.time() if now is None else now
    try:
        epochs = db.last_reading_epoch_per_probe(window_seconds=None) or {}
    except Exception:
        return set()
    out = set()
    for pid, ep in epochs.items():
        if not pid:
            continue
        try:
            if (now - float(ep)) <= probe_fresh_window(cfg, pid):
                out.add(pid)
        except (TypeError, ValueError):
            continue
    return out


def hub_status(probes: Iterable[Any], online_timeout: float,
               total_readings: int, now: float | None = None,
               reporting_online: int = 0) -> Dict[str, Any]:
    """Summarise hub health.

    Returns ``{"state", "online", "total", "readings"}`` where ``state`` is one of:
      * ``"online"``  — at least one probe reported within ``online_timeout`` seconds
      * ``"offline"`` — probes are known but all have gone quiet
      * ``"idle"``    — no probes known, but readings exist (probe was here, now gone)
      * ``"waiting"`` — fresh install, nothing has ever reported

    ``reporting_online`` is the count of probes freshly reporting to the database
    (the dashboard's own "Connected Probes" figure). A probe that is posting but
    is **not** mDNS-visible — a deep-sleep battery probe, or loaded demo data —
    still counts as online, so the footer agrees with the dashboard instead of
    reading "idle" while the dashboard shows live probes.
    """
    now = time.time() if now is None else now
    total = 0
    online = 0
    for p in probes:
        total += 1
        last = p.get("last_seen") if isinstance(p, dict) else getattr(p, "last_seen", None)
        if isinstance(last, (int, float)) and (now - float(last)) <= online_timeout:
            online += 1

    reporting_online = max(int(reporting_online or 0), 0)
    online = max(online, reporting_online)
    total = max(total, reporting_online)

    if online:
        state = "online"
    elif total:
        state = "offline"
    elif total_readings:
        state = "idle"
    else:
        state = "waiting"
    return {"state": state, "online": online, "total": total, "readings": int(total_readings)}

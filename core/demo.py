"""Demo data — let a new user explore the dashboard before any real probe exists.

Seeds a day of realistic readings for a couple of clearly-labelled DEMO probes,
and clears them again. Demo probe ids are prefixed ``DEMO-`` so they are easy to
identify, filter, and remove without ever touching real data.
"""
from __future__ import annotations

import datetime
import math
from core.units import c_to_f

DEMO_PREFIX = "DEMO-"

# Each demo probe carries the alarm range a real one in that role would be held
# to. Without them the demo showed two probes reading normally and nothing
# checking either — no alarm range on the Devices cards, and (since the hub
# stopped calling an unwatched probe "OK") two grey "no alarm set" badges as the
# first thing anyone saw. Thresholds make the demo show the product instead of a
# thermometer: the range, a green OK earned against it, and the alerting the hub
# exists for. ``clear_demo_data`` strips them again with everything else DEMO-.
_DEMO_PROBES = {
    # The swing is deliberately inside the band. At ±1.2 the fridge crossed 5 °C
    # twice a cycle, so the demo chart showed a line poking over its own limit
    # with no event recorded against it (the monitor only ever evaluates the
    # newest reading) — which reads as alerting that missed an excursion.
    "DEMO-Fridge": {"name": "Demo Fridge", "base": 4.0, "amp": 0.8,
                    "min": 1.0, "max": 5.0},          # food-safe fridge band
    "DEMO-Room":   {"name": "Demo Room",   "base": 21.5, "amp": 1.8,
                    "min": 18.0, "max": 25.0},        # comfortable room
}


def has_demo_data(db) -> bool:
    """True if any demo probe currently has readings in the store."""
    try:
        # O(log N) index probe — this runs on every settings render, so it must
        # not scan/group the whole readings table just to answer yes/no.
        return bool(db.has_probe_prefix(DEMO_PREFIX))
    except Exception:
        pass  # older Database without the helper — fall back to the full scan
    try:
        return any(str(pid).startswith(DEMO_PREFIX)
                   for pid in db.last_reading_epoch_per_probe().keys())
    except Exception:
        return False


def load_demo_data(db, cfg, hours: int = 24, step_min: int = 5) -> int:
    """Seed ~``hours`` of readings for the demo probes. Returns rows inserted."""
    now = datetime.datetime.now().replace(microsecond=0)
    n_points = max(1, int(hours * 60 / step_min))
    rows = 0
    names = dict(cfg.get("probe_names", {}) or {})
    thresholds = dict(cfg.get("alert_thresholds", {}) or {})
    for pid, spec in _DEMO_PROBES.items():
        for i in range(n_points):
            # newest point lands at ~now so demo probes read as live, not stale
            t = now - datetime.timedelta(minutes=(n_points - 1 - i) * step_min)
            c = spec["base"] + spec["amp"] * math.sin(i / 12.0)
            db.append(t.isoformat(timespec="seconds"), round(c, 2),
                      round(c_to_f(c), 2), pid)
            rows += 1
        names[pid] = spec["name"]
        thresholds[pid] = {"min": spec["min"], "max": spec["max"]}
    cfg.update({"probe_names": names, "alert_thresholds": thresholds})
    return rows


def clear_demo_data(db, cfg) -> int:
    """Delete every demo probe's readings and config metadata. Returns rows removed."""
    from core.config_schema import _DICTS
    ids = set(_DEMO_PROBES.keys())
    try:
        ids |= {pid for pid in db.last_reading_epoch_per_probe().keys()
                if str(pid).startswith(DEMO_PREFIX)}
    except Exception:
        pass
    from core.metrics import LATEST
    removed = 0
    for pid in ids:
        try:
            removed += db.delete_probe(pid)
        except Exception:
            pass
        # Keep the Prometheus latest-reading registry in step so a cleared demo
        # probe doesn't linger as a frozen /metrics series.
        try:
            LATEST.evict(pid)
        except Exception:
            pass
    for key in _DICTS:
        d = dict(cfg.get(key, {}) or {})
        if any(str(pid).startswith(DEMO_PREFIX) for pid in d):
            for pid in [p for p in d if str(p).startswith(DEMO_PREFIX)]:
                d.pop(pid, None)
            cfg.update({key: d})
    return removed

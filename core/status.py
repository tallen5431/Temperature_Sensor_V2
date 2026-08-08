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

# Bound the per-probe "last reading" GROUP BY behind :func:`reporting_probe_ids`
# to the last week. Any probe silent longer than this is unambiguously not
# reporting (fresh windows top out at minutes, not days), and the cutoff keeps
# the query cost tracking recent rows instead of the entire retained history.
REPORTING_LOOKBACK_SEC = 7 * 86400


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


def limits_for(cfg, probe_id, site: str = "") -> Dict[str, Any]:
    """The limits THIS hub may judge ``probe_id`` by — the one resolution rule.

    Two things were being got wrong independently, in two places each.

    **The ``default`` fallback.** The alert engine resolves a probe's limits as
    "its own entry, else ``default``" (:func:`core.alerts.threshold_for`). The
    Dashboard card did the same; the Devices card looked up the per-probe entry
    only. So on a hub configured with a ``default``, one page showed "▼ LOW" and
    the other said "Alarm range not set" — for the same probe, at the same
    moment, and the Devices answer was the dangerous direction: it reads as "this
    probe is unmonitored" about a probe that will absolutely alarm.

    **Forwarded probes.** A reading carrying a ``site`` label came from another
    hub, and thresholds are per hub and are not forwarded. Judging it by THIS
    hub's limits is not a near miss, it is a different question: head office
    running fridges (0..8 C) rendered every healthy store freezer at -19 C as
    "▼ LOW" on its dashboard. There is nothing to fall back to, so the honest
    answer is no limits — the store hub judges its own probes and forwards the
    events, which is what head office should be showing.

    Returns a ``{min, max}``-shaped dict, empty when this hub cannot judge.
    """
    if site:
        return {}
    thresholds = (cfg.get("alert_thresholds", {}) if hasattr(cfg, "get") else {}) or {}
    return (thresholds.get(probe_id) or thresholds.get("default") or {}) if thresholds else {}


def probe_state(temp_c, thresholds, *, stale: bool = False,
                held=None, watched=None) -> Dict[str, Any]:
    """One verdict on "how is this probe doing?", shared by every surface.

    The Dashboard cards and the Devices grid each derived this independently and
    reached OPPOSITE answers for the same probe. Given a probe that is both in
    breach and silent, the Dashboard tested staleness first and rendered a grey
    "stale" (dropping the alarm); the Devices grid tested the breach first and
    rendered a red "ALARM" (dropping the silence). So one page showed a calm grey
    card and the other a red one, for one probe, at the same moment.

    That combination is the most urgent state this product has: the temperature
    went wrong *and* you have lost sight of it. Neither page reported it in full,
    and the reading either page displayed was hours old with nothing saying so.

    Both facts are independent, so both are returned:

    ``alarm``    ``'high'``/``'low'`` when the probe is outside its limits — from
                 the raw reading, or from ``held`` when some authority other than
                 this reading says so. Two things use that: the local monitor's
                 hysteresis deadband (back inside the limit but not yet cleared
                 by it), and a forwarded verdict on a multi-site hub, where the
                 store that owns the probe has judged it and head office has not
                 got the thresholds to.
    ``stale``    the caller's freshness verdict, passed straight through so this
                 stays pure (see :func:`probe_fresh_window` for the rule).
    ``watched``  whether anything is checking this probe. Derived from the limits
                 unless the caller overrides it — head office holds no limits for
                 a forwarded probe, but the store that sent it does, so "no limit
                 here" is not "nobody is watching".
    ``severity`` the worst of the above, for colour. A breach is ``danger`` even
                 when the probe has also gone silent; silent-or-unwatched is
                 ``secondary`` (both mean "this hub does not know"), and only a
                 fresh reading inside limits it is actually being held to earns
                 ``success``.

    Rendering stays with each surface — the two pages speak deliberately
    different vocabularies ("▲ HIGH" vs "ALARM") — but they can no longer
    disagree about the facts underneath.
    """
    lo = (thresholds or {}).get("min")
    hi = (thresholds or {}).get("max")
    watched = (lo is not None or hi is not None) if watched is None else bool(watched)
    alarm = None
    if temp_c is not None:
        try:
            if hi is not None and float(temp_c) > float(hi):
                alarm = "high"
            elif lo is not None and float(temp_c) < float(lo):
                alarm = "low"
        except (TypeError, ValueError):
            alarm = None
    if alarm is None and held in ("high", "low"):
        alarm = held
    if alarm is not None:
        severity = "danger"
    elif stale or not watched:
        severity = "secondary"
    else:
        severity = "success"
    return {"alarm": alarm, "stale": bool(stale), "watched": watched,
            "severity": severity}


def reporting_probe_ids(cfg, db, now: float | None = None,
                        site: str | None = None) -> set:
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

    ``site`` narrows the *input set* to one forwarding store, for the dashboard's
    KPI while a store is selected — the freshness rule itself is unchanged, so a
    narrowed count still agrees probe-for-probe with every other surface. Every
    machine-facing caller (``/metrics``, ``/api/health``) leaves it ``None``: a
    scraper wants the whole hub, not whatever a browser tab happens to show.
    """
    now = time.time() if now is None else now
    # The site kwarg is passed ONLY when a site is actually selected, so the call
    # every existing caller makes is byte-for-byte what it always was — a stand-in
    # db (tests, /metrics' cached wrapper) needn't grow a parameter it never uses.
    extra = {} if site is None else {"site": site}
    try:
        epochs = db.last_reading_epoch_per_probe(
            window_seconds=REPORTING_LOOKBACK_SEC, **extra) or {}
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


def hub_health_window(cfg) -> float:
    """Seconds the newest successful write may age before the hub reads unhealthy.

    ``HealthState.snapshot`` defaults to a flat 120 s, and its docstring invites
    callers "monitoring slow-cadence probes" to pass an interval-aware bound
    instead — but no caller did, so a deep-sleep deployment permanently
    contradicted itself. One probe on a 600 s cadence writes once per 600 s, so
    ``healthy`` was true for 120 s of every 600 and false for the other 480: the
    Diagnostics page rendered "Needs attention" directly above its own probe
    table listing that same probe "online", ``/api/health`` reported
    ``healthy:false``, and ``setpoint_healthy`` flapped 1→0→1 on every scrape,
    which is precisely the metric a Grafana alert would be wired to.

    Same shape as :func:`probe_prune_window`: the configured floor, widened to
    the slowest probe's own fresh window. A fast fleet keeps 120 s
    responsiveness; a slow one stops crying wolf.
    """
    try:
        base = float(cfg.get("health_fresh_sec", 120) or 120)
    except (TypeError, ValueError):
        base = 120.0
    try:
        windows = [probe_fresh_window(cfg, pid)
                   for pid in ((cfg.get("probe_intervals") or {}).keys())]
        windows.append(probe_fresh_window(cfg, None))
        return max(base, max(windows))
    except Exception:  # noqa: BLE001 - config is user-editable; never break health
        return base


def probe_prune_window(cfg) -> float:
    """Seconds a probe may be unseen before discovery may evict it.

    Single source of truth shared by BOTH pruners — the auto-provisioner's cycle
    and the alert monitor's hourly sweep. They must agree: a deep-sleeping probe
    answers mDNS only during its brief wake, so its discovery entry is kept alive
    almost entirely by the last_seen stamped on each ingest. If either pruner
    used the flat ``probe_prune_after_sec`` default, a probe reporting at or
    beyond that cadence would be evicted BETWEEN posts — dropping off the Devices
    grid and churning the provisioner's bookkeeping — even though the other
    pruner was correctly protecting it.

    The floor is the configured value; the effective window is at least twice the
    slowest probe's own fresh window.
    """
    try:
        base = int(cfg.get("probe_prune_after_sec", 3600) or 3600)
    except (TypeError, ValueError):
        base = 3600
    try:
        windows = [probe_fresh_window(cfg, pid)
                   for pid in ((cfg.get("probe_intervals") or {}).keys())]
        windows.append(probe_fresh_window(cfg, None))
        return max(base, max(windows) * 2)
    except Exception:  # noqa: BLE001 - config is user-editable; never break pruning
        return base

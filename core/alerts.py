"""Threshold alert evaluation — pure logic, no I/O.

Kept free of Dash/SMTP/DB specifics so the state machine can be unit-tested in
isolation.  The background :class:`alert_monitor.AlertMonitor` feeds it the
latest reading per probe and dispatches the returned events to notification
channels.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple


def threshold_for(thresholds: dict, probe_id: str) -> dict:
    """Return the threshold config for a probe, falling back to 'default'."""
    return (thresholds.get(probe_id) or thresholds.get("default") or {}) if thresholds else {}


def classify(temp_c: float, thr: dict) -> Tuple[str, Optional[float]]:
    """Classify a reading as 'high', 'low', or 'ok' against a threshold dict.

    Returns ``(condition, limit)`` where ``limit`` is the breached threshold
    value (or None when ok).
    """
    hi = thr.get("max")
    lo = thr.get("min")
    if hi is not None and temp_c > hi:
        return "high", hi
    if lo is not None and temp_c < lo:
        return "low", lo
    return "ok", None


def _event(probe_id: str, kind: str, temp_c: float, limit: Optional[float],
           prev_condition: Optional[str] = None) -> dict:
    return {"probe_id": probe_id, "kind": kind, "temperature_c": temp_c,
            "limit": limit, "prev_condition": prev_condition}


def evaluate(readings: Dict[str, float], thresholds: dict, states: dict,
             now: Optional[float] = None, cooldown_sec: int = 1800,
             notify_recovery: bool = True) -> Tuple[List[dict], dict]:
    """Compare the latest reading per probe to thresholds and detect events.

    Parameters
    ----------
    readings : ``{probe_id: latest_temperature_c}``
    thresholds : per-probe ``{min, max}`` (with optional ``default``)
    states : previous per-probe state ``{condition, last_notified}``
    cooldown_sec : minimum seconds between repeat notifications while a probe
        stays in breach (so a sustained problem reminds you without spamming)
    notify_recovery : emit a 'recovery' event when a probe returns to normal

    Returns ``(events, new_states)``.  ``events`` only contains transitions and
    cooldown reminders — never one per poll.
    """
    now = now if now is not None else time.time()
    new_states = dict(states)
    events: List[dict] = []

    for probe_id, temp_c in readings.items():
        thr = threshold_for(thresholds, probe_id)
        cond, limit = classify(temp_c, thr)
        prev = states.get(probe_id, {"condition": "ok", "last_notified": 0.0})
        prev_cond = prev.get("condition", "ok")

        if cond in ("high", "low"):
            transitioned = cond != prev_cond
            cooled_down = (now - prev.get("last_notified", 0.0)) >= cooldown_sec
            if transitioned or cooled_down:
                events.append(_event(probe_id, cond, temp_c, limit))
                new_states[probe_id] = {"condition": cond, "last_notified": now}
            else:
                new_states[probe_id] = prev
        else:  # ok
            if prev_cond in ("high", "low") and notify_recovery:
                events.append(_event(probe_id, "recovery", temp_c, None, prev_condition=prev_cond))
            new_states[probe_id] = {"condition": "ok", "last_notified": 0.0}

    return events, new_states


def evaluate_offline(last_epochs: Dict[str, int], states: dict,
                     now: Optional[float] = None, offline_after_sec: int = 300) -> Tuple[List[dict], dict]:
    """Detect probes that have stopped (or resumed) reporting.

    Parameters
    ----------
    last_epochs : ``{probe_id: epoch_of_latest_reading}`` for currently-tracked probes
    states : previous per-probe ``"online"``/``"offline"`` string
    offline_after_sec : a probe silent longer than this is considered offline

    Returns ``(events, new_states)``.  Probes absent from ``last_epochs`` (e.g.
    aged out of the tracking window) are dropped from the returned states.
    """
    now = now if now is not None else time.time()
    new_states: dict = {}
    events: List[dict] = []
    for probe_id, last_epoch in last_epochs.items():
        age = now - last_epoch
        cond = "offline" if age > offline_after_sec else "online"
        prev = states.get(probe_id, "online")
        if cond != prev:
            events.append({"probe_id": probe_id, "kind": cond, "age_sec": int(age)})
        new_states[probe_id] = cond
    return events, new_states


def format_event(event: dict, names: Optional[dict] = None) -> Tuple[str, str]:
    """Build a human (subject, message) pair for an event.

    ``names`` maps probe_id -> friendly name (optional).
    """
    names = names or {}
    pid = event["probe_id"]
    label = names.get(pid, pid)
    kind = event["kind"]
    limit = event.get("limit")

    # Connectivity events carry no temperature.
    if kind == "offline":
        mins = max(1, int(event.get("age_sec", 0)) // 60)
        return (f"⚠️ {label}: OFFLINE (silent {mins} min)",
                f"{label} has stopped reporting — no readings for {mins} minute(s).")
    if kind == "online":
        return (f"✅ {label}: back online",
                f"{label} is reporting again.")

    c = event["temperature_c"]
    f = (c * 9.0 / 5.0) + 32.0
    reading = f"{c:.1f}°C / {f:.1f}°F"
    if kind == "high":
        return (f"⚠️ {label}: temperature HIGH ({reading})",
                f"{label} is {reading}, above the {limit:.1f}°C maximum threshold.")
    if kind == "low":
        return (f"❄️ {label}: temperature LOW ({reading})",
                f"{label} is {reading}, below the {limit:.1f}°C minimum threshold.")
    if kind == "recovery":
        return (f"✅ {label}: temperature back to normal ({reading})",
                f"{label} has returned to normal and is now {reading}.")
    return f"{label}: {reading}", f"{label} is {reading}."

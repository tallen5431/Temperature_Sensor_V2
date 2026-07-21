"""Threshold alert evaluation — pure logic, no I/O.

Kept free of Dash/SMTP/DB specifics so the state machine can be unit-tested in
isolation.  The background :class:`alert_monitor.AlertMonitor` feeds it the
latest reading per probe and dispatches the returned events to notification
channels.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional, Tuple, Union


class HeldStates:
    """Registry of probes currently held in a threshold condition.

    The background :class:`alert_monitor.AlertMonitor` owns the hysteresis
    state machine, but the dashboard needs to know when a probe's alert banner
    should stay up even though the raw reading is back inside the limit (the
    deadband hold).  This tiny thread-safe map keeps the two in agreement
    without the UI re-deriving alert state.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: Dict[str, str] = {}

    def set_states(self, states: Dict[str, str]) -> None:
        """Replace the registry with the probes currently held in breach.

        Entries whose value is not ``'high'``/``'low'`` are dropped, and probes
        absent from ``states`` (cleared breaches) are forgotten.
        """
        with self._lock:
            self._states = {str(pid): cond for pid, cond in (states or {}).items()
                            if cond in ("high", "low")}

    def get(self, probe_id) -> Optional[str]:
        """Return ``'high'``/``'low'`` while the probe is held in breach, else None."""
        with self._lock:
            return self._states.get(probe_id)


# Process-wide instance: the AlertMonitor updates it every cycle, the dashboard
# reads it (``from core.alerts import HELD``).
HELD = HeldStates()


def threshold_for(thresholds: dict, probe_id: str) -> dict:
    """Return the threshold config for a probe, falling back to 'default'."""
    return (thresholds.get(probe_id) or thresholds.get("default") or {}) if thresholds else {}


def classify(temp_c: float, thr: dict, prev_condition: str = "ok",
             hysteresis: float = 0.0) -> Tuple[str, Optional[float]]:
    """Classify a reading as 'high', 'low', or 'ok' against a threshold dict.

    ``hysteresis`` is a deadband in °C that damps a noisy sensor sitting right on
    a limit: once a probe is in breach it must move back *inside* the limit by
    ``hysteresis`` before it clears, so it won't flap high→ok→high every reading.
    Entering a breach always uses the raw threshold; ``prev_condition`` is the
    probe's last condition ('ok'/'high'/'low').

    Returns ``(condition, limit)`` where ``limit`` is the breached threshold
    value (or None when ok).
    """
    hi = thr.get("max")
    lo = thr.get("min")
    h = max(0.0, float(hysteresis or 0.0))
    # Hold an existing breach until the reading clears the limit by the deadband.
    if prev_condition == "high" and hi is not None and temp_c > hi - h:
        return "high", hi
    if prev_condition == "low" and lo is not None and temp_c < lo + h:
        return "low", lo
    if hi is not None and temp_c > hi:
        return "high", hi
    if lo is not None and temp_c < lo:
        return "low", lo
    return "ok", None


def _event(probe_id: str, kind: str, temp_c: float, limit: Optional[float],
           prev_condition: Optional[str] = None, transition: bool = True) -> dict:
    # ``transition`` is False for cooldown reminders, so consumers (the event
    # log) can tell a new incident from a repeat of an ongoing one.
    return {"probe_id": probe_id, "kind": kind, "temperature_c": temp_c,
            "limit": limit, "prev_condition": prev_condition, "transition": transition}


def evaluate(readings: Dict[str, float], thresholds: dict, states: dict,
             now: Optional[float] = None, cooldown_sec: int = 1800,
             notify_recovery: bool = True, hysteresis: float = 0.0) -> Tuple[List[dict], dict]:
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
        prev = states.get(probe_id, {"condition": "ok", "last_notified": 0.0})
        prev_cond = prev.get("condition", "ok")
        cond, limit = classify(temp_c, thr, prev_condition=prev_cond, hysteresis=hysteresis)

        if cond in ("high", "low"):
            transitioned = cond != prev_cond
            cooled_down = (now - prev.get("last_notified", 0.0)) >= cooldown_sec
            if transitioned or cooled_down:
                events.append(_event(probe_id, cond, temp_c, limit, transition=transitioned))
                new_states[probe_id] = {"condition": cond, "last_notified": now}
            else:
                new_states[probe_id] = prev
        else:  # ok
            if prev_cond in ("high", "low") and notify_recovery:
                events.append(_event(probe_id, "recovery", temp_c, None, prev_condition=prev_cond))
            new_states[probe_id] = {"condition": "ok", "last_notified": 0.0}

    return events, new_states


def evaluate_offline(last_epochs: Dict[str, int], states: dict,
                     now: Optional[float] = None,
                     offline_after_sec: Union[float, Dict[str, float]] = 300) -> Tuple[List[dict], dict]:
    """Detect probes that have stopped (or resumed) reporting.

    Parameters
    ----------
    last_epochs : ``{probe_id: epoch_of_latest_reading}`` for currently-tracked probes
    states : previous per-probe ``"online"``/``"offline"`` string
    offline_after_sec : silence threshold in seconds — either one number applied
        to every probe, or a ``{probe_id: seconds}`` mapping so each probe is
        judged against its own window (e.g. ``core.status.probe_fresh_window``,
        which scales with a probe's reporting interval).  Probes missing from
        the mapping fall back to 300 s.

    Returns ``(events, new_states)``.  Probes absent from ``last_epochs`` (e.g.
    aged out of the tracking window) are dropped from the returned states.
    """
    now = now if now is not None else time.time()
    per_probe = offline_after_sec if isinstance(offline_after_sec, dict) else None
    new_states: dict = {}
    events: List[dict] = []
    for probe_id, last_epoch in last_epochs.items():
        threshold = per_probe.get(probe_id, 300) if per_probe is not None else offline_after_sec
        age = now - last_epoch
        cond = "offline" if age > threshold else "online"
        prev = states.get(probe_id, "online")
        if cond != prev:
            events.append({"probe_id": probe_id, "kind": cond, "age_sec": int(age)})
        new_states[probe_id] = cond
    return events, new_states


def evaluate_rate(pairs: Dict[str, Tuple[float, float]], rate_limit_c: float,
                  window_min: int, states: dict, now: Optional[float] = None,
                  cooldown_sec: int = 1800) -> Tuple[List[dict], dict]:
    """Detect probes whose temperature is changing too fast.

    A freezer door left open shows up as a rapid rise long before the absolute
    threshold trips — this catches the slope, not the level.

    Parameters
    ----------
    pairs : ``{probe_id: (latest_c, past_c)}`` where ``past_c`` is the reading
        closest to ``window_min`` minutes ago
    rate_limit_c : trigger when ``abs(latest - past)`` meets/exceeds this many
        °C; 0 (or less) disables the check entirely
    window_min : the span the pair covers, carried into the event for wording
    states : previous per-probe ``{condition, last_notified}`` (same shape as
        :func:`evaluate`'s states)
    cooldown_sec : minimum seconds between repeat notifications while the rate
        stays excessive

    Returns ``(events, new_states)``.  Events carry ``kind='rate'`` plus
    ``delta_c`` (signed) and ``window_min``.
    """
    now = now if now is not None else time.time()
    if not rate_limit_c or rate_limit_c <= 0:
        return [], {}
    new_states = dict(states)
    events: List[dict] = []
    for probe_id, (latest_c, past_c) in pairs.items():
        delta = latest_c - past_c
        prev = states.get(probe_id, {"condition": "ok", "last_notified": 0.0})
        prev_cond = prev.get("condition", "ok")
        if abs(delta) >= rate_limit_c:
            transitioned = prev_cond != "rate"
            cooled_down = (now - prev.get("last_notified", 0.0)) >= cooldown_sec
            if transitioned or cooled_down:
                events.append({"probe_id": probe_id, "kind": "rate",
                               "temperature_c": latest_c, "limit": rate_limit_c,
                               "delta_c": delta, "window_min": int(window_min),
                               "transition": transitioned})
                new_states[probe_id] = {"condition": "rate", "last_notified": now}
            else:
                new_states[probe_id] = prev
        else:
            new_states[probe_id] = {"condition": "ok", "last_notified": 0.0}
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
    if kind == "rate":
        delta = float(event.get("delta_c", 0.0))
        mins = int(event.get("window_min", 0) or 0)
        change = f"{'rose' if delta >= 0 else 'fell'} {abs(delta):.1f} °C in {mins} min"
        return (f"{label}: temperature {change}",
                f"{label} {change} and is now {reading}.")
    # A cooldown reminder can fire while a breach is HELD by the hysteresis
    # deadband: the reading is back inside the raw limit but has not cleared it
    # by the deadband, so claiming it is "above the maximum" would be false.
    if kind == "high":
        if limit is not None and c <= limit:
            return (f"{label}: temperature still HIGH ({reading})",
                    f"{label} is {reading} — back at or below the {limit:.1f}°C maximum, "
                    f"but it has not yet cleared the limit by the alert deadband.")
        return (f"⚠️ {label}: temperature HIGH ({reading})",
                f"{label} is {reading}, above the {limit:.1f}°C maximum threshold.")
    if kind == "low":
        if limit is not None and c >= limit:
            return (f"{label}: temperature still LOW ({reading})",
                    f"{label} is {reading} — back at or above the {limit:.1f}°C minimum, "
                    f"but it has not yet cleared the limit by the alert deadband.")
        return (f"❄️ {label}: temperature LOW ({reading})",
                f"{label} is {reading}, below the {limit:.1f}°C minimum threshold.")
    if kind == "recovery":
        return (f"✅ {label}: temperature back to normal ({reading})",
                f"{label} has returned to normal and is now {reading}.")
    return f"{label}: {reading}", f"{label} is {reading}."

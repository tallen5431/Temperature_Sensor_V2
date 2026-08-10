"""Threshold alert evaluation — pure logic, no I/O.

Kept free of Dash/SMTP/DB specifics so the state machine can be unit-tested in
isolation.  The background :class:`alert_monitor.AlertMonitor` feeds it the
latest reading per probe and dispatches the returned events to notification
channels.
"""
from __future__ import annotations

import datetime
import threading
import time
from typing import Dict, List, Optional, Tuple, Union
from core.units import c_to_f


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


def find_missed_excursions(rows, thr: dict, probe_id: str = "",
                           hysteresis: float = 0.0, state: Optional[dict] = None,
                           live_open: bool = False) -> List[dict]:
    """Excursions that came and went without the live evaluator ever seeing one.

    :func:`evaluate` judges the LATEST reading per probe, once per monitor cycle.
    Anything that breaches and recovers between two of those looks at ends like
    nothing happened — and the readings themselves are in the database the whole
    time, drawn on the chart, with no event and no alert beside them.

    That is not a rare corner. It is exactly what a hub outage produces: a probe
    with the threshold watch armed buffers every sample to flash while the hub is
    unreachable, then flushes the lot on reconnect. A freezer that failed and
    recovered inside that window arrives as history. The watch exists so an
    excursion between reports is not missed; storing it and never looking at it
    gives that back.

    ``rows`` is ``[(epoch, temperature_c), ...]`` ascending, for one probe. A run
    touching the LAST row is deliberately not reported: that breach is still open,
    so it belongs to :func:`evaluate`, which owns the cooldown and deadband state
    for it. Only closed runs — ones that recovered before the newest reading —
    are returned, so the two can never both report the same incident.

    ``state`` is an optional per-probe dict CARRIED BETWEEN CALLS, and it is what
    makes that promise hold across more than one batch. The caller sweeps rows in
    arrival order, a chunk per cycle, so a breach open at the end of one chunk
    resumes at the start of the next. Without carried state each call restarted
    at ``prev_condition="ok"``: the deadband was re-armed mid-excursion, and the
    run reappeared as brand new. The caller passes the same dict back each cycle;
    this function reads ``state["condition"]`` on entry and writes the batch's
    trailing condition to it on exit. Omit it and the behaviour is the
    single-batch one.

    ``live_open`` is the OTHER half, and the two are not interchangeable. A run
    carried in from the previous batch is only :func:`evaluate`'s to report if
    evaluate is actually holding a breach for this probe — which is what
    ``live_open`` says. Suppressing on the carry alone loses real incidents: a
    probe flushing a buffered outage sends readings that are OLD, the monitor's
    freshness filter keeps them out of :func:`evaluate` entirely, and a long
    enough excursion spans two sweeps. Nobody would ever have reported it.

    Each run collapses to ONE event: 13 minutes at a 7 s cadence is 110 readings
    and one problem.
    """
    out: List[dict] = []

    def _emit(finished: dict) -> None:
        # A run that was ALREADY open when this batch began AND that the live
        # engine is holding a breach for is evaluate()'s incident: it alerted it
        # last cycle and will emit the recovery. Reporting it here too would
        # send a second, contradictory message — "while the hub was not
        # watching" about an excursion the hub watched — and file a phantom row
        # in the durable event log.
        #
        # Both halves are required. Carried-in alone is not enough: backfilled
        # readings are old, so the monitor's freshness filter keeps them out of
        # evaluate() altogether, and an excursion long enough to span two
        # sweeps would be dropped here having never been reported anywhere.
        if finished.pop("carried", False):
            return
        out.append(finished)

    run = None
    ordered = sorted((r for r in rows if r and r[1] is not None), key=lambda r: r[0])
    last_index = len(ordered) - 1
    prev_condition = str((state or {}).get("condition") or "ok")
    # Only the batch's FIRST run can inherit the previous batch's open breach,
    # and only when the live engine is holding that breach (see ``live_open``).
    inherit = (prev_condition
               if (live_open and prev_condition in ("high", "low")) else None)
    for i, (epoch, temp_c) in enumerate(ordered):
        try:
            value = float(temp_c)
        except (TypeError, ValueError):
            continue
        condition, limit = classify(
            value, thr, prev_condition=prev_condition, hysteresis=hysteresis)
        prev_condition = condition
        if condition != "ok" and run is not None and run["condition"] != condition:
            _emit(run)               # straight from one limit to the other
            run = None
        if condition == "ok":
            if run is not None:
                _emit(run)
                run = None
        else:
            if run is None:
                run = {"probe_id": probe_id, "kind": "missed", "condition": condition,
                       "limit": limit, "start_epoch": int(epoch),
                       "end_epoch": int(epoch), "temperature_c": value, "samples": 0,
                       "carried": inherit == condition}
            run["end_epoch"] = int(epoch)
            run["samples"] += 1
            # The WORST reading of the run, not the first or last: it is the
            # number that says how bad it got.
            if ((condition == "high" and value > run["temperature_c"])
                    or (condition == "low" and value < run["temperature_c"])):
                run["temperature_c"] = value
        inherit = None               # the first row has been judged
        if i == last_index:
            run = None               # still open — evaluate() owns it
    # Whatever the batch ended on is where the next one resumes: an open breach
    # so it stays suppressed, 'ok' so a genuinely new excursion is reported.
    if state is not None and ordered:
        state["condition"] = prev_condition
    return out


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


def _normalize_conn_state(state, now: float) -> dict:
    """Coerce a stored connectivity state into the working dict form.

    Accepts the legacy plain string (``"online"``/``"offline"``) so old persisted
    state — and the hand-seeded state in tests — keeps working, as well as the
    richer dict this function now returns.
    """
    if isinstance(state, dict):
        committed = state.get("committed", "online")
        return {
            "raw": state.get("raw", committed),
            "committed": committed,
            "online_since": state.get("online_since"),
            "flaps": int(state.get("flaps", 0) or 0),
        }
    s = state if state in ("online", "offline") else "online"
    return {"raw": s, "committed": s,
            "online_since": now if s == "online" else None, "flaps": 0}


def evaluate_offline(last_epochs: Dict[str, int], states: dict,
                     now: Optional[float] = None,
                     offline_after_sec: Union[float, Dict[str, float]] = 300,
                     recover_hold_sec: Union[float, Dict[str, float]] = 0) -> Tuple[List[dict], dict]:
    """Detect probes that have stopped (or resumed) reporting, with flap damping.

    Going *offline* is reported the moment a probe has been silent past its
    threshold — that first drop is a genuine incident you want to know about.
    Coming *back online* is damped: a probe on a weak link (spotty freezer Wi-Fi)
    that lands one reading then goes quiet again would otherwise flap
    offline→online→offline and fire a pair of notifications every cycle.

    ``recover_hold_sec`` is the connectivity analogue of the temperature
    :func:`classify` deadband: once a probe is reported offline it must stay
    *continuously* online for this long before "back online" is emitted.  Blips
    shorter than the hold are absorbed, so a whole flaky episode collapses to a
    single offline and a single (confirmed) back-online.  Each offline→online
    bounce that happens *during* an open outage is counted and carried out on the
    eventual back-online event as ``flaps``, so the message can say the link was
    unstable.  ``0`` (the default) restores the legacy behaviour: recovery is
    reported on the first fresh reading.

    Parameters
    ----------
    last_epochs : ``{probe_id: epoch_of_latest_reading}`` for currently-tracked probes
    states : previous per-probe state (a dict as returned here, or a legacy
        ``"online"``/``"offline"`` string — both are accepted)
    offline_after_sec : silence threshold in seconds — either one number applied
        to every probe, or a ``{probe_id: seconds}`` mapping so each probe is
        judged against its own window (e.g. ``core.status.probe_fresh_window``,
        which scales with a probe's reporting interval).  Probes missing from
        the mapping fall back to 300 s.
    recover_hold_sec : back-online confirmation window in seconds — a single
        number or a ``{probe_id: seconds}`` mapping (probes missing from it use
        0). ``core.status.probe_fresh_window`` is a natural per-probe value: a
        probe is trusted "back" once it has been steady for as long as it took to
        call it offline.

    Returns ``(events, new_states)``.  Probes absent from ``last_epochs`` (e.g.
    aged out of the tracking window) are dropped from the returned states.
    """
    now = now if now is not None else time.time()
    per_probe = offline_after_sec if isinstance(offline_after_sec, dict) else None
    per_hold = recover_hold_sec if isinstance(recover_hold_sec, dict) else None
    new_states: dict = {}
    events: List[dict] = []
    for probe_id, last_epoch in last_epochs.items():
        threshold = per_probe.get(probe_id, 300) if per_probe is not None else offline_after_sec
        hold = (per_hold.get(probe_id, 0) if per_hold is not None else recover_hold_sec) or 0
        age = now - last_epoch
        raw = "offline" if age > threshold else "online"

        st = _normalize_conn_state(states.get(probe_id), now)
        committed = st["committed"]
        online_since = st["online_since"]
        flaps = st["flaps"]

        # Anchor the online streak to the epoch of its FIRST reading, and count a
        # "flap" whenever the probe bounces back offline while an outage is still
        # open (unconfirmed). online_since holds a reading epoch, not wall-clock:
        # a single reading keeps raw=="online" for a whole freshness window
        # (age <= threshold) even while the probe is silent, so timing the hold
        # against `now` would let one blip clear the outage the moment enough
        # wall-clock passed. Timing it against the newest reading's epoch instead
        # requires the probe to have actually PRODUCED readings spanning the hold.
        if raw == "online":
            if online_since is None:
                online_since = last_epoch
        else:  # raw offline
            if st["raw"] == "online" and committed == "offline":
                flaps += 1
            online_since = None

        if committed == "online":
            if raw == "offline":
                committed, flaps = "offline", 0
                events.append({"probe_id": probe_id, "kind": "offline", "age_sec": int(age)})
        else:  # committed offline — hold the all-clear until the probe has
               # reported steadily: newest reading fresh AND readings now span
               # the hold window (last_epoch advanced >= hold beyond streak start).
            if raw == "online" and (last_epoch - online_since) >= hold:
                committed = "online"
                ev = {"probe_id": probe_id, "kind": "online", "age_sec": int(age)}
                if flaps:
                    ev["flaps"] = flaps
                events.append(ev)
                flaps = 0

        new_states[probe_id] = {"raw": raw, "committed": committed,
                                "online_since": online_since, "flaps": flaps}
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
        flaps = int(event.get("flaps", 0) or 0)
        if flaps >= 2:
            return (f"✅ {label}: back online (link was unstable)",
                    f"{label} is reporting steadily again — it dropped {flaps} times "
                    f"on a weak connection before staying up.")
        return (f"✅ {label}: back online",
                f"{label} is reporting again.")

    c = event["temperature_c"]
    f = c_to_f(c)
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
    if kind == "missed":
        # Past tense throughout, and it says WHEN: this is history arriving late,
        # and a message written like a live alert would send someone to check a
        # freezer that is currently fine.
        mins = max(1, int(event.get("end_epoch", 0) - event.get("start_epoch", 0)) // 60)
        when = _local_clock(event.get("start_epoch"))
        direction = ("above the" if event.get("condition") == "high" else "below the")
        bound = "maximum" if event.get("condition") == "high" else "minimum"
        limit_txt = (f" {direction} {limit:.1f}°C {bound}" if limit is not None else "")
        return (f"⚠️ {label}: went out of range for {mins} min while the hub was not watching",
                f"{label} reached {reading}{limit_txt}, starting around {when} and lasting "
                f"about {mins} minute(s). It has since returned to normal.\n\n"
                f"These readings arrived late — the probe stored them while it could not "
                f"reach the hub, and sent them when it reconnected. Nothing was wrong with "
                f"the probe; the alert simply could not be raised at the time.")
    return f"{label}: {reading}", f"{label} is {reading}."


def _local_clock(epoch) -> str:
    """``epoch`` as a short local wall-clock string, or '' if unreadable."""
    try:
        return datetime.datetime.fromtimestamp(float(epoch)).strftime("%H:%M on %d %b")
    except (TypeError, ValueError, OSError, OverflowError):
        return "an unknown time"

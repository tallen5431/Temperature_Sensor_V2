"""Ingest payload normalisation and timezone handling.

The persistence layer now lives in :mod:`core.db` (SQLite).  This module is
responsible only for turning a probe's HTTP payload into a normalised
``(timestamp, celsius, fahrenheit)`` triple, with timestamps converted to
local machine time so every stored row shares one timezone.  It also holds the
small pure helpers for the optional humidity / VPD (grow) variant and the
shared threshold-breach check.
"""
from __future__ import annotations

import datetime
import math
import re
import time

# A probe with a bad clock (failed NTP / drifted RTC) can stamp a reading in the
# future. The hub's clock is authoritative, so a timestamp more than this many
# seconds ahead of "now" is treated as a glitch and clamped to the hub's current
# time — otherwise the dashboard draws a line into the future and that bogus
# "latest" reading can mask a live threshold breach.
_FUTURE_TOLERANCE_SEC = 120

# A probe id is a short token. A real TempSensor sends "TempSensor-<HEX6>";
# this bounds anything a buggy/malicious LAN client might POST so an arbitrary
# value can never reach the database, the CSV export, or an MQTT topic.
_PROBE_ID_STRIP = re.compile(r"[^A-Za-z0-9_-]")


def sanitize_probe_id(probe_id) -> str:
    """Coerce a probe id to a safe token: keep ``[A-Za-z0-9_-]``, cap at 32 chars.

    Valid ids (``TempSensor-9A3F2C``) pass through unchanged; junk is stripped.
    Returns ``""`` if nothing valid remains (treated as an anonymous reading).
    """
    if not probe_id:
        return ""
    return _PROBE_ID_STRIP.sub("", str(probe_id))[:32]


def _local_iso_now() -> str:
    """Current local machine time as a naive ISO 8601 string (no tz suffix)."""
    return datetime.datetime.now().isoformat(timespec="seconds")


def _to_local_naive(ts_str: str) -> str:
    """Convert a timestamp string to local machine time as a naive ISO string.

    Timestamps carrying explicit timezone info (trailing ``Z`` for UTC, or a
    ``+HH:MM`` / ``-HH:MM`` offset, with or without fractional seconds) are
    converted to the local machine timezone before the offset is dropped.
    Naive timestamps are assumed to already be local time and returned trimmed
    to second precision.
    """
    ts_str = str(ts_str).strip()
    has_z = ts_str.endswith("Z")
    # Find a timezone offset sign after the time portion (skip the date's
    # hyphens by starting the search at the 'T'/space separator).
    sep = max(ts_str.find("T"), ts_str.find(" "))
    has_offset = False
    if sep != -1:
        tail = ts_str[sep + 1:]
        has_offset = ("+" in tail) or ("-" in tail)

    if has_z or has_offset:
        try:
            aware = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if aware.tzinfo is not None:
                return aware.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
        except Exception:
            pass  # fall through and use as-is

    # Already naive (or unparseable) — trim to seconds precision.
    try:
        return datetime.datetime.fromisoformat(ts_str.split("+")[0].rstrip("Z")).isoformat(timespec="seconds")
    except Exception:
        return ts_str[:19]


def _clamp_future(ts: str) -> str:
    """Replace an implausibly-future timestamp with the hub's current time.

    A reading can only measure the present, so a stamp far ahead of now means the
    probe's clock is wrong; trust the hub's clock instead. Past timestamps (e.g.
    buffered offline readings flushed on reconnect) are left untouched.
    """
    try:
        if datetime.datetime.fromisoformat(str(ts)).timestamp() > time.time() + _FUTURE_TOLERANCE_SEC:
            return _local_iso_now()
    except Exception:
        pass
    return ts


def normalize_payload(payload: dict):
    """Normalise an ingest payload.

    Accepts temperature keys like ``temperature_c``/``temp_c``/``t_c`` (and the
    Fahrenheit equivalents) plus an optional ``timestamp``/``ts``.  Returns
    ``(timestamp_iso_local, celsius, fahrenheit)``; raises ``ValueError`` if no
    temperature value is present.
    """
    raw_ts = payload.get("timestamp") or payload.get("ts") or ""
    ts = _clamp_future(_to_local_naive(raw_ts)) if raw_ts else _local_iso_now()

    c_keys = ["temperature_c", "temp_c", "t_c", "c"]
    f_keys = ["temperature_f", "temp_f", "t_f", "f"]

    t_c = next((float(payload[k]) for k in c_keys if k in payload and payload[k] not in (None, "")), None)
    t_f = next((float(payload[k]) for k in f_keys if k in payload and payload[k] not in (None, "")), None)

    if t_c is None and t_f is None:
        raise ValueError("No temperature value found")

    if t_c is None:  # compute from F
        t_c = (t_f - 32.0) * 5.0 / 9.0
    if t_f is None:  # compute from C
        t_f = (t_c * 9.0 / 5.0) + 32.0

    # Enforce the ingest contract (PROTOCOL.md §6): the resolved value must be a
    # finite number in a physically sane band. This rejects NaN/inf (which would
    # otherwise 500 on the NOT NULL insert or poison stats/exports) and sensor
    # fault codes (85.0 power-on, -127 disconnected) before they reach the DB and
    # fire spurious alerts. Callers turn the ValueError into a clean 400.
    if not (math.isfinite(t_c) and math.isfinite(t_f)):
        raise ValueError("temperature must be a finite number")
    if not (-60.0 <= t_c <= 150.0):
        raise ValueError("temperature out of range (-60..150 C)")

    return ts, float(t_c), float(t_f)


def threshold_breach(value, lo, hi):
    """Single source of truth for 'is this reading out of range?'.

    Returns "high" if value > hi, "low" if value < lo, else None. A None bound is
    ignored — but a bound of 0 is a REAL threshold (freezer/greenhouse), so this
    checks ``is not None`` rather than truthiness. Both the dashboard alert banner
    and the server-side notifier use this so they can't diverge.
    """
    try:
        if hi is not None and value > float(hi):
            return "high"
        if lo is not None and value < float(lo):
            return "low"
    except (TypeError, ValueError):
        return None
    return None


def extract_humidity(payload: dict):
    """Return a validated relative-humidity percentage from an ingest payload, or None.

    Accepts humidity_pct / humidity / rh / h. Values must be finite and within
    0..100 %RH; anything else is treated as 'no humidity reading' (returns None)
    rather than corrupting the log — a temperature-only probe simply omits it.
    """
    for k in ("humidity_pct", "humidity", "rh", "h"):
        if k in payload and payload[k] not in (None, ""):
            try:
                rh = float(payload[k])
            except (TypeError, ValueError):
                return None
            if math.isfinite(rh) and 0.0 <= rh <= 100.0:
                return rh
            return None
    return None


def compute_vpd(temp_c: float, rh_pct: float, leaf_offset_c: float = 0.0) -> float:
    """Vapour Pressure Deficit in kPa — the metric indoor growers actually buy on.

    Uses the Tetens saturation-vapour-pressure formula. ``leaf_offset_c`` models
    leaf temperature below air temperature (growers typically use ~2 °C); 0 gives
    plain air VPD. Returned value is clamped to be non-negative.
    """
    def svp(t):  # saturation vapour pressure (kPa)
        denom = t + 237.3
        if denom <= 0:  # sub -237.3 C: guard the division/overflow, return 0 kPa
            return 0.0
        return 0.6108 * math.exp((17.27 * t) / denom)

    leaf_t = temp_c - float(leaf_offset_c or 0.0)
    vpd = svp(leaf_t) - svp(temp_c) * (float(rh_pct) / 100.0)
    return max(0.0, vpd)

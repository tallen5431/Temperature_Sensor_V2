"""Ingest payload normalisation and timezone handling.

The persistence layer now lives in :mod:`core.db` (SQLite).  This module is
responsible only for turning a probe's HTTP payload into a normalised
``(timestamp, celsius, fahrenheit)`` triple, with timestamps converted to
local machine time so every stored row shares one timezone.
"""
from __future__ import annotations

import datetime


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


def normalize_payload(payload: dict):
    """Normalise an ingest payload.

    Accepts temperature keys like ``temperature_c``/``temp_c``/``t_c`` (and the
    Fahrenheit equivalents) plus an optional ``timestamp``/``ts``.  Returns
    ``(timestamp_iso_local, celsius, fahrenheit)``; raises ``ValueError`` if no
    temperature value is present.
    """
    raw_ts = payload.get("timestamp") or payload.get("ts") or ""
    ts = _to_local_naive(raw_ts) if raw_ts else _local_iso_now()

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

    return ts, float(t_c), float(t_f)

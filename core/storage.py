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
from core.units import c_to_f, f_to_c

# A probe with a bad clock (failed NTP / drifted RTC) can stamp a reading in the
# future. The hub's clock is authoritative, so a timestamp more than this many
# seconds ahead of "now" is treated as a glitch and clamped to the hub's current
# time — otherwise the dashboard draws a line into the future and that bogus
# "latest" reading can mask a live threshold breach.
_FUTURE_TOLERANCE_SEC = 120

# A hub wall clock earlier than this is treated as not-yet-NTP-synced and is NOT
# trusted for any decision that would discard or overwrite probe data. Hub
# hardware without a battery-backed RTC (a Raspberry Pi) boots to 1970/epoch-0 or
# a stale fake-hwclock date; 2025-01-01 UTC is safely before this software runs in
# production yet well after those bad-clock values. Canonical here and imported by
# core.db (delete_future_readings) so the two clock guards cannot drift apart.
CLOCK_TRUSTWORTHY_FLOOR_EPOCH = 1_735_689_600  # 2025-01-01T00:00:00Z

# A probe id is a short token. A real Setpoint sends "Setpoint-<HEX6>";
# this bounds anything a buggy/malicious LAN client might POST so an arbitrary
# value can never reach the database, the CSV export, or an MQTT topic.
_PROBE_ID_STRIP = re.compile(r"[^A-Za-z0-9_-]")


def sanitize_probe_id(probe_id) -> str:
    """Coerce a probe id to a safe token: keep ``[A-Za-z0-9_-]``, cap at 32 chars.

    Valid ids (``Setpoint-9A3F2C``) pass through unchanged; junk is stripped.
    Returns ``""`` if nothing valid remains — see :func:`storage_probe_id` for
    what an ingest path does with that.
    """
    if not probe_id:
        return ""
    return _PROBE_ID_STRIP.sub("", str(probe_id))[:32]


# Where a reading with no usable id gets filed. PROTOCOL.md §6.4 says such a
# reading "is still logged, without an id" — and it was, under probe_id "", which
# every UI surface skips (`if not str(pid).strip(): continue`) and which
# `delete_probe("")` refuses to touch. So the hub answered `{"ok": true}`, stored
# the row, counted it in the readings total, wrote it to the CSV export with a
# blank column, and showed it precisely nowhere, with no way to remove it. An
# integrator who forgot X-Probe-ID watched the readings counter climb and no
# probe ever appear.
#
# The reading is still kept — a bad label is never a reason to lose a
# temperature, the same rule the rest of this module follows. It just gets an id
# a human can see, name and delete, so a broken sender is a visible fact on the
# dashboard instead of an invisible one in the file.
UNIDENTIFIED_PROBE_ID = "unidentified"


def storage_probe_id(probe_id) -> str:
    """The id an ingest path should FILE a reading under.

    :func:`sanitize_probe_id` answers "what is this id, cleaned up?" and is what
    to use for comparing, looking up per-probe config, or deciding whether a
    caller supplied one. This answers the different question of where the row
    goes, and never returns empty.
    """
    return sanitize_probe_id(probe_id) or UNIDENTIFIED_PROBE_ID


def sanitize_site(site) -> str:
    """Coerce a site name to a safe token, same charset and cap as a probe id.

    ``site`` labels which building a reading came from. It is empty for every
    locally-ingested reading and set only on rows a store hub forwarded to an
    aggregating hub, so an HQ dashboard can tell six stores apart. Sanitised
    rather than rejected for the same reason probe ids are: a bad label must not
    cost a good temperature reading.
    """
    if not site:
        return ""
    return _PROBE_ID_STRIP.sub("", str(site))[:32]


def _local_iso_now() -> str:
    """Current local machine time as a naive ISO 8601 string (no tz suffix).

    Millisecond precision: this stamps a payload that arrives WITHOUT its own
    timestamp (a probe whose clock hasn't synced yet). Two such readings from
    one probe within the same wall-clock second would collapse onto an identical
    whole-second stamp — and the UNIQUE(probe_id, epoch, site) ingest index would then
    treat the second as a duplicate and drop it. Sub-second precision keeps them
    distinct so no legitimate reading is ever discarded.
    """
    return datetime.datetime.now().isoformat(timespec="milliseconds")


def _iso_keep_subsec(dt: datetime.datetime) -> str:
    """ISO 8601 string keeping millisecond precision when the value has any, else
    whole seconds.

    High-rate logging (e.g. a 0.5 s cadence while a freezer door is open) needs
    sub-second timestamps so two readings within the same second stay
    distinguishable. A probe that only sends whole seconds still gets a clean
    second-resolution stamp with no spurious ``.000`` suffix, so nothing changes
    for the common case.
    """
    return dt.isoformat(timespec="milliseconds" if dt.microsecond else "seconds")


def _to_local_naive(ts_str: str) -> str:
    """Convert a timestamp string to local machine time as a naive ISO string.

    Timestamps carrying explicit timezone info (trailing ``Z`` for UTC, or a
    ``+HH:MM`` / ``-HH:MM`` offset, with or without fractional seconds) are
    converted to the local machine timezone before the offset is dropped.
    Naive timestamps are assumed to already be local time. Millisecond precision
    is preserved when present (see :func:`_iso_keep_subsec`).
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
                return _iso_keep_subsec(aware.astimezone().replace(tzinfo=None))
        except Exception:
            pass  # fall through and use as-is

    # Already naive (or unparseable) — keep sub-second precision when present.
    try:
        return _iso_keep_subsec(datetime.datetime.fromisoformat(ts_str.split("+")[0].rstrip("Z")))
    except Exception:
        return ts_str[:23]


def _clamp_future(ts: str) -> str:
    """Replace an implausibly-future timestamp with the hub's current time.

    A reading can only measure the present, so a stamp far ahead of now means the
    probe's clock is wrong; trust the hub's clock instead. Past timestamps (e.g.
    buffered offline readings flushed on reconnect) are left untouched.

    ...but only when the HUB's clock is itself trustworthy. This runs on every
    ingest, and hub hardware without a battery-backed RTC (a Raspberry Pi) can
    boot to 1970 or a stale date before NTP lands. With a clock that far behind,
    every correct probe stamp looks "far in the future" and would be overwritten
    with the hub's wrong time — destroying the good data in favour of the bad
    clock. Worse, a whole replayed backlog then collapses onto near-identical
    stamps and the UNIQUE(probe_id, epoch, site) index drops all but a couple of rows.
    So below the trust floor we keep the probe's stamp: the probe only stamps a
    reading once its own clock is NTP-valid, making it the better source.
    """
    try:
        now = time.time()
        if now < CLOCK_TRUSTWORTHY_FLOOR_EPOCH:
            return ts       # hub clock not yet synced — the probe's stamp wins
        if datetime.datetime.fromisoformat(str(ts)).timestamp() > now + _FUTURE_TOLERANCE_SEC:
            return _local_iso_now()
    except Exception:
        pass
    return ts


def absolute_epoch(raw_ts) -> float | None:
    """The exact POSIX epoch of a timestamp that carries explicit timezone info.

    Readings are STORED as local-naive strings so every row shares one timezone,
    but that conversion is lossy exactly once a year: during the DST fall-back
    hour two distinct UTC instants an hour apart map to the same local wall time
    (01:30 EDT and 01:30 EST are both "01:30"). Re-deriving the epoch from that
    string then gives both readings the SAME epoch, which

      * makes them collide on the ``UNIQUE(probe_id, epoch, site)`` ingest index, so
        one is silently discarded, and
      * interleaves the whole repeated hour when anything sorts by epoch — the
        chart, the exports, the rate-of-change window.

    The firmware always stamps in UTC (``nowIso()`` emits a trailing ``Z``), so
    the unambiguous instant IS available on the wire — it just has to be carried
    past the local-naive conversion instead of being recomputed from it.

    Returns ``None`` for a naive stamp (nothing better is knowable) or an
    unparseable one, in which case callers fall back to ``iso_to_epoch``.
    """
    s = str(raw_ts or "").strip()
    if not s:
        return None
    has_z = s.endswith("Z")
    sep = max(s.find("T"), s.find(" "))
    has_offset = sep != -1 and (("+" in s[sep + 1:]) or ("-" in s[sep + 1:]))
    if not (has_z or has_offset):
        return None
    try:
        aware = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return aware.timestamp() if aware.tzinfo is not None else None
    except Exception:
        return None


def is_future_stamp(raw_ts, now: float | None = None) -> bool:
    """True when a raw ingest timestamp is implausibly ahead of the hub's clock.

    Public counterpart to the clamp inside :func:`normalize_payload`, for callers
    that must know a row WILL be clamped before it happens — notably the bulk
    ``/ingest_csv`` drain, which has to re-stamp such rows itself (spread 1 ms
    apart) instead of letting every row clamp independently to the same
    millisecond and be swallowed by the UNIQUE(probe_id, epoch, site) index.

    Returns ``False`` when the hub's own clock is below the trust floor: an
    unsynced hub must never classify a correctly-stamped probe reading as
    "future" (see :func:`_clamp_future`).
    """
    if not raw_ts:
        return False
    now = time.time() if now is None else now
    if now < CLOCK_TRUSTWORTHY_FLOOR_EPOCH:
        return False
    try:
        local = _to_local_naive(str(raw_ts))
        return datetime.datetime.fromisoformat(local).timestamp() > now + _FUTURE_TOLERANCE_SEC
    except Exception:
        return False


def _as_float(v) -> float:
    """``float()`` that reports an out-of-range JSON integer as a ``ValueError``.

    ``json.loads`` yields arbitrary-precision ints, and ``float(10**400)`` raises
    **OverflowError** — which is not a ValueError subclass, so it escaped both
    ingest handlers (they catch ``(ValueError, KeyError, TypeError)``, matching
    what :func:`normalize_payload` documents itself as raising). One such reading
    500ed the endpoint: on the bulk path that loses the probe's WHOLE batch and
    counts a write failure, so the hub also starts reporting itself unhealthy.
    A number the hub cannot represent is a rejected reading, like any other
    out-of-range value.
    """
    try:
        return float(v)
    except OverflowError as e:
        raise ValueError(str(e)) from e


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

    t_c = next((_as_float(payload[k]) for k in c_keys if k in payload and payload[k] not in (None, "")), None)
    t_f = next((_as_float(payload[k]) for k in f_keys if k in payload and payload[k] not in (None, "")), None)

    if t_c is None and t_f is None:
        raise ValueError("No temperature value found")

    if t_c is None:  # compute from F
        t_c = f_to_c(t_f)
    if t_f is None:  # compute from C
        t_f = c_to_f(t_c)

    # Enforce the ingest contract (PROTOCOL.md §6): the resolved value must be a
    # finite number in a physically sane band. This rejects NaN/inf (which would
    # otherwise 500 on the NOT NULL insert or poison stats/exports) and the -127
    # disconnected sensor fault code before it reaches the DB and fires a
    # spurious alert. (85.0, the DS18B20 power-on value, is physically plausible
    # and is intentionally left in-band.) Callers turn the ValueError into a clean 400.
    if not (math.isfinite(t_c) and math.isfinite(t_f)):
        raise ValueError("temperature must be a finite number")
    if not (-60.0 <= t_c <= 150.0):
        raise ValueError("temperature out of range (-60..150 C)")
    # Gate the Fahrenheit value too (-60..150 C == -76..302 F exactly). When only
    # one unit is sent the other is derived and always agrees, but a payload that
    # sends BOTH could otherwise slip a garbage t_f (e.g. C=25, F=9999) past the
    # C-only check and poison the temperature_f column, stats and exports.
    if not (-76.0 <= t_f <= 302.0):
        raise ValueError("temperature out of range (-76..302 F)")

    return ts, float(t_c), float(t_f)


def threshold_breach(value, lo, hi):
    """Raw-limit check: 'is this reading outside its configured range right now?'.

    Returns "high" if value > hi, "low" if value < lo, else None. A None bound is
    ignored — but a bound of 0 is a REAL threshold (freezer/greenhouse), so this
    checks ``is not None`` rather than truthiness. This is the instantaneous
    check the dashboard banner starts from; the notifier's state machine
    (``core.alerts.classify``) layers a hysteresis deadband on top, so a probe
    can read in-range here while the notifier still HOLDS the breach until it
    clears the limit by the deadband (see ``core.alerts.HELD``).
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
                rh = _as_float(payload[k])
            except (TypeError, ValueError):
                return None
            if math.isfinite(rh) and 0.0 <= rh <= 100.0:
                return rh
            return None
    return None


def extract_battery(payload: dict):
    """Return a validated battery charge percentage (0..100) from an ingest
    payload, or None.

    Accepts ``battery_pct`` (used directly when finite and within 0..100) or,
    failing that, ``battery_v`` — a single-cell LiPo pack voltage mapped
    linearly 3.0 V -> 0 %, 4.2 V -> 100 % and clamped to that range. A voltage
    outside the plausible cell band (2.5..5.0 V) is sensor junk, not a nearly
    full/empty cell, so it — like any non-finite or out-of-band value — means
    'no battery reading' (returns None). A mains-powered probe simply omits
    both keys.
    """
    if "battery_pct" in payload and payload["battery_pct"] not in (None, ""):
        try:
            pct = _as_float(payload["battery_pct"])
        except (TypeError, ValueError):
            return None
        if math.isfinite(pct) and 0.0 <= pct <= 100.0:
            return pct
        return None
    if "battery_v" in payload and payload["battery_v"] not in (None, ""):
        try:
            volts = _as_float(payload["battery_v"])
        except (TypeError, ValueError):
            return None
        if not (math.isfinite(volts) and 2.5 <= volts <= 5.0):
            return None
        pct = (volts - 3.0) / (4.2 - 3.0) * 100.0
        return max(0.0, min(100.0, pct))
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

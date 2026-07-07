# core/storage.py
from __future__ import annotations

import csv
import datetime
import math
import os
import re
import threading
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from core.applog import HEALTH, get_logger

log = get_logger("storage")

COLUMNS = ["timestamp", "temperature_c", "temperature_f", "humidity_pct", "vpd_kpa", "probe_id"]

# Physically plausible bounds for the supported sensors (DS18B20/thermocouple).
# Anything outside this — including sensor fault codes (85.0 power-on, -127
# disconnected) and NaN/inf — is rejected so it can't corrupt dashboard stats.
MIN_TEMP_C = -60.0
MAX_TEMP_C = 150.0

PROBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

# One process-wide lock serializes every writer (multiple Flask/waitress threads
# ingest concurrently). The old code had no lock and a second divergent writer,
# which could interleave partial rows.
_write_lock = threading.Lock()


# --- cross-platform advisory file lock (best-effort, for multi-process safety) --
@contextmanager
def _os_lock(fh):
    locked = False
    try:
        try:
            import fcntl  # POSIX

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            locked = True
        except Exception:
            try:
                import msvcrt  # Windows

                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                locked = True
            except Exception:
                locked = False
        yield
    finally:
        if locked:
            try:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except Exception:
                try:
                    import msvcrt

                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass


def ensure_csv(csv_file: Path) -> None:
    """Create the log with headers, or upgrade an older/narrower file ONCE.

    This is the only place a whole-file rewrite may happen, and it runs at
    startup — never on the per-write hot path. Any columns missing from an older
    log (e.g. probe_id, humidity_pct, vpd_kpa) are added so name-based reads work.
    """
    csv_file = Path(csv_file)
    if not csv_file.exists():
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(COLUMNS)
        return
    # One-time schema upgrade: add any missing columns.
    try:
        df = pd.read_csv(csv_file, nrows=0)
        missing = [c for c in COLUMNS if c not in df.columns]
        if missing:
            full = pd.read_csv(csv_file)
            for c in missing:
                full[c] = ""
            full.to_csv(csv_file, index=False)
            log.info("Upgraded %s to include columns: %s", csv_file.name, ", ".join(missing))
    except Exception as e:
        log.warning("Could not verify/upgrade CSV schema for %s: %s", csv_file, e)


def _escape_csv_field(value: str) -> str:
    """Neutralize spreadsheet formula injection.

    A malicious/malfunctioning probe could send probe_id='=HYPERLINK(...)'; if
    the customer opens the exported CSV in Excel/Sheets it would execute. Prefix
    any field beginning with a formula trigger with a single quote.
    """
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def sanitize_probe_id(probe_id) -> str:
    """Constrain probe_id to a safe, bounded identifier. Empty string if invalid."""
    if not probe_id:
        return ""
    s = str(probe_id).strip()
    return s if PROBE_ID_RE.match(s) else ""


def append_row(csv_file: Path, ts: str, t_c: float, t_f: float, probe_id: str | None = None,
               humidity_pct: float | None = None, vpd_kpa: float | None = None) -> None:
    """Append exactly one row (in COLUMNS order) through the single serialized writer.

    Always writes every column (empty string when a value is absent) so rows are
    never ragged. humidity_pct/vpd_kpa are populated only for probes with an RH
    sensor; temperature-only probes leave them blank.
    """
    csv_file = Path(csv_file)
    pid = _escape_csv_field(probe_id or "")
    row = [
        ts,
        f"{float(t_c):.3f}",
        f"{float(t_f):.3f}",
        "" if humidity_pct is None else f"{float(humidity_pct):.2f}",
        "" if vpd_kpa is None else f"{float(vpd_kpa):.3f}",
        pid,
    ]
    try:
        with _write_lock:
            need_header = (not csv_file.exists()) or csv_file.stat().st_size == 0
            with open(csv_file, "a", newline="", encoding="utf-8") as f:
                with _os_lock(f):
                    w = csv.writer(f)
                    if need_header:
                        w.writerow(COLUMNS)
                    w.writerow(row)
                    f.flush()
                    os.fsync(f.fileno())
        HEALTH.record_write()
    except Exception as e:
        HEALTH.record_failure()
        log.error("Failed to append reading to %s: %s", csv_file, e)
        raise


def apply_calibration(t_c: float, probe_id: str, calibration: dict | None) -> float:
    """Apply a per-probe calibration (gain then offset) before logging.

    Temperature instruments drift unit-to-unit; a customer trims to a reference
    (e.g. ice bath) and the correction lives in config, not in firmware.
    """
    if not calibration or not probe_id:
        return t_c
    cal = calibration.get(probe_id) or calibration.get("default")
    if not isinstance(cal, dict):
        return t_c
    try:
        gain = float(cal.get("gain", 1.0) or 1.0)
        offset = float(cal.get("offset_c", 0.0) or 0.0)
        return (t_c * gain) + offset
    except Exception:
        return t_c


def normalize_payload(payload: dict):
    """Parse and *validate* an ingest payload.

    Accepts temperature_c/temp_c/t_c/c or temperature_f/temp_f/t_f/f. Rejects
    non-finite values and anything outside the plausible sensor range so a fault
    code or NaN can never poison the log or the auto-scaled dashboard axis.

    Returns (timestamp_iso, celsius, fahrenheit).
    Raises ValueError on missing or out-of-range input.
    """
    now = datetime.datetime.now().isoformat(timespec="seconds")
    ts = payload.get("timestamp") or payload.get("ts") or now

    c_keys = ["temperature_c", "temp_c", "t_c", "c"]
    f_keys = ["temperature_f", "temp_f", "t_f", "f"]

    def _first_float(keys):
        for k in keys:
            if k in payload and payload[k] not in (None, ""):
                return float(payload[k])
        return None

    t_c = _first_float(c_keys)
    t_f = _first_float(f_keys)

    if t_c is None and t_f is None:
        raise ValueError("No temperature value found")

    if t_c is None:
        t_c = (t_f - 32.0) * 5.0 / 9.0
    if t_f is None:
        t_f = (t_c * 9.0 / 5.0) + 32.0

    if not math.isfinite(t_c):
        raise ValueError("Temperature is not a finite number")
    if not (MIN_TEMP_C <= t_c <= MAX_TEMP_C):
        raise ValueError(f"Temperature {t_c:.2f}C outside valid range [{MIN_TEMP_C}, {MAX_TEMP_C}]")

    return ts, float(t_c), float(t_f)


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
        return 0.6108 * math.exp((17.27 * t) / (t + 237.3))

    leaf_t = temp_c - float(leaf_offset_c or 0.0)
    vpd = svp(leaf_t) - svp(temp_c) * (float(rh_pct) / 100.0)
    return max(0.0, vpd)

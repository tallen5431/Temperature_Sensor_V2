# core/storage.py
from __future__ import annotations
from pathlib import Path
import pandas as pd
import datetime
import threading

REQUIRED_COLS = ["timestamp","temperature_c","temperature_f"]
OPTIONAL_COLS = ["probe_id"]

# Serialise all writes so concurrent Flask threads and the PullLogger thread
# never interleave rows or produce out-of-order timestamps.
_write_lock = threading.Lock()

# Cache of (csv_path_str, column_name) pairs that are confirmed present.
# Avoids re-reading the whole file on every append_row call.
_column_cache: set = set()

def ensure_csv(csv_file: Path) -> None:
    if not csv_file.exists():
        cols = REQUIRED_COLS + OPTIONAL_COLS
        pd.DataFrame(columns=cols).to_csv(csv_file, index=False)
        # Pre-populate cache so _ensure_column skips the read entirely
        for col in cols:
            _column_cache.add((str(csv_file), col))

def _ensure_column(csv_file: Path, col: str) -> None:
    # Upgrade-in-place to add a missing column (keeps data). Small file friendly.
    # Caller must already hold _write_lock.
    cache_key = (str(csv_file), col)
    if cache_key in _column_cache:
        return
    try:
        df = pd.read_csv(csv_file)
        if col not in df.columns:
            df[col] = ""
            df.to_csv(csv_file, index=False)
        _column_cache.add(cache_key)
    except Exception:
        # If anything goes wrong, leave file as-is; app will still run.
        pass

# Backwards compatible append: probe_id is optional
def append_row(csv_file: Path, ts: str, t_c: float, t_f: float, probe_id: str|None = None) -> None:
    with _write_lock:
        try:
            # If probe_id present, make sure file has that column
            if probe_id is not None:
                _ensure_column(csv_file, "probe_id")
                df = pd.DataFrame([[ts, t_c, t_f, probe_id]], columns=REQUIRED_COLS + ["probe_id"])
            else:
                df = pd.DataFrame([[ts, t_c, t_f]], columns=REQUIRED_COLS)
            # Write with header only if file empty (pandas handles this automatically when mode='a' with header=False)
            df.to_csv(csv_file, mode="a", header=False, index=False)
        except Exception:
            # Last-resort fallback (try without probe_id)
            pd.DataFrame([[ts, t_c, t_f]], columns=REQUIRED_COLS).to_csv(csv_file, mode="a", header=False, index=False)

def _local_iso_now() -> str:
    """Current local machine time as a naive ISO 8601 string (no timezone suffix)."""
    return datetime.datetime.now().isoformat(timespec="seconds")


def _to_local_naive(ts_str: str) -> str:
    """Convert a timestamp string to local machine time, returned as a naive ISO string.

    Timestamps that carry explicit timezone info (trailing 'Z' for UTC, or a
    '+HH:MM'/'-HH:MM' offset) are converted to the local machine timezone before
    the offset is dropped.  Timestamps that are already naive are assumed to be
    local time and are returned unchanged (trimmed to second precision).
    """
    ts_str = str(ts_str).strip()
    has_z      = ts_str.endswith('Z')
    has_offset = len(ts_str) > 19 and ts_str[19] in ('+', '-')

    if has_z or has_offset:
        try:
            # Replace 'Z' with '+00:00' so fromisoformat can parse it on Python <3.11
            aware = datetime.datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            # Convert to local wall-clock time and drop tzinfo
            return aware.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
        except Exception:
            pass  # fall through and use as-is

    # Already naive (or unparseable) — trim to 19 chars (seconds precision)
    return ts_str[:19]


def normalize_payload(payload: dict):
    """
    Accepts keys like temperature_c/temp_c/t_c or temperature_f/temp_f/t_f.
    Returns (timestamp_iso, celsius, fahrenheit)
    """
    raw_ts = payload.get("timestamp") or payload.get("ts") or ""
    # Convert to local naive ISO so every row in the CSV is in the same
    # timezone (local machine time).  Probe timestamps arrive as UTC (with 'Z')
    # and must be shifted, not just stripped, to display correctly.
    ts = _to_local_naive(raw_ts) if raw_ts else _local_iso_now()

    c_keys = ["temperature_c","temp_c","t_c","c"]
    f_keys = ["temperature_f","temp_f","t_f","f"]

    t_c = next((float(payload[k]) for k in c_keys if k in payload), None)
    t_f = next((float(payload[k]) for k in f_keys if k in payload), None)

    if t_c is None and t_f is None:
        raise ValueError("No temperature value found")

    if t_c is None:  # compute from F
        t_c = (t_f - 32.0) * 5.0 / 9.0
    if t_f is None:  # compute from C
        t_f = (t_c * 9.0 / 5.0) + 32.0

    return ts, float(t_c), float(t_f)

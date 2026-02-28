# core/storage.py
from __future__ import annotations
from pathlib import Path
import pandas as pd
import datetime

REQUIRED_COLS = ["timestamp","temperature_c","temperature_f"]
OPTIONAL_COLS = ["probe_id"]

def ensure_csv(csv_file: Path) -> None:
    if not csv_file.exists():
        cols = REQUIRED_COLS + OPTIONAL_COLS
        pd.DataFrame(columns=cols).to_csv(csv_file, index=False)

def _ensure_column(csv_file: Path, col: str) -> None:
    # Upgrade-in-place to add a missing column (keeps data). Small file friendly.
    try:
        df = pd.read_csv(csv_file)
        if col not in df.columns:
            df[col] = ""
            df.to_csv(csv_file, index=False)
    except Exception:
        # If anything goes wrong, leave file as-is; app will still run.
        pass

# Backwards compatible append: probe_id is optional
def append_row(csv_file: Path, ts: str, t_c: float, t_f: float, probe_id: str|None = None) -> None:
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

def normalize_payload(payload: dict):
    """
    Accepts keys like temperature_c/temp_c/t_c or temperature_f/temp_f/t_f.
    Returns (timestamp_iso, celsius, fahrenheit)
    """
    now = datetime.datetime.now().isoformat(timespec="seconds")
    ts = payload.get("timestamp") or payload.get("ts") or now

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

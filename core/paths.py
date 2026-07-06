# core/paths.py
"""Single source of truth for filesystem paths.

The old code let the writer use an absolute CSV path while the dashboard reader
defaulted to a *relative* one, so launching from any other working directory
logged to one file and read from another — a permanently empty dashboard. Both
sides now import the exact same resolved path from here.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def get_csv_path() -> Path:
    env = os.getenv("CSV_FILE")
    return Path(env).resolve() if env else (BASE_DIR / "temperature_log.csv")


def get_log_dir() -> Path:
    return Path(os.getenv("LOG_DIR") or (BASE_DIR / "logs"))

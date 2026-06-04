"""SQLite-backed reading store for the Temperature Hub.

Replaces the previous append-only CSV file as the system of record.  The CSV
approach rewrote the whole file to add columns and was read in full by the
dashboard every few seconds, which caused blank-dashboard / corruption issues
under concurrent access and did not scale to long-term logging.

Design notes
------------
* WAL journal mode lets the dashboard read while probes are still writing,
  without readers ever seeing a half-written file.
* One connection per thread (``threading.local``) so Flask/waitress worker
  threads never share a connection object.  A single write lock serialises
  writers to avoid "database is locked" errors under load.
* Every row stores both the human-readable local ISO ``ts`` and an integer
  ``epoch`` so time-window queries are index-backed and fast regardless of how
  much history has accumulated.
"""
from __future__ import annotations

import csv as _csv
import datetime
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

import pandas as pd

# Columns exposed to the rest of the app.  ``timestamp`` is aliased from the
# ``ts`` column so existing dashboard code keeps working unchanged.
_SELECT_COLS = "ts AS timestamp, temperature_c, temperature_f, probe_id"


def iso_to_epoch(ts: str) -> int:
    """Convert a local-naive ISO timestamp to a POSIX epoch (seconds).

    Naive timestamps are interpreted as local machine time, matching how the
    rest of the app stores them.  Returns the current epoch if parsing fails so
    a malformed timestamp never blocks an insert.
    """
    try:
        s = str(ts).strip().rstrip("Z")
        return int(datetime.datetime.fromisoformat(s).timestamp())
    except Exception:
        return int(time.time())


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._write_lock = threading.Lock()
        self._local = threading.local()
        self._init_schema()

    # -- connection management -------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
        return conn

    def _init_schema(self) -> None:
        conn = self._conn()
        with self._write_lock:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS readings (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts            TEXT    NOT NULL,
                    epoch         INTEGER NOT NULL,
                    temperature_c REAL    NOT NULL,
                    temperature_f REAL    NOT NULL,
                    probe_id      TEXT    NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_readings_epoch ON readings(epoch)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_readings_probe_epoch ON readings(probe_id, epoch)"
            )
            conn.commit()

    # -- writes ----------------------------------------------------------------
    def append(self, ts: str, t_c: float, t_f: float, probe_id: str = "") -> None:
        epoch = iso_to_epoch(ts)
        conn = self._conn()
        with self._write_lock:
            conn.execute(
                "INSERT INTO readings (ts, epoch, temperature_c, temperature_f, probe_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(ts), epoch, float(t_c), float(t_f), probe_id or ""),
            )
            conn.commit()

    # -- reads -----------------------------------------------------------------
    def count(self) -> int:
        row = self._conn().execute("SELECT COUNT(*) AS n FROM readings").fetchone()
        return int(row["n"]) if row else 0

    def latest(self) -> Optional[dict]:
        """Most recent reading overall, or None if the table is empty."""
        row = self._conn().execute(
            f"SELECT {_SELECT_COLS} FROM readings ORDER BY epoch DESC, id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def _cutoff(self, window_seconds: Optional[int]) -> Optional[int]:
        if not window_seconds:
            return None
        return int(time.time()) - int(window_seconds)

    def window_df(self, window_seconds: Optional[int] = None, max_points: int = 6000) -> pd.DataFrame:
        """Return readings within a rolling window as a DataFrame.

        When the window contains more than ``max_points`` rows the result is
        uniformly downsampled in SQL (``id % stride``) so the dashboard stays
        responsive even with millions of historical readings.  Statistics are
        computed separately on the full window via :meth:`window_stats`, so
        downsampling only affects plot density, never the reported min/max/avg.
        """
        conn = self._conn()
        cutoff = self._cutoff(window_seconds)
        where = "WHERE epoch >= ?" if cutoff is not None else ""
        params: tuple = (cutoff,) if cutoff is not None else ()

        total = conn.execute(f"SELECT COUNT(*) AS n FROM readings {where}", params).fetchone()["n"]
        if total == 0:
            return pd.DataFrame(columns=["timestamp", "temperature_c", "temperature_f", "probe_id"])

        stride = max(1, (total + max_points - 1) // max_points)
        if stride > 1:
            sample = "AND (id % ?) = 0" if cutoff is not None else "WHERE (id % ?) = 0"
            sql = f"SELECT {_SELECT_COLS} FROM readings {where} {sample} ORDER BY epoch ASC"
            rows = conn.execute(sql, params + (stride,)).fetchall()
        else:
            sql = f"SELECT {_SELECT_COLS} FROM readings {where} ORDER BY epoch ASC"
            rows = conn.execute(sql, params).fetchall()

        return pd.DataFrame([dict(r) for r in rows],
                            columns=["timestamp", "temperature_c", "temperature_f", "probe_id"])

    def window_stats(self, window_seconds: Optional[int] = None) -> dict:
        """Accurate min/max/avg/count over the full (un-downsampled) window."""
        conn = self._conn()
        cutoff = self._cutoff(window_seconds)
        where = "WHERE epoch >= ?" if cutoff is not None else ""
        params: tuple = (cutoff,) if cutoff is not None else ()

        agg = conn.execute(
            f"SELECT COUNT(*) AS n, MIN(temperature_c) AS mn, MAX(temperature_c) AS mx, "
            f"AVG(temperature_c) AS av FROM readings {where}",
            params,
        ).fetchone()
        if not agg or not agg["n"]:
            return {"count": 0, "min": None, "max": None, "avg": None,
                    "min_ts": None, "max_ts": None}

        min_ts = conn.execute(
            f"SELECT ts FROM readings {where} ORDER BY temperature_c ASC, epoch ASC LIMIT 1", params
        ).fetchone()
        max_ts = conn.execute(
            f"SELECT ts FROM readings {where} ORDER BY temperature_c DESC, epoch ASC LIMIT 1", params
        ).fetchone()
        return {
            "count": int(agg["n"]),
            "min": agg["mn"],
            "max": agg["mx"],
            "avg": agg["av"],
            "min_ts": min_ts["ts"] if min_ts else None,
            "max_ts": max_ts["ts"] if max_ts else None,
        }

    def latest_per_probe(self, window_seconds: Optional[int] = None) -> pd.DataFrame:
        """Latest reading for each probe within the window (for alert checks).

        Relies on SQLite's documented guarantee that, with ``GROUP BY`` and a
        ``MAX()`` aggregate, the bare columns come from the row holding that
        maximum — so each row returned is the newest reading per probe.
        """
        conn = self._conn()
        cutoff = self._cutoff(window_seconds)
        where = "WHERE epoch >= ?" if cutoff is not None else ""
        params: tuple = (cutoff,) if cutoff is not None else ()
        rows = conn.execute(
            f"SELECT {_SELECT_COLS}, MAX(epoch) AS _m FROM readings {where} GROUP BY probe_id",
            params,
        ).fetchall()
        return pd.DataFrame(
            [{"timestamp": r["timestamp"], "temperature_c": r["temperature_c"],
              "temperature_f": r["temperature_f"], "probe_id": r["probe_id"]} for r in rows],
            columns=["timestamp", "temperature_c", "temperature_f", "probe_id"],
        )

    # -- export ----------------------------------------------------------------
    def export_csv(self, file_obj, window_seconds: Optional[int] = None) -> int:
        """Write readings to a file-like object as CSV. Returns the row count."""
        conn = self._conn()
        cutoff = self._cutoff(window_seconds)
        where = "WHERE epoch >= ?" if cutoff is not None else ""
        params: tuple = (cutoff,) if cutoff is not None else ()
        writer = _csv.writer(file_obj)
        writer.writerow(["timestamp", "temperature_c", "temperature_f", "probe_id"])
        n = 0
        for r in conn.execute(
            f"SELECT ts, temperature_c, temperature_f, probe_id FROM readings {where} ORDER BY epoch ASC",
            params,
        ):
            writer.writerow([r["ts"], f"{r['temperature_c']:.3f}", f"{r['temperature_f']:.3f}", r["probe_id"]])
            n += 1
        return n


def migrate_csv_if_present(db: "Database", csv_path: str | Path) -> int:
    """One-time import of a legacy ``temperature_log.csv`` into the database.

    Runs only when the database is empty, so it is safe to call on every start.
    Returns the number of rows imported (0 if nothing to do).
    """
    csv_path = Path(csv_path)
    if not csv_path.exists() or db.count() > 0:
        return 0
    imported = 0
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                ts = (row.get("timestamp") or "").strip()
                if not ts:
                    continue
                try:
                    t_c = float(row.get("temperature_c"))
                except (TypeError, ValueError):
                    continue
                try:
                    t_f = float(row.get("temperature_f"))
                except (TypeError, ValueError):
                    t_f = (t_c * 9.0 / 5.0) + 32.0
                db.append(ts, t_c, t_f, (row.get("probe_id") or "").strip())
                imported += 1
    except Exception:
        return imported
    return imported

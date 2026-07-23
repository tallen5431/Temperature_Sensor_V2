"""SQLite-backed reading store for the Setpoint hub.

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
from typing import Iterable, Optional

import pandas as pd

# Columns exposed to the rest of the app.  ``timestamp`` is aliased from the
# ``ts`` column so existing dashboard code keeps working unchanged.
_SELECT_COLS = "ts AS timestamp, temperature_c, temperature_f, probe_id"


_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value) -> str:
    """Neutralise spreadsheet formula injection in an exported CSV cell.

    A cell that begins with ``= + - @`` (or a leading tab/CR) is treated as a
    formula by Excel/Sheets; prefixing it with a single quote makes it plain
    text. Applied to the free-form string columns of the export.
    """
    s = "" if value is None else str(value)
    if s and s[0] in _FORMULA_LEAD:
        return "'" + s
    return s


def _xlsx_safe(value) -> str:
    """Neutralise formula injection for a string written into an .xlsx cell.

    openpyxl treats a string that starts with ``=`` as a formula; the same
    single-quote guard used for CSV forces it to be stored as literal text. Only
    the rare free-form string that begins with a formula character is altered.
    """
    s = "" if value is None else str(value)
    if s and s[0] in _FORMULA_LEAD:
        return "'" + s
    return s


class ExportTooLargeForXlsx(Exception):
    """Raised when a requested .xlsx export would exceed Excel's row limit.

    Carries the actual and maximum row counts so the caller can tell the user to
    narrow the date range (or use the CSV export, which has no such limit).
    """

    def __init__(self, rows: int, max_rows: int):
        self.rows = rows
        self.max_rows = max_rows
        super().__init__(
            f"{rows:,} rows exceeds Excel's limit of {max_rows:,}; "
            f"narrow the date range or use a CSV export.")


def iso_to_epoch(ts: str) -> float:
    """Convert a local-naive ISO timestamp to a POSIX epoch (fractional seconds).

    Naive timestamps are interpreted as local machine time, matching how the
    rest of the app stores them.  Returns the current epoch if parsing fails so
    a malformed timestamp never blocks an insert.

    The value is a float so sub-second timestamps (high-rate logging) keep their
    precision. SQLite's flexible typing stores a whole-second epoch as an INTEGER
    (lossless) and a fractional one as REAL in the same ``epoch`` column, so this
    is backward-compatible with existing integer rows and the epoch index.
    """
    try:
        s = str(ts).strip().rstrip("Z")
        return datetime.datetime.fromisoformat(s).timestamp()
    except Exception:
        return time.time()


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
                    probe_id      TEXT    NOT NULL DEFAULT '',
                    humidity_pct  REAL,
                    vpd_kpa       REAL,
                    battery_pct   REAL
                )
                """
            )
            # Forward-migrate a pre-humidity/pre-battery database: ADD COLUMN is a
            # no-op error if the column already exists, so guard each one
            # independently.
            for col in ("humidity_pct", "vpd_kpa", "battery_pct"):
                try:
                    conn.execute(f"ALTER TABLE readings ADD COLUMN {col} REAL")
                except sqlite3.OperationalError:
                    pass  # column already present
            conn.execute("CREATE INDEX IF NOT EXISTS idx_readings_epoch ON readings(epoch)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_readings_probe_epoch ON readings(probe_id, epoch)"
            )
            # Alert-lifecycle event log (threshold breach/recovery, probe
            # offline/online, rate-of-change) — powers the dashboard's recent
            # events feed without re-deriving history from raw readings.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts            TEXT    NOT NULL,
                    epoch         INTEGER NOT NULL,
                    kind          TEXT    NOT NULL,
                    probe_id      TEXT    NOT NULL DEFAULT '',
                    temperature_c REAL,
                    limit_c       REAL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_epoch ON events(epoch)")
            conn.commit()

    # -- writes ----------------------------------------------------------------
    def append(self, ts: str, t_c: float, t_f: float, probe_id: str = "",
               humidity: float | None = None, vpd: float | None = None,
               battery: float | None = None) -> None:
        epoch = iso_to_epoch(ts)
        conn = self._conn()
        with self._write_lock:
            conn.execute(
                "INSERT INTO readings (ts, epoch, temperature_c, temperature_f, probe_id, "
                "humidity_pct, vpd_kpa, battery_pct) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(ts), epoch, float(t_c), float(t_f), probe_id or "",
                 (float(humidity) if humidity is not None else None),
                 (float(vpd) if vpd is not None else None),
                 (float(battery) if battery is not None else None)),
            )
            conn.commit()

    def record_event(self, kind: str, probe_id: str, temperature_c=None,
                     limit=None, ts=None) -> None:
        """Append one alert-lifecycle event to the events log.

        ``kind`` is one of ``'high' 'low' 'recovery' 'offline' 'online' 'rate'``;
        ``ts`` defaults to the current local time.  Best-effort by design: the
        alert cycle that emits an event must never be broken by an unrecordable
        one, so bad numeric fields are coerced to NULL, a blank kind is skipped,
        and any storage error is swallowed rather than raised to the caller.
        """
        def _f(v):
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None
        try:
            kind = str(kind or "").strip()
            if not kind:
                return  # nothing meaningful to record
            ts = str(ts) if ts else datetime.datetime.now().isoformat(timespec="seconds")
            conn = self._conn()
            with self._write_lock:
                conn.execute(
                    "INSERT INTO events (ts, epoch, kind, probe_id, temperature_c, limit_c) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (ts, int(iso_to_epoch(ts)), kind, str(probe_id or ""),
                     _f(temperature_c), _f(limit)),
                )
                conn.commit()
        except Exception:
            pass  # an event is telemetry — never worth failing the caller over

    def bulk_insert(self, rows) -> int:
        """Insert many ``(ts, t_c, t_f, probe_id)`` tuples in one transaction.

        Used for the legacy-CSV migration so importing tens of thousands of rows
        is a single commit rather than one per row.  Returns rows inserted.
        """
        params = [(str(ts), iso_to_epoch(ts), float(t_c), float(t_f), (pid or ""))
                  for (ts, t_c, t_f, pid) in rows]
        if not params:
            return 0
        conn = self._conn()
        with self._write_lock:
            conn.executemany(
                "INSERT INTO readings (ts, epoch, temperature_c, temperature_f, probe_id) "
                "VALUES (?, ?, ?, ?, ?)",
                params,
            )
            conn.commit()
        return len(params)

    # -- reads -----------------------------------------------------------------
    def count(self) -> int:
        row = self._conn().execute("SELECT COUNT(*) AS n FROM readings").fetchone()
        return int(row["n"]) if row else 0

    def has_any(self) -> bool:
        """True if the store holds at least one reading. ``EXISTS`` stops at the
        first row, so this is O(1) — unlike ``count()`` (a full scan) it is cheap
        to call on every dashboard tick just to test emptiness."""
        row = self._conn().execute("SELECT EXISTS(SELECT 1 FROM readings) AS e").fetchone()
        return bool(row and row["e"])

    def has_probe_prefix(self, prefix: str) -> bool:
        """True if any reading's ``probe_id`` starts with ``prefix``.

        The GLOB prefix pattern rewrites to a range seek on
        ``idx_readings_probe_epoch`` (verified via EXPLAIN QUERY PLAN in the
        tests), so answering "is demo data loaded?" on every settings render is
        O(log N) instead of scanning/grouping the whole readings table the way
        ``last_reading_epoch_per_probe`` does.  ``prefix`` is expected to be a
        plain probe-id token (no GLOB metacharacters).
        """
        if not prefix:
            return self.has_any()
        row = self._conn().execute(
            "SELECT EXISTS(SELECT 1 FROM readings WHERE probe_id GLOB ?) AS e",
            (str(prefix) + "*",),
        ).fetchone()
        return bool(row and row["e"])

    def latest(self) -> Optional[dict]:
        """Most recent reading overall, or None if the table is empty."""
        row = self._conn().execute(
            f"SELECT {_SELECT_COLS} FROM readings ORDER BY epoch DESC, id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def last_reading_epoch_per_probe(self, window_seconds: Optional[int] = None) -> dict:
        """Map ``probe_id -> epoch of its most recent reading`` within the window.

        Used for offline detection: a probe whose newest reading is older than
        the offline threshold has gone silent.  The window bounds which probes
        are tracked, so long-retired probes drop out instead of alerting forever.
        """
        conn = self._conn()
        cutoff = self._cutoff(window_seconds)
        where = "WHERE epoch >= ?" if cutoff is not None else ""
        params: tuple = (cutoff,) if cutoff is not None else ()
        rows = conn.execute(
            f"SELECT probe_id, MAX(epoch) AS last_epoch FROM readings {where} GROUP BY probe_id",
            params,
        ).fetchall()
        return {r["probe_id"]: int(r["last_epoch"]) for r in rows if r["probe_id"]}

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
            # Downsample by per-probe ROW POSITION, not by `id % stride`. Primary
            # keys are not contiguous (multiple writers interleave, delete_probe/
            # purge leave gaps), so `id % stride` biases the sample per probe and
            # can select ZERO rows (blank chart) or drop entire probes. Numbering
            # each probe's rows newest-first and keeping every stride-th one means
            # rn=1 (the live tip) is always kept, every probe is represented, and
            # the result is never empty. Point count stays near max_points (a
            # multi-probe window can exceed it by up to one point per probe —
            # bounded by the probe-registry cap and harmless for the chart).
            sql = (
                "SELECT timestamp, temperature_c, temperature_f, probe_id FROM ("
                "  SELECT ts AS timestamp, epoch, id, temperature_c, temperature_f, probe_id,"
                "         ROW_NUMBER() OVER (PARTITION BY probe_id ORDER BY epoch DESC, id DESC) AS rn"
                f"  FROM readings {where}"
                ") WHERE (rn - 1) % ? = 0 ORDER BY epoch ASC, id ASC"
            )
            rows = conn.execute(sql, params + (stride,)).fetchall()
        else:
            sql = f"SELECT {_SELECT_COLS} FROM readings {where} ORDER BY epoch ASC"
            rows = conn.execute(sql, params).fetchall()

        return pd.DataFrame([{"timestamp": r["timestamp"], "temperature_c": r["temperature_c"],
                              "temperature_f": r["temperature_f"], "probe_id": r["probe_id"]}
                             for r in rows],
                            columns=["timestamp", "temperature_c", "temperature_f", "probe_id"])

    def window_stats(self, window_seconds: Optional[int] = None,
                     probe_id: Optional[str] = None) -> dict:
        """Accurate min/max/avg/count over the full (un-downsampled) window.

        When ``probe_id`` is given, the stats cover only that probe — used by the
        dashboard's "focus one probe" mode so the min/max/avg describe the single
        selected probe instead of all probes mixed together.
        """
        conn = self._conn()
        cutoff = self._cutoff(window_seconds)
        clauses, params_list = [], []
        if cutoff is not None:
            clauses.append("epoch >= ?"); params_list.append(cutoff)
        if probe_id:
            clauses.append("probe_id = ?"); params_list.append(probe_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params: tuple = tuple(params_list)

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

    def stats_per_probe(self, window_seconds: Optional[int] = None) -> dict:
        """Per-probe min/max/avg/count over the full (un-downsampled) window.

        Returns ``{probe_id: {count, min, max, avg}}``. Used for the dashboard's
        per-probe statistics breakdown, where a single global average across
        probes of different ranges (a −18 °C freezer + a 22 °C room) would be
        meaningless. Rows with an empty ``probe_id`` are grouped under ``""``.
        """
        conn = self._conn()
        cutoff = self._cutoff(window_seconds)
        where = "WHERE epoch >= ?" if cutoff is not None else ""
        params: tuple = (cutoff,) if cutoff is not None else ()
        rows = conn.execute(
            f"SELECT probe_id, COUNT(*) AS n, MIN(temperature_c) AS mn, "
            f"MAX(temperature_c) AS mx, AVG(temperature_c) AS av "
            f"FROM readings {where} GROUP BY probe_id",
            params,
        ).fetchall()
        return {
            (r["probe_id"] or ""): {
                "count": int(r["n"]), "min": r["mn"], "max": r["mx"], "avg": r["av"],
            }
            for r in rows if r["n"]
        }

    def latest_per_probe(self, window_seconds: Optional[int] = None) -> pd.DataFrame:
        """Latest reading for each probe within the window (for alerts/display).

        Ties on ``epoch`` (two readings in the same second) are broken by
        insertion ``id`` so "latest" is always the most recently stored row.

        Implemented as per-probe index seeks on ``idx_readings_probe_epoch``:
        the distinct probe ids come straight off the index, then each probe's
        newest row is one backward ``ORDER BY epoch DESC LIMIT 1`` seek (``id``
        is the rowid, so the index order breaks epoch ties for free).  That is
        O(probes x log N) per call, replacing a ROW_NUMBER() window scan that
        touched every row in the window on every dashboard tick.
        """
        conn = self._conn()
        cutoff = self._cutoff(window_seconds)
        where = "WHERE epoch >= ?" if cutoff is not None else ""
        params: tuple = (cutoff,) if cutoff is not None else ()
        pids = [r["probe_id"] for r in conn.execute(
            f"SELECT DISTINCT probe_id FROM readings {where}", params).fetchall()]
        cols = ["timestamp", "temperature_c", "temperature_f", "probe_id",
                "humidity_pct", "vpd_kpa", "battery_pct"]
        epoch_clause = " AND epoch >= ?" if cutoff is not None else ""
        out = []
        for pid in pids:
            row = conn.execute(
                f"SELECT ts AS timestamp, temperature_c, temperature_f, probe_id, "
                f"humidity_pct, vpd_kpa, battery_pct FROM readings "
                f"WHERE probe_id = ?{epoch_clause} ORDER BY epoch DESC, id DESC LIMIT 1",
                (pid,) + params,
            ).fetchone()
            if row is not None:
                out.append({k: row[k] for k in cols})
        return pd.DataFrame(out, columns=cols)

    def fetch_readings(self, window_seconds: Optional[int] = None,
                       probe_id: Optional[str] = None,
                       start_epoch: Optional[int] = None,
                       end_epoch: Optional[int] = None,
                       limit: Optional[int] = None,
                       max_points: int = 6000) -> list:
        """Return readings as a list of dict rows for the JSON read API.

        Accepts the same filters as :meth:`export_csv` (a rolling
        ``window_seconds``, a single ``probe_id``, and an absolute
        ``start_epoch``/``end_epoch`` range, all AND-ed). Unlike
        :meth:`window_df` the rows include humidity and VPD. The result is
        bounded to at most ``limit`` (default ``max_points``, hard cap 50 000)
        of the most RECENT matching rows, returned oldest-first, so a
        months-long store can never emit an unbounded payload over the API.
        """
        conn = self._conn()
        clauses, params_list = [], []
        cutoff = self._cutoff(window_seconds)
        if cutoff is not None:
            clauses.append("epoch >= ?"); params_list.append(cutoff)
        if start_epoch is not None:
            clauses.append("epoch >= ?"); params_list.append(int(start_epoch))
        if end_epoch is not None:
            clauses.append("epoch <= ?"); params_list.append(int(end_epoch))
        if probe_id:
            clauses.append("probe_id = ?"); params_list.append(probe_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        try:
            cap = int(limit) if limit else int(max_points)
        except (TypeError, ValueError):
            cap = int(max_points)
        cap = max(1, min(cap, 50000))
        rows = conn.execute(
            f"SELECT ts AS timestamp, temperature_c, temperature_f, probe_id, "
            f"humidity_pct, vpd_kpa, battery_pct FROM readings {where} "
            f"ORDER BY epoch DESC, id DESC LIMIT ?",
            tuple(params_list) + (cap,),
        ).fetchall()
        out = [dict(r) for r in rows]
        out.reverse()  # oldest-first for charting/time-series consumers
        return out

    def list_events(self, limit: int = 50, window_seconds: Optional[int] = None,
                    kinds: Optional[Iterable[str]] = None,
                    exclude_kinds: Optional[Iterable[str]] = None) -> list:
        """Most recent alert-lifecycle events as dict rows, newest first.

        Row keys: ``timestamp, epoch, kind, probe_id, temperature_c, limit_c``.
        ``window_seconds`` bounds the log to a rolling window (index-backed via
        ``idx_events_epoch``); ``limit`` caps the payload for the UI/API.
        ``kinds`` restricts the result to those event kinds (whitelist);
        ``exclude_kinds`` drops them (blacklist). Filtering by kind *in SQL* —
        before the ``LIMIT`` — is what lets a caller pull, say, the newest N
        *alerts* without a flapping probe's online/offline churn evicting them
        from the fetch window.
        """
        conn = self._conn()
        cutoff = self._cutoff(window_seconds)
        clauses: list = []
        params: list = []
        if cutoff is not None:
            clauses.append("epoch >= ?")
            params.append(cutoff)
        kind_list = [str(k) for k in kinds] if kinds else None
        if kind_list:
            clauses.append(f"kind IN ({','.join('?' * len(kind_list))})")
            params.extend(kind_list)
        drop_list = [str(k) for k in exclude_kinds] if exclude_kinds else None
        if drop_list:
            clauses.append(f"kind NOT IN ({','.join('?' * len(drop_list))})")
            params.extend(drop_list)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        try:
            cap = max(1, int(limit))
        except (TypeError, ValueError):
            cap = 50
        rows = conn.execute(
            f"SELECT ts AS timestamp, epoch, kind, probe_id, temperature_c, limit_c "
            f"FROM events {where} ORDER BY epoch DESC, id DESC LIMIT ?",
            tuple(params) + (cap,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- maintenance -----------------------------------------------------------
    def purge_older_than(self, days: int) -> int:
        """Delete readings older than ``days`` days. Returns rows removed."""
        if not days or int(days) <= 0:
            return 0
        cutoff = int(time.time()) - int(days) * 86400
        conn = self._conn()
        with self._write_lock:
            cur = conn.execute("DELETE FROM readings WHERE epoch < ?", (cutoff,))
            conn.commit()
            return cur.rowcount

    def delete_future_readings(self, tolerance_sec: int = 120) -> int:
        """Delete readings stamped implausibly far in the future. Returns rows removed.

        A probe with a bad clock can stamp a reading ahead of real time (see the
        ingest-time clamp in core.storage). Any such row already in the store
        would draw the chart past 'now' and become the bogus 'latest' reading —
        masking a live threshold breach. Run once at startup so an existing
        database self-heals; new readings are clamped at ingest so none recur.
        """
        cutoff = int(time.time()) + int(tolerance_sec)
        conn = self._conn()
        with self._write_lock:
            cur = conn.execute("DELETE FROM readings WHERE epoch > ?", (cutoff,))
            conn.commit()
            return cur.rowcount

    def delete_probe(self, probe_id: str) -> int:
        """Delete every reading for a single probe. Returns rows removed.

        Used by "remove device" so a decommissioned/test probe's history stops
        showing up in the dashboard, stats and CSV export. An empty probe_id is
        a no-op guard so a blank id can't wipe the unlabelled bucket by accident.
        """
        pid = (probe_id or "").strip()
        if not pid:
            return 0
        conn = self._conn()
        with self._write_lock:
            cur = conn.execute("DELETE FROM readings WHERE probe_id = ?", (pid,))
            conn.commit()
            return cur.rowcount

    def backup(self, dest_path: str | Path) -> None:
        """Write a consistent snapshot of the database to ``dest_path``."""
        dest = sqlite3.connect(str(dest_path))
        try:
            with self._write_lock:
                self._conn().backup(dest)
        finally:
            dest.close()

    # -- export ----------------------------------------------------------------
    # Excel refuses to open a worksheet with more than 1,048,576 rows (including
    # the header); the friendly .xlsx export guards against this instead of
    # producing a file Excel silently truncates or rejects.
    XLSX_MAX_ROWS = 1_048_576

    def _export_where(self, window_seconds, probe_id, start_epoch, end_epoch):
        """Build the shared ``WHERE`` clause + params for every export variant.

        Filters (all AND-ed, any may be omitted): a rolling ``window_seconds``, a
        single ``probe_id``, and an absolute ``start_epoch``/``end_epoch`` range.
        """
        clauses, params_list = [], []
        cutoff = self._cutoff(window_seconds)
        if cutoff is not None:
            clauses.append("epoch >= ?"); params_list.append(cutoff)
        if start_epoch is not None:
            clauses.append("epoch >= ?"); params_list.append(int(start_epoch))
        if end_epoch is not None:
            clauses.append("epoch <= ?"); params_list.append(int(end_epoch))
        if probe_id:
            clauses.append("probe_id = ?"); params_list.append(probe_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, tuple(params_list)

    @staticmethod
    def _utc_string(epoch) -> str:
        """Format a row's epoch as an unambiguous ISO-8601 UTC string.

        Carries millisecond precision when the row has it (sub-second/high-rate
        logging), else keeps the clean seconds format.
        """
        utc_dt = datetime.datetime.fromtimestamp(float(epoch), tz=datetime.timezone.utc)
        if utc_dt.microsecond:
            return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc_dt.microsecond // 1000:03d}Z"
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _local_date_time(ts, epoch):
        """Split a row into ``(date, time)`` objects in the hub's local wall clock.

        Prefers the stored local ISO ``ts`` (what the probe/hub recorded); falls
        back to the epoch in local time if ``ts`` is malformed. Seconds
        resolution — sub-second precision is preserved in the UTC column.
        """
        try:
            dt = datetime.datetime.fromisoformat(str(ts).replace("Z", ""))
        except (ValueError, TypeError):
            dt = datetime.datetime.fromtimestamp(float(epoch))
        return dt.date(), dt.time().replace(microsecond=0)

    def export_csv(self, file_obj, window_seconds: Optional[int] = None,
                   probe_id: Optional[str] = None,
                   start_epoch: Optional[int] = None,
                   end_epoch: Optional[int] = None) -> int:
        """Write readings to a file-like object as CSV. Returns the row count.

        This is the canonical/system-of-record export: ISO-8601 timestamps and
        every column, unchanged. Every row carries both the stored local
        ``timestamp`` and an unambiguous ``timestamp_utc`` derived from the row's
        epoch, so exported data stays correct across machines and DST changes.
        """
        conn = self._conn()
        where, params = self._export_where(window_seconds, probe_id, start_epoch, end_epoch)
        writer = _csv.writer(file_obj)
        writer.writerow(["timestamp", "timestamp_utc", "temperature_c", "temperature_f",
                         "probe_id", "humidity_pct", "vpd_kpa"])
        n = 0
        for r in conn.execute(
            f"SELECT ts, epoch, temperature_c, temperature_f, probe_id, humidity_pct, vpd_kpa "
            f"FROM readings {where} ORDER BY epoch ASC",
            params,
        ):
            hum = "" if r["humidity_pct"] is None else f"{r['humidity_pct']:.2f}"
            vpd = "" if r["vpd_kpa"] is None else f"{r['vpd_kpa']:.3f}"
            writer.writerow([_csv_safe(r["ts"]), self._utc_string(r["epoch"]),
                             f"{r['temperature_c']:.3f}", f"{r['temperature_f']:.3f}",
                             _csv_safe(r["probe_id"]), hum, vpd])
            n += 1
        return n

    # Column headers shared by the two Excel-friendly variants (CSV + .xlsx).
    _FRIENDLY_HEADERS = ["date", "time", "probe", "temperature_c", "temperature_f",
                         "probe_id", "timestamp_utc"]

    def export_friendly_csv(self, file_obj, name_map: Optional[dict] = None,
                            window_seconds: Optional[int] = None,
                            probe_id: Optional[str] = None,
                            start_epoch: Optional[int] = None,
                            end_epoch: Optional[int] = None) -> int:
        """Write an Excel-friendly CSV. Returns the row count.

        Same filters as :meth:`export_csv`, but reshaped for people who open the
        file directly in a spreadsheet:

        * ``date`` and ``time`` are split into separate columns (local wall
          clock) so Excel/Sheets parse each as a real date/time value and sort,
          filter and pivot natively — an ISO ``...T...``-with-milliseconds string
          is imported as text and won't.
        * ``probe`` shows the friendly name set in the dashboard (``name_map``),
          with the raw ``probe_id`` kept alongside for disambiguation.
        * the unused ``humidity_pct``/``vpd_kpa`` columns are dropped as noise.
        * ``timestamp_utc`` is retained (full precision) so the exact,
          machine-independent instant is never lost.
        """
        names = name_map or {}
        conn = self._conn()
        where, params = self._export_where(window_seconds, probe_id, start_epoch, end_epoch)
        writer = _csv.writer(file_obj)
        writer.writerow(self._FRIENDLY_HEADERS)
        n = 0
        for r in conn.execute(
            f"SELECT ts, epoch, temperature_c, temperature_f, probe_id "
            f"FROM readings {where} ORDER BY epoch ASC",
            params,
        ):
            d, t = self._local_date_time(r["ts"], r["epoch"])
            pid = r["probe_id"] or ""
            friendly = names.get(pid, pid) if isinstance(names, dict) else pid
            writer.writerow([d.isoformat(), t.isoformat(), _csv_safe(friendly),
                             f"{r['temperature_c']:.3f}", f"{r['temperature_f']:.3f}",
                             _csv_safe(pid), self._utc_string(r["epoch"])])
            n += 1
        return n

    def count_readings(self, window_seconds: Optional[int] = None,
                       probe_id: Optional[str] = None,
                       start_epoch: Optional[int] = None,
                       end_epoch: Optional[int] = None) -> int:
        """Count readings matching the export filters (used for the .xlsx guard)."""
        conn = self._conn()
        where, params = self._export_where(window_seconds, probe_id, start_epoch, end_epoch)
        row = conn.execute(f"SELECT COUNT(*) AS n FROM readings {where}", params).fetchone()
        return int(row["n"]) if row else 0

    def export_xlsx(self, file_obj, name_map: Optional[dict] = None,
                    window_seconds: Optional[int] = None,
                    probe_id: Optional[str] = None,
                    start_epoch: Optional[int] = None,
                    end_epoch: Optional[int] = None) -> int:
        """Write a native .xlsx workbook. Returns the row count.

        Same reshaped columns as :meth:`export_friendly_csv`, but as a real Excel
        file so ``date``/``time`` are true date/time cells and the temperatures
        are real numbers — the user double-clicks and everything is already
        typed, sorted, filterable (auto-filter) with a frozen header row.

        Streams via openpyxl's ``write_only`` mode so a long log doesn't buffer
        in memory. Raises :class:`ExportTooLargeForXlsx` when the result would
        exceed Excel's row limit (the caller should offer CSV instead), and
        ``ImportError`` if openpyxl isn't installed.
        """
        from openpyxl import Workbook  # lazy: optional dependency
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter

        names = name_map or {}
        total = self.count_readings(window_seconds, probe_id, start_epoch, end_epoch)
        if total > self.XLSX_MAX_ROWS - 1:  # -1 leaves room for the header row
            raise ExportTooLargeForXlsx(total, self.XLSX_MAX_ROWS - 1)

        wb = Workbook(write_only=True)
        ws = wb.create_sheet("Readings")
        ws.freeze_panes = "A2"  # keep the header visible while scrolling
        widths = [12, 11, 22, 15, 15, 20, 26]
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        # Filter dropdowns over the whole populated table (header + data rows).
        ws.auto_filter.ref = f"A1:{get_column_letter(len(self._FRIENDLY_HEADERS))}{total + 1}"

        bold = Font(bold=True)
        header = []
        for label in self._FRIENDLY_HEADERS:
            c = WriteOnlyCell(ws, value=label)
            c.font = bold
            header.append(c)
        ws.append(header)

        conn = self._conn()
        where, params = self._export_where(window_seconds, probe_id, start_epoch, end_epoch)
        n = 0
        for r in conn.execute(
            f"SELECT ts, epoch, temperature_c, temperature_f, probe_id "
            f"FROM readings {where} ORDER BY epoch ASC",
            params,
        ):
            d, t = self._local_date_time(r["ts"], r["epoch"])
            pid = r["probe_id"] or ""
            friendly = names.get(pid, pid) if isinstance(names, dict) else pid
            date_cell = WriteOnlyCell(ws, value=d)
            date_cell.number_format = "yyyy-mm-dd"
            time_cell = WriteOnlyCell(ws, value=t)
            time_cell.number_format = "hh:mm:ss"
            c_cell = WriteOnlyCell(ws, value=round(float(r["temperature_c"]), 3))
            c_cell.number_format = "0.000"
            f_cell = WriteOnlyCell(ws, value=round(float(r["temperature_f"]), 3))
            f_cell.number_format = "0.000"
            ws.append([date_cell, time_cell, _xlsx_safe(friendly),
                       c_cell, f_cell, _xlsx_safe(pid), self._utc_string(r["epoch"])])
            n += 1
        wb.save(file_obj)
        return n


def migrate_csv_if_present(db: "Database", csv_path: str | Path) -> int:
    """One-time import of a legacy ``temperature_log.csv`` into the database.

    Runs only when the database is empty, so it is safe to call on every start.
    Returns the number of rows imported (0 if nothing to do).
    """
    csv_path = Path(csv_path)
    if not csv_path.exists() or db.count() > 0:
        return 0
    rows = []
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
                rows.append((ts, t_c, t_f, (row.get("probe_id") or "").strip()))
        return db.bulk_insert(rows)
    except Exception:
        # Partial import is still useful; insert whatever parsed cleanly.
        return db.bulk_insert(rows)

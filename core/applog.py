# core/applog.py
"""Application logging for an unattended 24/7 appliance.

The old code was littered with bare ``except Exception: pass`` which hides the
single worst failure mode for a temperature monitor: silent write failure (disk
full, permission loss) where the customer believes logging is fine while nothing
is recorded. This wires a rotating file log plus console output so field
incidents are diagnosable, and exposes lightweight health counters that
``GET /api/health`` surfaces.
"""
from __future__ import annotations

import logging
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

_configured = False
_lock = threading.Lock()


def setup_logging(log_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """Configure the root 'tempsensor' logger once. Safe to call repeatedly."""
    global _configured
    with _lock:
        logger = logging.getLogger("tempsensor")
        if _configured:
            return logger
        logger.setLevel(level)
        fmt = logging.Formatter(
            "%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console = logging.StreamHandler()
        console.setFormatter(fmt)
        logger.addHandler(console)

        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            fileh = RotatingFileHandler(
                log_dir / "tempsensor.log",
                maxBytes=2_000_000,
                backupCount=5,
                encoding="utf-8",
            )
            fileh.setFormatter(fmt)
            logger.addHandler(fileh)
        except Exception:
            # A missing log dir must never stop the product from running.
            logger.warning("Could not open log file in %s; console logging only", log_dir)

        logger.propagate = False
        _configured = True
        return logger


def get_logger(name: str = "tempsensor") -> logging.Logger:
    return logging.getLogger(name if name.startswith("tempsensor") else f"tempsensor.{name}")


class HealthState:
    """Thread-safe counters describing whether the appliance is actually healthy.

    Exposed via GET /api/health so a monitoring dashboard (or the maker's
    support team) can tell at a glance if writes are flowing.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.rows_written = 0
        self.ingest_rejected = 0
        self.write_failures = 0
        self.last_write_ts: float | None = None

    def record_write(self) -> None:
        with self._lock:
            self.rows_written += 1
            self.last_write_ts = time.time()

    def record_reject(self) -> None:
        with self._lock:
            self.ingest_rejected += 1

    def record_failure(self) -> None:
        with self._lock:
            self.write_failures += 1

    def snapshot(self) -> dict:
        with self._lock:
            last = self.last_write_ts
            age = (time.time() - last) if last else None
            return {
                "rows_written": self.rows_written,
                "ingest_rejected": self.ingest_rejected,
                "write_failures": self.write_failures,
                "last_write_age_sec": round(age, 1) if age is not None else None,
                "healthy": bool(last and age is not None and age < 120 and self.write_failures == 0),
            }


# A single process-wide health object other modules can import.
HEALTH = HealthState()

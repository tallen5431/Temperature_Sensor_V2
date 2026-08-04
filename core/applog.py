# core/applog.py
"""Application logging for an unattended 24/7 appliance.

The old code was littered with bare ``except Exception: pass`` which hides the
single worst failure mode for a temperature monitor: silent write failure (disk
full, permission loss) where the customer believes logging is fine while nothing
is recorded. This module exposes the lightweight health counters that
``GET /api/health`` and the Diagnostics page surface, plus the logger factory
every module uses.

Handler wiring lives in :mod:`core.logging_setup`, which ``app.py`` calls once at
startup for the ``hub`` tree. This module used to carry a second, unreferenced
configurator for a ``setpoint`` tree writing to its own ``setpoint.log`` — dead
code that, had anything called it, would have split the log across two files.
"""
from __future__ import annotations

import logging
import threading
import time


def get_logger(name: str = "hub") -> logging.Logger:
    """Return a logger under the ``hub`` tree that ``configure_logging`` wires to
    the console + rotating file handler.

    Historically this returned ``setpoint.*`` loggers, but that tree was never
    configured, so records from the api/audit/mqtt modules (which use this
    helper) were silently dropped and never reached the on-disk hub.log. Routing
    them under ``hub`` puts them in the single configured tree with every other
    module, so field incidents are actually diagnosable from the log file.
    """
    return logging.getLogger(name if name.startswith("hub") else f"hub.{name}")


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
        self.last_failure_ts: float | None = None
        # Rejected-for-auth count. A probe holding a stale device token (the hub
        # regenerated it, or config.json was recreated) 401s on every wake and
        # buffers forever. Without a counter that is indistinguishable from "hub
        # down" on the probe and completely invisible on the hub — the Devices
        # grid just shows it offline with no reason. Surfaced in /api/health and
        # /api/diagnostics so the cause is findable.
        self.unauthorized = 0
        self.last_unauthorized_ts: float | None = None
        # Notifications that never reached anyone. Alerting is the product's
        # promise, so a silently-undelivered alert is its worst failure: the
        # dashboard still shows the breach, the event log still records it, and
        # the operator reasonably concludes they were told. Two distinct causes,
        # counted separately because they mean different things — `failed` is a
        # channel problem (SMTP down, webhook 500, bad credentials), `dropped` is
        # back-pressure, the dispatch queue filling because sends are slower than
        # events arrive. Surfaced in /api/health and /api/diagnostics.
        self.notify_failures = 0
        self.notify_dropped = 0
        self.last_notify_failure_ts: float | None = None

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
            self.last_failure_ts = time.time()

    def record_unauthorized(self) -> int:
        """Count one auth-rejected API request. Returns the running total."""
        with self._lock:
            self.unauthorized += 1
            self.last_unauthorized_ts = time.time()
            return self.unauthorized

    def record_notify_failure(self, n: int = 1) -> None:
        """Count notification(s) a channel accepted but failed to deliver."""
        if n <= 0:
            return
        with self._lock:
            self.notify_failures += n
            self.last_notify_failure_ts = time.time()

    def record_notify_dropped(self) -> None:
        """Count one event discarded because the dispatch queue was full."""
        with self._lock:
            self.notify_dropped += 1
            self.last_notify_failure_ts = time.time()

    def snapshot(self, fresh_window_sec: float = 120) -> dict:
        """Health counters plus the derived ``healthy`` flag.

        ``fresh_window_sec`` bounds how old the newest successful write may be
        before the appliance counts as unhealthy; callers monitoring slow-cadence
        probes can pass an interval-aware bound instead of the 120 s default.
        A write failure no longer latches the flag forever: only a failure NEWER
        than the latest successful write marks the appliance unhealthy, so one
        transient hiccup months ago cannot condemn a recovered system.
        """
        with self._lock:
            last = self.last_write_ts
            age = (time.time() - last) if last else None
            failing = (self.last_failure_ts is not None
                       and (last is None or self.last_failure_ts > last))
            unauth_age = ((time.time() - self.last_unauthorized_ts)
                          if self.last_unauthorized_ts else None)
            notify_age = ((time.time() - self.last_notify_failure_ts)
                          if self.last_notify_failure_ts else None)
            return {
                "rows_written": self.rows_written,
                "ingest_rejected": self.ingest_rejected,
                "write_failures": self.write_failures,
                "unauthorized": self.unauthorized,
                "last_unauthorized_age_sec": (round(unauth_age, 1)
                                              if unauth_age is not None else None),
                "notify_failures": self.notify_failures,
                "notify_dropped": self.notify_dropped,
                "last_notify_failure_age_sec": (round(notify_age, 1)
                                                if notify_age is not None else None),
                "last_write_age_sec": round(age, 1) if age is not None else None,
                "healthy": bool(last and age is not None and age < fresh_window_sec
                                and not failing),
            }


# A single process-wide health object other modules can import.
HEALTH = HealthState()

# Wall-clock time the process started, for an uptime readout on the health panel.
PROCESS_START = time.time()

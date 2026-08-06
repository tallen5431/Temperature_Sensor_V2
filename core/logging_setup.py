"""Centralised logging configuration.

Call :func:`configure_logging` once at startup.  Modules obtain loggers via
``logging.getLogger("hub.<area>")``.  A rotating file handler keeps a bounded
on-disk history so field issues can be diagnosed from a customer's log file.
"""
from __future__ import annotations

import logging
import logging.handlers
import time
from pathlib import Path
from typing import Optional

# Seconds between "the request queue is backing up" notices. Waitress logs one
# per request while its worker pool is saturated, and saturation is a sustained
# condition, so the raw stream is one line per request for as long as it lasts.
QUEUE_NOTICE_INTERVAL_SEC = 300


class _ThrottledQueueDepth(logging.Filter):
    """Let waitress say the queue is backing up — but once, not per request.

    A burst that saturates the worker pool (twenty probes draining buffered
    readings at once after an outage, which is exactly when an operator is
    already anxious) makes ``waitress.queue`` log a WARNING for every queued
    request. A 45-second synthetic burst produced 13,383 of them against 404
    real hub lines: a 33:1 flood that buries the log, in the ordinary format of
    a library the customer has never heard of, describing successful
    backpressure — nothing failed in that run.

    The same problem `probe_discovery._quiet_zeroconf_cache_race` solves for
    zeroconf, and the same answer: keep the signal, drop the repetition. The
    first notice in each interval passes; the rest are dropped. Every other
    waitress record is untouched, so a real serving error is never hidden.
    """

    def __init__(self, interval_sec: float = QUEUE_NOTICE_INTERVAL_SEC, clock=None):
        super().__init__()
        self.interval = float(interval_sec)
        # None means "nothing emitted yet", NOT "emitted at time zero". Seeding
        # this to 0.0 compared against time.monotonic(), which counts from system
        # boot — so on a machine less than `interval` seconds up, the very first
        # notice was silently swallowed. That is precisely a hub configured to
        # start on boot or login: the one moment it is most likely to be
        # saturated (every probe rejoining at once) is the moment the warning
        # would not have been shown.
        self._last: float | None = None
        self._suppressed = 0
        self._clock = clock or time.monotonic

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "waitress.queue":
            return True
        now = self._clock()
        if self._last is not None and now - self._last < self.interval:
            self._suppressed += 1
            return False
        if self._suppressed:
            record.msg = (f"{record.getMessage()} (and {self._suppressed:,} more "
                          f"like it in the last {int(self.interval / 60)} min — "
                          f"the hub is keeping up but requests are queuing)")
            record.args = ()
            self._suppressed = 0
        self._last = now
        return True


def configure_logging(log_dir: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    root = logging.getLogger("hub")
    if getattr(root, "_configured", False):
        return root

    root.setLevel(level)
    root.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    if log_dir:
        try:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                Path(log_dir) / "hub.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
            file_handler.setFormatter(fmt)
            root.addHandler(file_handler)
        except Exception as e:  # noqa: BLE001
            root.warning("file logging disabled: %s", e)

    # Waitress logs to its own top-level logger, so its records reached the
    # console through the root logger's default handling — in a different format
    # from every hub line, and NOT into logs/hub.log, which is the file a
    # customer is asked to send to support. Adopt it into the hub's handlers so
    # it is formatted and retained like everything else, throttled so the
    # queue-depth stream cannot bury the log it now shares.
    waitress = logging.getLogger("waitress")
    waitress.handlers.clear()
    waitress.propagate = False
    waitress.setLevel(level)
    for handler in root.handlers:
        waitress.addHandler(handler)
    # On `waitress.queue` itself, NOT on its parent. A logger's filters run in
    # its own handle(); a record from a child only visits an ancestor's
    # HANDLERS. Attached one level up this would have been inert, and the flood
    # would have carried on through a fix that looked right.
    queue_logger = logging.getLogger("waitress.queue")
    # Loggers are process-global and survive a re-configure, so adding blindly
    # would stack a second throttle whose independent interval lets twice as
    # much through.
    if not any(isinstance(f, _ThrottledQueueDepth) for f in queue_logger.filters):
        queue_logger.addFilter(_ThrottledQueueDepth())

    root._configured = True  # type: ignore[attr-defined]
    return root

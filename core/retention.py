# core/retention.py
"""Background maintenance that keeps the temperature log bounded.

Runs shortly after startup and then on a slow period (default hourly). Reads its
policy from config each cycle so changes take effect without a restart. All the
real work (and the write-lock) lives in core.storage.apply_retention.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from core.applog import get_logger
from core.storage import apply_retention

log = get_logger("retention")


class RetentionManager(threading.Thread):
    def __init__(self, csv_path: Path, cfg, period_sec: int = 3600):
        super().__init__(daemon=True)
        self.csv_path = Path(csv_path)
        self.cfg = cfg
        self.period_sec = int(period_sec)
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def _run_once(self) -> None:
        rcfg = self.cfg.get("retention", {}) or {}
        if not rcfg.get("enabled", True):
            return
        try:
            before, after = apply_retention(
                self.csv_path,
                raw_days=int(rcfg.get("raw_days", 14)),
                downsample_days=int(rcfg.get("downsample_days", 365)),
                interval_min=int(rcfg.get("downsample_interval_min", 15)),
            )
            if after < before:
                try:
                    from core.audit import AUDIT
                    AUDIT.record("data.retention", detail=f"{before}->{after} rows")
                except Exception:
                    pass
        except Exception as e:
            log.warning("retention cycle failed: %s", e)

    def run(self) -> None:
        # Small initial delay so startup isn't competing with the first reads.
        if self._stop.wait(30):
            return
        while not self._stop.is_set():
            self._run_once()
            self._stop.wait(self.period_sec)

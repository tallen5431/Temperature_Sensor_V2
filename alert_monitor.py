"""Background thread that evaluates threshold alerts and runs DB maintenance.

This runs independently of the dashboard, so notifications fire even when no
browser is open — which is the whole point of an alerting product.  It also
applies the data-retention policy on a slow cadence.
"""
from __future__ import annotations

import logging
import threading
import time

from core.alerts import evaluate, evaluate_offline, format_event
from core.notifications import Notifier

log = logging.getLogger("hub.alert_monitor")

# Track probes for offline detection if they reported within this window. Bounds
# the set so long-retired probes don't alert forever.
OFFLINE_MONITOR_WINDOW_SEC = 86400


class AlertMonitor(threading.Thread):
    def __init__(self, db, cfg, notifier=None, period_sec: int = 30):
        super().__init__(daemon=True)
        self.db = db
        self.cfg = cfg
        self.notifier = notifier or Notifier(cfg)
        self.period_sec = int(period_sec)
        self._stop = threading.Event()
        self._states: dict = {}
        self._offline_states: dict = {}
        self._offline_seeded = False
        self._last_purge = 0.0

    def stop(self):
        self._stop.set()

    def _readings(self) -> dict:
        """Latest reading per probe, limited to recent data so we don't alert on
        a stale value from a probe that has gone offline."""
        freshness = int(self.cfg.get("alert_freshness_sec", 600) or 600)
        df = self.db.latest_per_probe(window_seconds=freshness)
        out = {}
        for _, row in df.iterrows():
            pid = row["probe_id"]
            if pid is None or str(pid).strip() == "":
                continue
            try:
                out[pid] = float(row["temperature_c"])
            except (TypeError, ValueError):
                continue
        return out

    def check_once(self) -> list:
        conf = self.cfg.get("notifications", {}) or {}
        if not conf.get("enabled"):
            # Reset so re-enabling re-alerts current breaches; re-seed offline.
            self._states = {}
            self._offline_states = {}
            self._offline_seeded = False
            return []

        names = self.cfg.get("probe_names", {}) or {}
        all_events: list = []

        # --- threshold alerts ---
        thresholds = self.cfg.get("alert_thresholds", {}) or {}
        readings = self._readings()
        events, self._states = evaluate(
            readings, thresholds, self._states,
            cooldown_sec=int(conf.get("cooldown_sec", 1800) or 1800),
            notify_recovery=bool(conf.get("notify_recovery", True)),
        )
        all_events.extend(events)

        # --- offline / back-online alerts ---
        if conf.get("offline_alerts", True):
            all_events.extend(self._check_offline())

        for ev in all_events:
            subject, message = format_event(ev, names)
            self.notifier.dispatch({**ev, "subject": subject, "message": message})
        return all_events

    def _check_offline(self) -> list:
        try:
            offline_after = int(self.cfg.get("offline_after_sec", 300) or 300)
        except (TypeError, ValueError):
            offline_after = 300
        last_epochs = self.db.last_reading_epoch_per_probe(window_seconds=OFFLINE_MONITOR_WINDOW_SEC)
        events, self._offline_states = evaluate_offline(
            last_epochs, self._offline_states, offline_after_sec=offline_after)
        # The first cycle just records current state so we don't emit a burst of
        # "offline" for probes that were already silent when the hub started.
        if not self._offline_seeded:
            self._offline_seeded = True
            return []
        return events

    def maybe_purge(self):
        try:
            days = int(self.cfg.get("retention_days", 0) or 0)
        except (TypeError, ValueError):
            days = 0
        if days <= 0:
            return
        now = time.time()
        if now - self._last_purge < 3600:  # at most hourly
            return
        self._last_purge = now
        try:
            removed = self.db.purge_older_than(days)
            if removed:
                log.info("retention: purged %d reading(s) older than %d days", removed, days)
        except Exception as e:  # noqa: BLE001
            log.warning("retention purge failed: %s", e)

    def run(self):
        log.info("alert monitor started (checking every %s s)", self.period_sec)
        while not self._stop.is_set():
            try:
                self.check_once()
                self.maybe_purge()
            except Exception as e:  # noqa: BLE001
                log.warning("alert monitor cycle error: %s", e)
            self._stop.wait(self.period_sec)

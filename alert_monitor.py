"""Background thread that evaluates threshold alerts and runs DB maintenance.

This runs independently of the dashboard, so notifications fire even when no
browser is open — which is the whole point of an alerting product.  It also
applies the data-retention policy on a slow cadence.
"""
from __future__ import annotations

import logging
import queue
import threading
import time

from core.alerts import evaluate, evaluate_offline, format_event
from core.notifications import Notifier

log = logging.getLogger("hub.alert_monitor")

# Track probes for offline detection if they reported within this window. Bounds
# the set so long-retired probes don't alert forever.
OFFLINE_MONITOR_WINDOW_SEC = 86400


class AlertMonitor(threading.Thread):
    def __init__(self, db, cfg, notifier=None, period_sec: int = 30, discovery=None):
        super().__init__(daemon=True)
        self.db = db
        self.cfg = cfg
        self.notifier = notifier or Notifier(cfg)
        self.period_sec = int(period_sec)
        # Optional discovery handle so registry pruning runs on this always-on
        # thread — otherwise prune only happens when the auto-provisioner is on.
        self.discovery = discovery
        self._stop_event = threading.Event()
        self._states: dict = {}
        self._offline_states: dict = {}
        self._offline_seeded = False
        self._last_purge = 0.0
        self._last_prune = 0.0
        # Notifications are sent on a dedicated worker so a slow/black-holed SMTP
        # or webhook (whose timeouts don't even bound DNS resolution) can't stall
        # alert evaluation, offline detection, and retention on the monitor loop.
        self._notify_q: "queue.Queue" = queue.Queue(maxsize=500)
        self._notify_thread: threading.Thread | None = None

    def stop(self):
        self._stop_event.set()
        # Non-blocking: if the queue is full (worker wedged on a slow SMTP send),
        # don't block shutdown — the worker also exits on _stop_event.
        try:
            self._notify_q.put_nowait(None)  # unblock the dispatch worker
        except queue.Full:
            pass

    def _dispatch(self, ev: dict) -> None:
        """Hand an event to the async worker when the monitor is running; fall
        back to an inline send when called directly (e.g. unit tests) so the
        behaviour stays synchronous and observable there."""
        if self._notify_thread and self._notify_thread.is_alive():
            try:
                self._notify_q.put_nowait(ev)
            except queue.Full:
                log.warning("notification queue full; dropping %s alert for %s",
                            ev.get("kind"), ev.get("probe_id"))
        else:
            self.notifier.dispatch(ev)

    def _dispatch_loop(self) -> None:
        while True:
            ev = self._notify_q.get()
            if ev is None:  # sentinel from stop()
                return
            try:
                self.notifier.dispatch(ev)
            except Exception as e:  # noqa: BLE001 - a channel error must not kill the worker
                log.warning("notification dispatch error: %s", e)

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
            hysteresis=self._hysteresis(),
        )
        all_events.extend(events)

        # --- offline / back-online alerts ---
        if conf.get("offline_alerts", True):
            all_events.extend(self._check_offline())

        for ev in all_events:
            subject, message = format_event(ev, names)
            self._dispatch({**ev, "subject": subject, "message": message})
        return all_events

    def _hysteresis(self) -> float:
        """Deadband (°C) a probe must clear before a breach is considered over —
        stops a noisy sensor at the limit from flapping high→ok→high."""
        try:
            return max(0.0, float(self.cfg.get("alert_hysteresis_c", 0.5)))
        except (TypeError, ValueError):
            return 0.5

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

    def maybe_prune_probes(self):
        """Evict long-gone probes from the discovery registry on a slow cadence,
        independent of whether the auto-provisioner is running."""
        if self.discovery is None or not hasattr(self.discovery, "prune_stale"):
            return
        now = time.time()
        if now - self._last_prune < 3600:  # at most hourly
            return
        self._last_prune = now
        try:
            after = int(self.cfg.get("probe_prune_after_sec", 3600) or 3600)
            self.discovery.prune_stale(after)
        except Exception as e:  # noqa: BLE001
            log.warning("probe prune failed: %s", e)

    def run(self):
        log.info("alert monitor started (checking every %s s)", self.period_sec)
        self._notify_thread = threading.Thread(
            target=self._dispatch_loop, name="alert-dispatch", daemon=True)
        self._notify_thread.start()
        while not self._stop_event.is_set():
            try:
                self.check_once()
                self.maybe_purge()
                self.maybe_prune_probes()
            except Exception as e:  # noqa: BLE001
                log.warning("alert monitor cycle error: %s", e)
            self._stop_event.wait(self.period_sec)
        self._notify_q.put(None)  # ensure the worker exits even without stop()

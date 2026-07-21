"""Background thread that evaluates threshold alerts and runs DB maintenance.

This runs independently of the dashboard, so notifications fire even when no
browser is open — which is the whole point of an alerting product.  It also
applies the data-retention policy on a slow cadence.
"""
from __future__ import annotations

import datetime
import logging
import queue
import threading
import time

from core.alerts import HELD, evaluate, evaluate_offline, evaluate_rate, format_event
from core.notifications import Notifier, send_email
from core.status import probe_fresh_window

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
        self._rate_states: dict = {}
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
        # Evaluation, the durable event log and the held-breach registry always
        # run so the dashboard stays truthful even with notifications switched
        # off — only Notifier dispatch is gated on the master switch.
        conf = self.cfg.get("notifications", {}) or {}
        notify = bool(conf.get("enabled"))
        cooldown = int(conf.get("cooldown_sec", 1800) or 1800)

        names = self.cfg.get("probe_names", {}) or {}
        all_events: list = []

        # --- threshold alerts ---
        thresholds = self.cfg.get("alert_thresholds", {}) or {}
        readings = self._readings()
        events, self._states = evaluate(
            readings, thresholds, self._states,
            cooldown_sec=cooldown,
            notify_recovery=bool(conf.get("notify_recovery", True)),
            hysteresis=self._hysteresis(),
        )
        all_events.extend(events)

        # --- rate-of-change alerts ---
        all_events.extend(self._check_rate(readings, cooldown))

        # --- offline / back-online alerts ---
        if conf.get("offline_alerts", True):
            all_events.extend(self._check_offline())

        # Publish which probes are currently held in a breach so the dashboard
        # can explain a banner that outlives the raw limit (hysteresis hold).
        HELD.set_states({pid: st.get("condition") for pid, st in self._states.items()
                         if st.get("condition") in ("high", "low")})

        for ev in all_events:
            # State TRANSITIONS go to the durable event log; threshold cooldown
            # reminders do not (one sustained problem would flood it with
            # duplicates). Rate events are already cooldown-bounded, so every
            # emitted one is recorded.
            if ev.get("kind") == "rate" or ev.get("transition", True):
                self._record_event(ev)
            if notify:
                subject, message = format_event(ev, names)
                self._dispatch({**ev, "subject": subject, "message": message})
        return all_events

    def _record_event(self, ev: dict) -> None:
        """Persist an event to the database's event log.

        Guarded so a DB hiccup (or a store without event support) can never
        kill the monitor loop — the log is best-effort, alerting is not.
        """
        try:
            self.db.record_event(ev.get("kind", ""), ev.get("probe_id", ""),
                                 temperature_c=ev.get("temperature_c"),
                                 limit=ev.get("limit"))
        except Exception as e:  # noqa: BLE001
            log.debug("could not record %s event: %s", ev.get("kind"), e)

    def _check_rate(self, readings: dict, cooldown_sec: int) -> list:
        """Rate-of-change alerts: pair each fresh probe's latest reading with
        the one closest to ``rate_window_min`` ago and hand both to the pure
        :func:`core.alerts.evaluate_rate`."""
        try:
            rate_c = float(self.cfg.get("rate_alert_c", 0.0) or 0.0)
        except (TypeError, ValueError):
            rate_c = 0.0
        if rate_c <= 0:
            self._rate_states = {}
            return []
        try:
            window_min = max(1, int(self.cfg.get("rate_window_min", 10) or 10))
        except (TypeError, ValueError):
            window_min = 10
        pairs = {}
        for pid, latest_c in readings.items():
            try:
                # Oldest-first within the window, so index 0 is ~window-old.
                rows = self.db.fetch_readings(window_seconds=window_min * 60, probe_id=pid)
                past_c = float(rows[0]["temperature_c"]) if rows else None
            except Exception:  # noqa: BLE001 - a read error must not kill the cycle
                continue
            if past_c is not None:
                pairs[pid] = (latest_c, past_c)
        events, self._rate_states = evaluate_rate(
            pairs, rate_c, window_min, self._rate_states, cooldown_sec=cooldown_sec)
        return events

    def _hysteresis(self) -> float:
        """Deadband (°C) a probe must clear before a breach is considered over —
        stops a noisy sensor at the limit from flapping high→ok→high."""
        try:
            return max(0.0, float(self.cfg.get("alert_hysteresis_c", 0.5)))
        except (TypeError, ValueError):
            return 0.5

    def _check_offline(self) -> list:
        last_epochs = self.db.last_reading_epoch_per_probe(window_seconds=OFFLINE_MONITOR_WINDOW_SEC)
        # Synthetic demo probes stop "reporting" the moment demo mode is turned
        # off — never alert on them.
        last_epochs = {pid: ep for pid, ep in last_epochs.items()
                       if not str(pid).startswith("DEMO-")}
        # Judge each probe against its own fresh window (floored at
        # offline_after_sec) so a slow deep-sleep cadence is not flagged
        # offline between wakes — the same rule every UI surface uses.
        windows = {pid: probe_fresh_window(self.cfg, pid) for pid in last_epochs}
        events, self._offline_states = evaluate_offline(
            last_epochs, self._offline_states, offline_after_sec=windows)
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

    def maybe_daily_summary(self, now: datetime.datetime | None = None) -> bool:
        """Send the once-a-day summary email when due. Returns True when sent.

        Gated on ``notifications.daily_summary.enabled`` and the email channel
        being enabled; the last-sent date persisted in the config keeps it to
        one email per day across restarts. A failed send is not recorded, so
        it retries on the next cycle instead of silently skipping a day.
        """
        conf = self.cfg.get("notifications", {}) or {}
        ds = conf.get("daily_summary", {}) or {}
        if not ds.get("enabled"):
            return False
        email = conf.get("email", {}) or {}
        if not email.get("enabled"):
            return False
        try:
            hour = int(ds.get("hour", 8))
        except (TypeError, ValueError):
            hour = 8
        now_dt = now if now is not None else datetime.datetime.now()
        if now_dt.hour < hour:
            return False
        today = now_dt.strftime("%Y-%m-%d")
        if self.cfg.get("daily_summary_last_sent") == today:
            return False
        subject, body = self._compose_daily_summary(today)
        ok, info = send_email(email, subject, body)
        if not ok:
            log.warning("daily summary email failed: %s", info)
            return False
        self.cfg.set("daily_summary_last_sent", today)
        log.info("daily summary sent for %s", today)
        return True

    def _compose_daily_summary(self, date_str: str) -> tuple:
        """Per-probe min/avg/max over the last 24 h plus the current reading."""
        names = self.cfg.get("probe_names", {}) or {}
        try:
            stats = self.db.stats_per_probe(86400) or {}
        except Exception:  # noqa: BLE001
            stats = {}
        current: dict = {}
        try:
            df = self.db.latest_per_probe(window_seconds=86400)
            for _, row in df.iterrows():
                try:
                    current[row["probe_id"]] = float(row["temperature_c"])
                except (TypeError, ValueError):
                    continue
        except Exception:  # noqa: BLE001
            pass
        lines = [f"Setpoint daily summary for {date_str}", ""]
        for pid in sorted(stats):
            s = stats[pid]
            label = names.get(pid, pid) or "(unlabelled)"
            line = (f"{label}: min {s['min']:.1f}°C / avg {s['avg']:.1f}°C / "
                    f"max {s['max']:.1f}°C over 24 h ({s['count']} readings)")
            if pid in current:
                line += f"; now {current[pid]:.1f}°C"
            lines.append(line)
        if not stats:
            lines.append("No readings in the last 24 hours.")
        return f"Setpoint daily summary — {date_str}", "\n".join(lines)

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
                self.maybe_daily_summary()
            except Exception as e:  # noqa: BLE001
                log.warning("alert monitor cycle error: %s", e)
            self._stop_event.wait(self.period_sec)
        self._notify_q.put(None)  # ensure the worker exits even without stop()

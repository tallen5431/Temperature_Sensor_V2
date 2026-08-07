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

from core.alerts import (HELD, evaluate, evaluate_offline, evaluate_rate,
                         find_missed_excursions, format_event)
from core.applog import HEALTH
from core.db import iso_to_epoch
from core.notifications import Notifier, send_email
from core.status import probe_fresh_window, probe_prune_window

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
        # Newest reading epoch each probe has been scanned up to, for excursions
        # that came and went between two cycles (see _check_missed). Seeded on
        # first sight WITHOUT scanning, so restarting the hub does not re-announce
        # every excursion still inside the retention window.
        self._scanned: dict = {}
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
                HEALTH.record_notify_dropped()
                log.warning("notification queue full; dropping %s alert for %s",
                            ev.get("kind"), ev.get("probe_id"))
        else:
            self._send(ev)

    def _send(self, ev: dict) -> None:
        """Dispatch to the channels and COUNT anything that did not get through.

        Notifier.dispatch reports a dead channel by returning ``ok=False`` rather
        than raising — send_email/send_webhook catch their own errors — so a
        bare try/except sees a clean run and the operator is never told. That is
        the failure this counter exists for: the dashboard still shows the
        breach and the event log still records it, so an undelivered alert looks
        exactly like a delivered one.
        """
        try:
            results = self.notifier.dispatch(ev) or []
        except Exception as e:  # noqa: BLE001 - a channel error must not kill the worker
            HEALTH.record_notify_failure()
            log.warning("notification dispatch error: %s", e)
            return
        failed = [ch for ch, ok, _ in results if not ok]
        if failed:
            HEALTH.record_notify_failure(len(failed))
            log.warning("notification for %s not delivered via %s",
                        ev.get("probe_id"), ", ".join(failed))

    def _dispatch_loop(self) -> None:
        while True:
            ev = self._notify_q.get()
            if ev is None:  # sentinel from stop()
                return
            self._send(ev)

    def _readings(self) -> dict:
        """Latest reading per probe, limited to recent data so we don't alert on
        a stale value from a probe that has gone offline.

        Freshness is judged PER PROBE. ``alert_freshness_sec`` (600 s) is a flat
        global, but a deep-sleeping probe legitimately reports only every
        interval — on a 15-minute cadence it is "stale" by that flat rule for a
        third of every cycle, so it flickers in and out of the alert engine while
        every other surface (dashboard, cards, offline detection) correctly calls
        it online via ``probe_fresh_window``. Each probe now gets the larger of
        the flat window and its own fresh window, so the alert engine agrees with
        the rest of the hub instead of contradicting it.
        """
        flat = int(self.cfg.get("alert_freshness_sec", 600) or 600)
        # Query wide enough to cover the slowest probe, then filter per probe.
        try:
            widest = max([flat] + [int(probe_fresh_window(self.cfg, pid))
                                   for pid in ((self.cfg.get("probe_intervals") or {}).keys())]
                         + [int(probe_fresh_window(self.cfg, None))])
        except Exception:  # noqa: BLE001 - config is user-editable
            widest = flat
        df = self.db.latest_per_probe(window_seconds=widest)
        now = time.time()
        out = {}
        for _, row in df.iterrows():
            pid = row["probe_id"]
            if pid is None or str(pid).strip() == "":
                continue
            try:
                allowed = max(flat, float(probe_fresh_window(self.cfg, pid)))
            except Exception:  # noqa: BLE001
                allowed = flat
            try:
                age = now - iso_to_epoch(str(row["timestamp"]))
            except Exception:  # noqa: BLE001 - a bad stamp shouldn't drop the probe
                age = 0.0
            if age > allowed:
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

        # --- excursions that came and went between cycles (backfill) ---
        # After evaluate(), so a run still open at the newest reading is reported
        # by the live path and this one leaves it alone — they can never both
        # claim the same incident.
        all_events.extend(self._check_missed())

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
            # Backfilled events are stamped when they HAPPENED, not when they were
            # discovered. Recorded at discovery, a freezer that went out of range
            # during a two-hour outage appears in Recent events as "just now" —
            # which is both false and the one detail that makes the row
            # actionable. Every other kind is judged live, so now is correct.
            ts = None
            if ev.get("kind") == "missed" and ev.get("start_epoch"):
                try:
                    ts = datetime.datetime.fromtimestamp(
                        float(ev["start_epoch"])).isoformat(timespec="seconds")
                except (TypeError, ValueError, OSError, OverflowError):
                    ts = None
            self.db.record_event(ev.get("kind", ""), ev.get("probe_id", ""),
                                 temperature_c=ev.get("temperature_c"),
                                 limit=ev.get("limit"), ts=ts)
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
                # The true window-old sample (index-backed, exact). Do NOT use
                # fetch_readings()[0]: it caps to the most-recent N rows first, so
                # on a high-cadence probe its oldest row is only ~N-old, not
                # window-old, which understates the delta and misses a rate alert.
                past_c = self.db.oldest_temp_c_in_window(pid, window_min * 60)
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

    def _recover_holds(self, windows: dict) -> dict:
        """Per-probe back-online confirmation window (see ``evaluate_offline``).

        Read from ``notifications.flap_grace_sec``: absent/None self-tunes to each
        probe's own offline window (a probe is trusted "back" once it has been
        steady for as long as it took to call it offline — damps a spotty link
        without extra tuning); a positive number pins the hold for every probe;
        ``0`` disables damping (recovery reported on the first fresh reading).
        """
        conf = self.cfg.get("notifications", {}) or {}
        raw = conf.get("flap_grace_sec")
        if raw is None:
            return dict(windows)
        try:
            sec = max(0, int(raw))
        except (TypeError, ValueError):
            return dict(windows)
        return {pid: sec for pid in windows}

    # A hub that has been off for a week must not wake up and send a hundred
    # e-mails. Scan at most this far back per probe, and report at most this many
    # runs per cycle; anything beyond is logged, because silently dropping it
    # would read as "nothing happened".
    MISSED_SCAN_MAX_SEC = 24 * 3600
    MISSED_MAX_PER_CYCLE = 3

    def _check_missed(self) -> list:
        """Excursions that began AND ended without the live evaluator seeing one.

        ``evaluate`` judges one reading per probe per cycle — the latest. A breach
        that starts and clears in between is stored, drawn on the chart, and never
        alerted. The threshold watch makes that the normal shape of a hub outage:
        the probe buffers every sample to flash while it cannot reach the hub,
        then flushes the lot, so a freezer that failed and recovered inside the
        outage arrives purely as history.

        Each probe is scanned forward from the last epoch it was scanned to.
        First sight seeds the watermark and scans NOTHING: without that, every
        hub restart would re-announce every excursion still in retention.
        """
        thresholds = self.cfg.get("alert_thresholds", {}) or {}
        if not thresholds:
            return []
        try:
            newest = self.db.last_reading_epoch_per_probe(
                window_seconds=self.MISSED_SCAN_MAX_SEC)
        except Exception:  # noqa: BLE001 - a read error must not kill the cycle
            return []

        floor = time.time() - self.MISSED_SCAN_MAX_SEC
        events: list = []
        for pid, latest_epoch in newest.items():
            if str(pid).startswith("DEMO-"):
                continue
            thr = thresholds.get(pid) or thresholds.get("default") or {}
            if thr.get("min") is None and thr.get("max") is None:
                continue
            since = self._scanned.get(pid)
            if since is None:
                self._scanned[pid] = latest_epoch
                continue          # first sight: seed only
            if latest_epoch <= since:
                continue          # nothing new
            try:
                rows = self.db.readings_after(pid, since, not_before=floor)
            except Exception:  # noqa: BLE001
                continue
            if not rows:
                continue
            # Advance the watermark to what was ACTUALLY scanned, not to the
            # helper's truncated MAX(epoch) — otherwise the newest reading falls
            # in the gap between the two and is never examined by anything.
            self._scanned[pid] = rows[-1][0]
            found = find_missed_excursions(rows, thr, probe_id=pid,
                                           hysteresis=self._hysteresis())
            if len(found) > self.MISSED_MAX_PER_CYCLE:
                log.warning("%s: %d missed excursions in one backfill; reporting the "
                            "first %d — see the chart for the rest",
                            pid, len(found), self.MISSED_MAX_PER_CYCLE)
                found = found[:self.MISSED_MAX_PER_CYCLE]
            events.extend(found)
        return events

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
            last_epochs, self._offline_states, offline_after_sec=windows,
            recover_hold_sec=self._recover_holds(windows))
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
        now = time.time()
        if now - self._last_prune < 3600:  # at most hourly
            return
        self._last_prune = now
        self._forget_deleted_probes()
        if self.discovery is None or not hasattr(self.discovery, "prune_stale"):
            return
        try:
            # Same rule the provisioner's pruner uses — a flat window here would
            # evict a deep-sleeping probe between posts and undo that protection.
            self.discovery.prune_stale(int(probe_prune_window(self.cfg)))
        except Exception as e:  # noqa: BLE001
            log.warning("probe prune failed: %s", e)

    def _forget_deleted_probes(self) -> None:
        """Drop alert state for probes whose data is no longer in the store.

        ``evaluate`` copies the previous states forward and only revises probes
        that reported this cycle, which is deliberate — it is what keeps a breach
        held while a probe is silent, so the cards can say ALARM · NO SIGNAL.
        But it also means "remove device" left the probe's ``high``/``low`` state
        behind forever: ``HELD`` kept publishing an alarm for a device that no
        longer exists, and the same id re-added later would start life already in
        breach. Deleting the readings is the operator saying this probe is gone,
        so take them at their word — on the same hourly cadence as the registry
        prune, and only for probes with no rows at all, so a merely-silent probe
        keeps its open incident.
        """
        if not (self._states or self._rate_states):
            return
        try:
            known = set(self.db.probe_ids() or ())
        except Exception as e:  # noqa: BLE001 - never break the monitor on a read
            log.debug("could not list probe ids for state prune: %s", e)
            return
        for states in (self._states, self._rate_states):
            for pid in [p for p in states if p not in known]:
                states.pop(pid, None)

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

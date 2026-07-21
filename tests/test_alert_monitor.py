"""Tests for the background alert monitor (alert_monitor.AlertMonitor)."""
import datetime
import time

import pandas as pd
import pytest

import alert_monitor
from alert_monitor import AlertMonitor
from core.config import Config
from core.db import Database


class RecordingNotifier:
    def __init__(self):
        self.events = []

    def dispatch(self, event):
        self.events.append(event)
        return [("test", True, "sent")]


class FakeEventDB:
    """Minimal db stub: canned latest readings plus a record_event recorder."""

    def __init__(self, temps=None):
        self.temps = dict(temps or {})   # {probe_id: latest_temperature_c}
        self.recorded = []
        self.fail_record = False

    def latest_per_probe(self, window_seconds=None):
        return pd.DataFrame(
            [{"timestamp": "t", "temperature_c": v, "temperature_f": v * 9 / 5 + 32,
              "probe_id": k, "humidity_pct": None, "vpd_kpa": None}
             for k, v in self.temps.items()],
            columns=["timestamp", "temperature_c", "temperature_f", "probe_id",
                     "humidity_pct", "vpd_kpa"])

    def last_reading_epoch_per_probe(self, window_seconds=None):
        return {pid: int(time.time()) for pid in self.temps}

    def fetch_readings(self, **kwargs):
        return []

    def record_event(self, kind, probe_id, temperature_c=None, limit=None, ts=None):
        if self.fail_record:
            raise RuntimeError("db is on fire")
        self.recorded.append((kind, probe_id, temperature_c, limit))


def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


def _setup(tmp_path, enabled=True):
    db = Database(tmp_path / "m.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({
        "alert_thresholds": {"TempProbe-FRIDGE": {"max": 8}},
        "notifications": {"enabled": enabled, "cooldown_sec": 1800, "notify_recovery": True},
    })
    notifier = RecordingNotifier()
    return db, cfg, notifier, AlertMonitor(db, cfg, notifier, period_sec=1)


def test_monitor_fires_then_dedupes(tmp_path):
    db, cfg, notifier, mon = _setup(tmp_path)
    db.append(_iso(datetime.datetime.now()), 12.0, 0.0, "TempProbe-FRIDGE")  # above max 8
    events = mon.check_once()
    assert len(events) == 1 and events[0]["kind"] == "high"
    assert len(notifier.events) == 1
    # Second poll with no new transition -> no duplicate notification
    assert mon.check_once() == []
    assert len(notifier.events) == 1


def test_monitor_disabled_evaluates_but_sends_nothing(tmp_path):
    # Evaluation (and event recording) is decoupled from notifications: with the
    # master switch off the breach is still detected, but nothing is dispatched.
    db, cfg, notifier, mon = _setup(tmp_path, enabled=False)
    db.append(_iso(datetime.datetime.now()), 99.0, 0.0, "TempProbe-FRIDGE")
    events = mon.check_once()
    assert len(events) == 1 and events[0]["kind"] == "high"
    assert notifier.events == []


def test_monitor_ignores_stale_readings(tmp_path):
    db, cfg, notifier, mon = _setup(tmp_path)
    cfg.update({"alert_freshness_sec": 300})
    # Reading is 10 minutes old -> outside the freshness window, so no alert.
    old = datetime.datetime.now() - datetime.timedelta(minutes=10)
    db.append(_iso(old), 50.0, 0.0, "TempProbe-FRIDGE")
    assert mon.check_once() == []


def test_monitor_recovery(tmp_path):
    db, cfg, notifier, mon = _setup(tmp_path)
    db.append(_iso(datetime.datetime.now()), 12.0, 0.0, "TempProbe-FRIDGE")
    mon.check_once()  # high
    db.append(_iso(datetime.datetime.now()), 4.0, 0.0, "TempProbe-FRIDGE")  # back to normal
    events = mon.check_once()
    assert len(events) == 1 and events[0]["kind"] == "recovery"


def test_monitor_hysteresis_suppresses_recovery_flap(tmp_path):
    db, cfg, notifier, mon = _setup(tmp_path)          # FRIDGE max = 8
    cfg.update({"alert_hysteresis_c": 0.5})
    db.append(_iso(datetime.datetime.now()), 9.0, 0.0, "TempProbe-FRIDGE")   # high (> 8)
    assert mon.check_once()[0]["kind"] == "high"
    # Hover just below the limit but inside the 0.5 deadband -> must NOT flap.
    db.append(_iso(datetime.datetime.now()), 7.7, 0.0, "TempProbe-FRIDGE")
    assert mon.check_once() == []
    # Clear well past the deadband -> a single recovery.
    db.append(_iso(datetime.datetime.now()), 7.0, 0.0, "TempProbe-FRIDGE")
    events = mon.check_once()
    assert len(events) == 1 and events[0]["kind"] == "recovery"


def test_monitor_offline_alert_after_seed(tmp_path):
    db, cfg, notifier, mon = _setup(tmp_path)
    # A reading 400 s old is past the default 300 s fresh window. The seed cycle
    # records it as already-offline without emitting a startup burst...
    old = datetime.datetime.now() - datetime.timedelta(seconds=400)
    db.append(_iso(old), 5.0, 0.0, "TempProbe-FRIDGE")
    assert mon.check_once() == []      # first cycle seeds — no offline burst
    # ...so pretend the probe was online at seed time to observe the
    # online -> offline transition itself.
    mon._offline_states = {"TempProbe-FRIDGE": "online"}
    events = mon.check_once()
    assert any(e["kind"] == "offline" and e["probe_id"] == "TempProbe-FRIDGE" for e in events)


def test_monitor_offline_respects_per_probe_interval(tmp_path):
    # The #1 field bug: a deep-sleep probe reporting every 10 min must NOT be
    # flagged offline between wakes. Its fresh window is 2.5x its own interval
    # (1500 s), not the global offline_after_sec.
    db, cfg, notifier, mon = _setup(tmp_path)
    cfg.update({"probe_intervals": {"TempProbe-SLEEPY": 600, "TempProbe-GONE": 600},
                "offline_after_sec": 300})
    now = datetime.datetime.now()
    db.append(_iso(now - datetime.timedelta(seconds=400)), 5.0, 0.0, "TempProbe-SLEEPY")
    db.append(_iso(now - datetime.timedelta(seconds=1600)), 5.0, 0.0, "TempProbe-GONE")
    mon._offline_seeded = True
    mon._offline_states = {"TempProbe-SLEEPY": "online", "TempProbe-GONE": "online"}
    events = mon._check_offline()
    kinds = {e["probe_id"]: e["kind"] for e in events}
    assert "TempProbe-SLEEPY" not in kinds          # silent 400 s < 1500 s window
    assert kinds.get("TempProbe-GONE") == "offline"  # silent 1600 s > 1500 s window


def test_monitor_offline_skips_demo_probes(tmp_path):
    # Synthetic DEMO- probes stop the moment demo mode is switched off; they
    # must never raise offline alerts (nor even be tracked).
    db, cfg, notifier, mon = _setup(tmp_path)
    old = datetime.datetime.now() - datetime.timedelta(seconds=4000)
    db.append(_iso(old), 4.0, 0.0, "DEMO-Fridge")
    mon._offline_seeded = True
    mon._offline_states = {"DEMO-Fridge": "online"}
    assert mon._check_offline() == []
    assert "DEMO-Fridge" not in mon._offline_states


def test_monitor_offline_disabled(tmp_path):
    db, cfg, notifier, mon = _setup(tmp_path)
    cfg.update({"offline_after_sec": 1,
                "notifications": {"enabled": True, "offline_alerts": False,
                                  "alert_thresholds": {}}})
    old = datetime.datetime.now() - datetime.timedelta(minutes=10)
    db.append(_iso(old), 5.0, 0.0, "TempProbe-FRIDGE")  # very stale but in range
    mon.check_once()
    assert mon.check_once() == []  # offline alerts off -> nothing


def _event_cfg(tmp_path, enabled=True):
    cfg = Config(tmp_path / "c.json")
    cfg.update({
        "alert_thresholds": {"TempProbe-FRIDGE": {"max": 8}},
        "notifications": {"enabled": enabled, "cooldown_sec": 1800,
                          "notify_recovery": True},
    })
    return cfg


def test_monitor_records_transition_events(tmp_path):
    # high and recovery transitions land in the event log; while a breach just
    # persists (no transition, no reminder) nothing is recorded.
    cfg = _event_cfg(tmp_path, enabled=False)   # recording is dispatch-independent
    fdb = FakeEventDB({"TempProbe-FRIDGE": 12.0})
    notifier = RecordingNotifier()
    mon = AlertMonitor(fdb, cfg, notifier, period_sec=1)
    mon.check_once()
    assert ("high", "TempProbe-FRIDGE", 12.0, 8) in fdb.recorded
    assert notifier.events == []                # notifications stay gated
    fdb.recorded.clear()
    mon.check_once()                            # still in breach, no transition
    assert fdb.recorded == []
    fdb.temps["TempProbe-FRIDGE"] = 4.0
    mon.check_once()
    assert ("recovery", "TempProbe-FRIDGE", 4.0, None) in fdb.recorded
    # online/offline transitions are recorded too
    fdb.recorded.clear()
    mon._offline_states = {"TempProbe-FRIDGE": "offline"}   # probe reports again
    mon.check_once()
    assert ("online", "TempProbe-FRIDGE", None, None) in fdb.recorded


def test_monitor_cooldown_reminder_not_recorded(tmp_path):
    # A cooldown reminder notifies again but is NOT a new incident: it must be
    # dispatched without being duplicated into the event log.
    cfg = _event_cfg(tmp_path)
    cfg.update({"notifications": {"enabled": True, "cooldown_sec": 1,
                                  "offline_alerts": False}})
    fdb = FakeEventDB({"TempProbe-FRIDGE": 12.0})
    notifier = RecordingNotifier()
    mon = AlertMonitor(fdb, cfg, notifier, period_sec=1)
    mon.check_once()
    assert len(fdb.recorded) == 1 and len(notifier.events) == 1
    time.sleep(1.1)                             # let the 1 s cooldown expire
    mon.check_once()                            # reminder fires...
    assert len(notifier.events) == 2
    assert len(fdb.recorded) == 1               # ...but is not recorded again


def test_monitor_record_event_failure_does_not_break_cycle(tmp_path):
    cfg = _event_cfg(tmp_path)
    fdb = FakeEventDB({"TempProbe-FRIDGE": 12.0})
    fdb.fail_record = True
    notifier = RecordingNotifier()
    mon = AlertMonitor(fdb, cfg, notifier, period_sec=1)
    events = mon.check_once()                   # must not raise
    assert len(events) == 1
    assert len(notifier.events) == 1            # the alert still went out


def test_monitor_updates_held_registry(tmp_path):
    from core.alerts import HELD
    db, cfg, notifier, mon = _setup(tmp_path)   # FRIDGE max = 8
    cfg.update({"alert_hysteresis_c": 0.5})
    db.append(_iso(datetime.datetime.now()), 9.0, 0.0, "TempProbe-FRIDGE")
    mon.check_once()
    assert HELD.get("TempProbe-FRIDGE") == "high"
    # Inside the deadband the breach is held -> still registered.
    db.append(_iso(datetime.datetime.now()), 7.7, 0.0, "TempProbe-FRIDGE")
    mon.check_once()
    assert HELD.get("TempProbe-FRIDGE") == "high"
    # Cleared past the deadband -> removed from the registry.
    db.append(_iso(datetime.datetime.now()), 7.0, 0.0, "TempProbe-FRIDGE")
    mon.check_once()
    assert HELD.get("TempProbe-FRIDGE") is None


def test_monitor_rate_alert_fires_and_cools_down(tmp_path):
    db, cfg, notifier, mon = _setup(tmp_path)
    cfg.update({"rate_alert_c": 2.0, "rate_window_min": 10})
    now = datetime.datetime.now()
    db.append(_iso(now - datetime.timedelta(minutes=9)), 20.0, 68.0, "TempProbe-ROOM")
    db.append(_iso(now), 25.0, 77.0, "TempProbe-ROOM")
    events = mon.check_once()
    rate = [e for e in events if e["kind"] == "rate"]
    assert len(rate) == 1 and rate[0]["probe_id"] == "TempProbe-ROOM"
    assert rate[0]["delta_c"] == pytest.approx(5.0)
    sent = [e for e in notifier.events if e["kind"] == "rate"]
    assert sent and "rose 5.0 °C in 10 min" in sent[0]["message"]
    # Same conditions on the next cycle -> per-probe cooldown suppresses spam.
    events2 = mon.check_once()
    assert [e for e in events2 if e["kind"] == "rate"] == []


def test_monitor_rate_alert_disabled_by_default(tmp_path):
    db, cfg, notifier, mon = _setup(tmp_path)   # no rate_alert_c in config
    now = datetime.datetime.now()
    db.append(_iso(now - datetime.timedelta(minutes=9)), 20.0, 68.0, "TempProbe-ROOM")
    db.append(_iso(now), 25.0, 77.0, "TempProbe-ROOM")
    assert [e for e in mon.check_once() if e["kind"] == "rate"] == []


class FakeSummaryDB(FakeEventDB):
    def __init__(self, temps=None, stats=None):
        super().__init__(temps)
        self.stats = stats or {}

    def stats_per_probe(self, window_seconds=None):
        assert window_seconds == 86400
        return self.stats


def _summary_setup(tmp_path, monkeypatch, send_result=(True, "sent")):
    cfg = Config(tmp_path / "c.json")
    cfg.update({"notifications": {
        "enabled": False,     # summary is independent of the alert master switch
        "daily_summary": {"enabled": True, "hour": 8},
        "email": {"enabled": True, "smtp_host": "smtp.local", "to": "a@b"},
    }})
    fdb = FakeSummaryDB(
        temps={"P1": 6.2},
        stats={"P1": {"count": 10, "min": 2.0, "max": 9.5, "avg": 5.1}})
    sent = []
    monkeypatch.setattr(alert_monitor, "send_email",
                        lambda email, subject, body: (sent.append((subject, body)),
                                                      send_result)[1])
    mon = AlertMonitor(fdb, cfg, RecordingNotifier(), period_sec=1)
    return cfg, mon, sent


def test_daily_summary_sent_once_per_day(tmp_path, monkeypatch):
    cfg, mon, sent = _summary_setup(tmp_path, monkeypatch)
    cfg.update({"probe_names": {"P1": "Fridge"}})
    at_9 = datetime.datetime(2026, 7, 21, 9, 0, 0)
    assert mon.maybe_daily_summary(now=at_9) is True
    assert len(sent) == 1
    subject, body = sent[0]
    assert "2026-07-21" in subject
    assert "Fridge" in body and "2.0" in body and "5.1" in body and "9.5" in body
    assert "6.2" in body                                  # current reading included
    assert cfg.get("daily_summary_last_sent") == "2026-07-21"
    # Same day again -> once-per-day guard.
    assert mon.maybe_daily_summary(now=at_9) is False
    assert len(sent) == 1
    # Next day, before the configured hour -> not yet; at the hour -> sends.
    assert mon.maybe_daily_summary(now=datetime.datetime(2026, 7, 22, 7, 59)) is False
    assert mon.maybe_daily_summary(now=datetime.datetime(2026, 7, 22, 8, 0)) is True
    assert len(sent) == 2


def test_daily_summary_failed_send_retries(tmp_path, monkeypatch):
    cfg, mon, sent = _summary_setup(tmp_path, monkeypatch, send_result=(False, "boom"))
    assert mon.maybe_daily_summary(now=datetime.datetime(2026, 7, 21, 9, 0)) is False
    assert len(sent) == 1
    assert cfg.get("daily_summary_last_sent") is None     # not marked -> retried
    assert mon.maybe_daily_summary(now=datetime.datetime(2026, 7, 21, 9, 1)) is False
    assert len(sent) == 2


def test_daily_summary_disabled_or_no_email(tmp_path, monkeypatch):
    cfg, mon, sent = _summary_setup(tmp_path, monkeypatch)
    notif = cfg.get("notifications")
    notif["daily_summary"]["enabled"] = False
    cfg.update({"notifications": notif})
    assert mon.maybe_daily_summary(now=datetime.datetime(2026, 7, 21, 9, 0)) is False
    notif["daily_summary"]["enabled"] = True
    notif["email"]["enabled"] = False
    cfg.update({"notifications": notif})
    assert mon.maybe_daily_summary(now=datetime.datetime(2026, 7, 21, 9, 0)) is False
    assert sent == []

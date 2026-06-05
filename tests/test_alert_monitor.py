"""Tests for the background alert monitor (alert_monitor.AlertMonitor)."""
import datetime

from alert_monitor import AlertMonitor
from core.config import Config
from core.db import Database


class RecordingNotifier:
    def __init__(self):
        self.events = []

    def dispatch(self, event):
        self.events.append(event)
        return [("test", True, "sent")]


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


def test_monitor_disabled_sends_nothing(tmp_path):
    db, cfg, notifier, mon = _setup(tmp_path, enabled=False)
    db.append(_iso(datetime.datetime.now()), 99.0, 0.0, "TempProbe-FRIDGE")
    assert mon.check_once() == []
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


def test_monitor_offline_alert_after_seed(tmp_path):
    import time
    db, cfg, notifier, mon = _setup(tmp_path)
    cfg.update({"offline_after_sec": 1})
    db.append(_iso(datetime.datetime.now()), 5.0, 0.0, "TempProbe-FRIDGE")  # fresh, in range
    assert mon.check_once() == []      # first cycle seeds — no offline burst
    time.sleep(1.2)                    # probe now silent > 1 s
    events = mon.check_once()
    assert any(e["kind"] == "offline" and e["probe_id"] == "TempProbe-FRIDGE" for e in events)


def test_monitor_offline_disabled(tmp_path):
    db, cfg, notifier, mon = _setup(tmp_path)
    cfg.update({"offline_after_sec": 1,
                "notifications": {"enabled": True, "offline_alerts": False,
                                  "alert_thresholds": {}}})
    old = datetime.datetime.now() - datetime.timedelta(minutes=10)
    db.append(_iso(old), 5.0, 0.0, "TempProbe-FRIDGE")  # very stale but in range
    mon.check_once()
    assert mon.check_once() == []  # offline alerts off -> nothing

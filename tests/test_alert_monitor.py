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
    now = datetime.datetime.now()
    db.append(_iso(now - datetime.timedelta(seconds=1)), 12.0, 0.0, "TempProbe-FRIDGE")
    mon.check_once()  # high
    db.append(_iso(now), 4.0, 0.0, "TempProbe-FRIDGE")  # back to normal (newer reading)
    events = mon.check_once()
    assert len(events) == 1 and events[0]["kind"] == "recovery"


def test_monitor_hysteresis_suppresses_recovery_flap(tmp_path):
    db, cfg, notifier, mon = _setup(tmp_path)          # FRIDGE max = 8
    cfg.update({"alert_hysteresis_c": 0.5})
    now = datetime.datetime.now()
    db.append(_iso(now - datetime.timedelta(seconds=2)), 9.0, 0.0, "TempProbe-FRIDGE")   # high (> 8)
    assert mon.check_once()[0]["kind"] == "high"
    # Hover just below the limit but inside the 0.5 deadband -> must NOT flap.
    db.append(_iso(now - datetime.timedelta(seconds=1)), 7.7, 0.0, "TempProbe-FRIDGE")
    assert mon.check_once() == []
    # Clear well past the deadband -> a single recovery.
    db.append(_iso(now), 7.0, 0.0, "TempProbe-FRIDGE")
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


def test_monitor_flap_damping_holds_recovery(tmp_path):
    # With the default (auto) flap grace, a probe that has just come back does NOT
    # immediately fire "back online" — it must stay steady for the hold window,
    # so a spotty link that lands one reading and drops again stops flapping.
    db, cfg, notifier, mon = _setup(tmp_path)          # notifications has no flap_grace -> auto
    now = datetime.datetime.now()
    db.append(_iso(now), 5.0, 0.0, "TempProbe-FRIDGE")  # fresh reading -> raw online
    mon._offline_seeded = True
    mon._offline_states = {"TempProbe-FRIDGE": {
        "committed": "offline", "raw": "offline", "online_since": None, "flaps": 2}}
    events = mon._check_offline()
    assert [e for e in events if e["kind"] == "online"] == []          # recovery withheld
    assert mon._offline_states["TempProbe-FRIDGE"]["committed"] == "offline"


def test_recover_holds_config_modes(tmp_path):
    db, cfg, notifier, mon = _setup(tmp_path)
    windows = {"p": 750.0, "q": 300.0}
    base = cfg.get("notifications") or {}
    assert mon._recover_holds(windows) == windows                     # auto: mirror each window
    cfg.update({"notifications": {**base, "flap_grace_sec": 120}})
    assert mon._recover_holds(windows) == {"p": 120, "q": 120}         # fixed for all probes
    cfg.update({"notifications": {**base, "flap_grace_sec": 0}})
    assert mon._recover_holds(windows) == {"p": 0, "q": 0}             # disabled


def _event_cfg(tmp_path, enabled=True):
    cfg = Config(tmp_path / "c.json")
    cfg.update({
        "alert_thresholds": {"TempProbe-FRIDGE": {"max": 8}},
        # flap_grace_sec=0 disables the back-online hold so these tests observe the
        # raw online/offline transitions directly (damping is exercised separately).
        "notifications": {"enabled": enabled, "cooldown_sec": 1800,
                          "notify_recovery": True, "flap_grace_sec": 0},
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
    now = datetime.datetime.now()
    db.append(_iso(now - datetime.timedelta(seconds=2)), 9.0, 0.0, "TempProbe-FRIDGE")
    mon.check_once()
    assert HELD.get("TempProbe-FRIDGE") == "high"
    # Inside the deadband the breach is held -> still registered.
    db.append(_iso(now - datetime.timedelta(seconds=1)), 7.7, 0.0, "TempProbe-FRIDGE")
    mon.check_once()
    assert HELD.get("TempProbe-FRIDGE") == "high"
    # Cleared past the deadband -> removed from the registry.
    db.append(_iso(now), 7.0, 0.0, "TempProbe-FRIDGE")
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


def test_readings_include_slow_probe_beyond_flat_freshness(tmp_path):
    # A deep-sleeping probe on a 15-min interval is "stale" by the flat
    # alert_freshness_sec (600 s) for a third of every cycle, so it used to
    # flicker in and out of the alert engine while the dashboard — which uses
    # probe_fresh_window — correctly called it online. Freshness is now judged
    # per probe, so the two agree.
    import datetime
    from core.config import Config
    from core.db import Database

    db = Database(tmp_path / "m.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"alert_freshness_sec": 600, "probe_intervals": {"slow": 900}})

    now = datetime.datetime.now()
    # Reading is 700 s old: beyond the flat 600 s window, well inside this
    # probe's own fresh window (max(300, 900 * 2.5) = 2250 s).
    db.append((now - datetime.timedelta(seconds=700)).isoformat(timespec="milliseconds"),
              -18.0, -0.4, "slow")
    mon = AlertMonitor(db, cfg)
    assert "slow" in mon._readings()

    # A probe with no override still obeys the flat window: 700 s old and a
    # 5 s interval -> fresh window is the 300 s floor -> genuinely stale.
    db.append((now - datetime.timedelta(seconds=700)).isoformat(timespec="milliseconds"),
              4.0, 39.2, "fast")
    assert "fast" not in mon._readings()


def test_both_pruners_share_one_window(tmp_path):
    # The alert monitor's hourly sweep used the flat probe_prune_after_sec while
    # the provisioner scaled it, so the monitor would evict a deep-sleeping probe
    # the provisioner was protecting. Both must use the same rule.
    from core.status import probe_prune_window
    from core.config import Config
    from core.db import Database

    cfg = Config(tmp_path / "c.json")
    cfg.update({"probe_prune_after_sec": 3600, "probe_intervals": {"slow": 3600}})
    expected = int(probe_prune_window(cfg))
    assert expected > 3600           # scaled up for the hourly probe

    seen = {}

    class _Disc:
        def prune_stale(self, seconds):
            seen["after"] = seconds

    mon = AlertMonitor(Database(tmp_path / "m.db"), cfg, discovery=_Disc())
    mon._last_prune = 0
    mon.maybe_prune_probes()
    assert seen["after"] == expected


def test_a_restart_re_reports_a_breach_that_is_still_happening(tmp_path):
    """Alert state is in-memory, so a hub restart re-evaluates from scratch.

    This pins a TRADE-OFF rather than an implementation detail, because the
    alternative is worse. Persisting the state would stop the duplicate, but a
    hub that was down for hours would then trust a stale verdict and could stay
    silent about a probe whose situation changed while it was off. For a
    food-safety device, re-reporting something still true beats missing
    something new — and after a power cut (which warms the freezer AND restarts
    the hub, the correlated case) being told again is what you want.

    The cost is one duplicate transition in the event log per restart per
    breaching probe: the audit trail reads as recover-and-re-breach when the
    excursion was continuous. Accepted knowingly; change it only with the
    stale-state risk in mind.
    """
    from core.config import Config
    from core.db import Database
    from alert_monitor import AlertMonitor

    db = Database(tmp_path / "t.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"alert_thresholds": {"default": {"min": 0.0, "max": 8.0}},
                "notifications": {"enabled": False}})

    class _F:
        def list_probes(self):
            return {}

    def warm():
        db.append(datetime.datetime.now().isoformat(timespec="milliseconds"),
                  15.0, 59.0, "walkin")

    warm()
    m = AlertMonitor(db, cfg, discovery=_F())
    m.check_once()
    m.check_once()          # same process: the state machine holds, no duplicate
    assert [e["kind"] for e in db.list_events()] == ["high"]

    warm()
    AlertMonitor(db, cfg, discovery=_F()).check_once()   # restart
    assert [e["kind"] for e in db.list_events()] == ["high", "high"]


def test_removing_a_device_clears_its_held_alarm(tmp_path):
    """"Remove device" deletes the probe's readings, but the monitor copies its
    state forward every cycle and only revises probes that reported — so a
    removed probe kept its `high` state forever. ``HELD`` went on publishing an
    alarm for a device that no longer existed, and re-adding the same id later
    started it already in breach, held by the hysteresis deadband.

    Holding state for a merely SILENT probe is deliberate (it is what lets the
    cards say ALARM · NO SIGNAL), so only probes with no rows at all are
    forgotten — the operator deleting the data is the signal.
    """
    from core.alerts import HELD

    db = Database(tmp_path / "r.db")
    cfg = Config(tmp_path / "r.json")
    cfg.update({"alert_thresholds": {"gone": {"max": 8.0}, "stays": {"max": 8.0}},
                "notifications": {"enabled": False}})
    now = datetime.datetime.now()
    db.append(_iso(now), 20.0, 68.0, "gone")      # both in breach
    db.append(_iso(now), 20.0, 68.0, "stays")
    mon = AlertMonitor(db, cfg, RecordingNotifier(), period_sec=1)
    mon.check_once()
    assert HELD.get("gone") == "high" and HELD.get("stays") == "high"

    db.delete_probe("gone")                       # what "remove device" does
    mon._last_prune = 0.0                         # the hourly sweep comes due
    mon.maybe_prune_probes()
    mon.check_once()

    assert HELD.get("gone") is None, "a deleted probe still holds an alarm"
    assert "gone" not in mon._states
    # The probe that is merely silent (deleted nothing) keeps its open incident.
    assert HELD.get("stays") == "high"


def test_a_silent_probe_keeps_its_open_breach(tmp_path):
    """The counterpart guard: pruning must not be able to swallow a real
    incident just because the probe stopped reporting mid-excursion — that is
    the case the alarm exists for."""
    from core.alerts import HELD

    db = Database(tmp_path / "s.db")
    cfg = Config(tmp_path / "s.json")
    cfg.update({"alert_thresholds": {"quiet": {"max": 8.0}},
                "notifications": {"enabled": False}})
    db.append(_iso(datetime.datetime.now() - datetime.timedelta(hours=6)),
              20.0, 68.0, "quiet")
    mon = AlertMonitor(db, cfg, RecordingNotifier(), period_sec=1)
    mon._states = {"quiet": {"condition": "high", "last_notified": time.time()}}
    mon._last_prune = 0.0
    mon.maybe_prune_probes()
    mon.check_once()
    assert HELD.get("quiet") == "high"

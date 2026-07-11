"""Tests for the dashboard computation (components.dashboard_view.build_dashboard)."""
import datetime

from components.dashboard_view import build_dashboard
from core.config import Config
from core.db import Database


class FakeFinder:
    def __init__(self, probes=None):
        self._p = probes or {}

    def list_probes(self):
        return self._p


def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


def _seed(db, n_per_probe=3):
    now = datetime.datetime.now()
    for probe in ("TempProbe-A", "TempProbe-B"):
        for i in range(n_per_probe):
            t = now - datetime.timedelta(minutes=(n_per_probe - i))
            db.append(_iso(t), 20.0 + i + (5 if probe.endswith("B") else 0), 0.0, probe)


def test_build_dashboard_empty(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius")
    assert len(out) == 14
    # metric-lastupdate is "(no data)" when empty
    assert out[3] == "(no data)"


def test_build_dashboard_with_data(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    _seed(db)
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius")
    gauge, fig, probes, lastupd, logging_status, hb, range_info = out[:7]
    # Two probes -> two traces, legend shown
    assert len(fig.data) == 2
    assert fig.layout.showlegend is True
    assert "data points" in range_info
    assert logging_status == "ON"


def test_build_dashboard_fahrenheit_unit(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    db.append(_iso(datetime.datetime.now()), 25.0, 77.0, "p")
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "fahrenheit")
    gauge = out[0]
    # Gauge value converted to °F (25C -> 77F)
    assert abs(gauge.data[0].value - 77.0) < 0.01
    assert gauge.data[0].number.suffix.strip() == "°F"


def test_build_dashboard_alerts_fire(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"alert_thresholds": {"TempProbe-HOT": {"max": 30}}})
    db.append(_iso(datetime.datetime.now()), 35.0, 95.0, "TempProbe-HOT")  # above max
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius")
    alerts = out[13]
    assert alerts and len(alerts) == 1  # one over-threshold alert raised


def test_build_dashboard_friendly_name_used(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"probe_names": {"TempProbe-A": "Kitchen", "TempProbe-B": "Garage"}})
    _seed(db)
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius")
    fig = out[1]
    names = {tr.name for tr in fig.data}
    assert names == {"Kitchen", "Garage"}


def test_reporting_probe_count(tmp_path):
    # "Connected Probes" now counts probes that actually reported within the
    # online window (from the readings DB), not just mDNS-discovered ones — so a
    # deep-sleep probe (radio off, never mDNS-visible) still counts while posting.
    import datetime
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    now = datetime.datetime.now()
    db.append(now.isoformat(timespec="seconds"), 22.0, 71.6, "a")   # recent → counts
    old = (now - datetime.timedelta(hours=2)).isoformat(timespec="seconds")
    db.append(old, 4.0, 39.2, "b")                                  # stale → not counted
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius")
    assert out[2] == "1"  # only the probe that reported within the online window


def test_reporting_probe_count_deep_sleep_not_flickering(tmp_path):
    # A deep-sleep battery probe wakes, posts, and sleeps for minutes — so its
    # newest reading is often older than the old 60 s bar but well within the
    # 5-min offline threshold the alert monitor uses. It must still count as
    # connected, otherwise "Connected Probes" flickers to 0 between wakes.
    import datetime
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    now = datetime.datetime.now()
    ninety_s_ago = (now - datetime.timedelta(seconds=90)).isoformat(timespec="seconds")
    db.append(ninety_s_ago, 22.0, 71.6, "sleepy")   # 90 s > old 60 s bar
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius")
    assert out[2] == "1"  # counts under the interval-aware / 5-min freshness window

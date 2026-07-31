"""The chart range selector must not change which probes can raise an alert.

``build_dashboard`` shares one latest-per-probe scan between the worst-breach
gauge picker and the alert banner. Both already gate each row on
``_probe_fresh_window`` -- the interval-aware "is this probe live?" test, and
the only thing that should decide. Scoping the QUERY to the selected chart range
as well turned a pure view control into an alerting control: a probe on a slow
deep-sleep cadence whose newest reading falls outside the selected range was
dropped before the freshness gate ever ran, so the banner went silent while the
probe's own card (which queries the 7-day presence window) still read "HIGH".
"""
import datetime

import pytest

from components.dashboard_view import build_dashboard
from core.db import Database

ALERTS = 13          # index of the alerts list in build_dashboard's 14-tuple
LAST_UPDATE = 3


class _Cfg(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


class _NoFinder:
    def list_probes(self):
        return {}


@pytest.fixture()
def db_with_slow_breach(tmp_path):
    """A 2 h-cadence probe, breaching, last heard from 90 minutes ago.

    5400 s old against an 18000 s freshness window: unambiguously live.
    """
    db = Database(tmp_path / "readings.db")
    now = datetime.datetime.now()

    def add(pid, minutes_ago, temp_c):
        ts = now - datetime.timedelta(minutes=minutes_ago)
        db.append(ts.isoformat(timespec="milliseconds"), temp_c,
                  temp_c * 9 / 5 + 32, pid, epoch=ts.timestamp())

    add("SLOW", 90, 35.0)     # breaching, outside a 1 h chart range
    add("ROOM", 0.1, 22.0)    # fine, inside every range
    return db


@pytest.fixture()
def cfg():
    return _Cfg({
        "probe_intervals": {"SLOW": 7200},
        "alert_thresholds": {"SLOW": {"max": 30}},
        "probe_names": {"SLOW": "Vaccine fridge"},
        "settings": {}, "notifications": {}, "calibration_offsets": {},
    })


@pytest.mark.parametrize("time_range", ["1h", "6h", "24h", "7d", "all"])
def test_live_breach_alerts_regardless_of_chart_range(db_with_slow_breach, cfg, time_range):
    out = build_dashboard(db_with_slow_breach, cfg, _NoFinder(), time_range, "celsius")
    assert len(out[ALERTS]) == 1, f"alert lost at range={time_range}"


def test_a_genuinely_stale_breach_still_does_not_alert(tmp_path, cfg):
    """Widening the query must not resurrect the bug the freshness gate prevents."""
    db = Database(tmp_path / "stale.db")
    now = datetime.datetime.now()
    old = now - datetime.timedelta(days=3)       # far beyond SLOW's 18000 s window
    db.append(old.isoformat(timespec="milliseconds"), 35.0, 95.0, "SLOW",
              epoch=old.timestamp())
    fresh = now - datetime.timedelta(seconds=5)
    db.append(fresh.isoformat(timespec="milliseconds"), 22.0, 71.6, "ROOM",
              epoch=fresh.timestamp())
    out = build_dashboard(db, cfg, _NoFinder(), "all", "celsius")
    assert out[ALERTS] == []


def test_empty_database_returns_the_no_data_state_without_raising(tmp_path, cfg, caplog):
    """First run is normal, not an error -- it must not log a traceback."""
    db = Database(tmp_path / "empty.db")
    with caplog.at_level("ERROR"):
        out = build_dashboard(db, cfg, _NoFinder(), "24h", "celsius")
    assert len(out) == 14
    assert out[LAST_UPDATE] == "(no data)"
    assert not [r for r in caplog.records if "dashboard update failed" in r.message]

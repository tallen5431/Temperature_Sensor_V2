"""Regression tests for the dashboard freshness-consistency fixes.

These lock in the behaviors surfaced by the dashboard code review:
  * the alert banner / gauge ignore probes that have gone silent,
  * focus-mode "Last Update" tracks the focused probe (not the hub-wide newest),
  * the shared `probe_fresh_window` helper, and
  * Diagnostics "reporting" using that same window so it matches the dashboard.
"""
import datetime

from components.dashboard_view import build_dashboard
from core.config import Config
from core.db import Database
from core.diagnostics import build_diagnostics
from core.status import probe_fresh_window


class _FakeFinder:
    def __init__(self, probes=None):
        self._p = probes or {}

    def list_probes(self):
        return self._p


def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


# --- build_dashboard: index map (see build_dashboard docstring) ---
# 0 gauge, 1 fig, 2 probes, 3 last_update, 4 logging, 5 heartbeat, 6 range_info,
# 7-12 stats, 13 alerts
LAST_UPDATE, LOGGING, ALERTS = 3, 4, 13


def test_stale_breach_does_not_alert(tmp_path):
    """A probe that breached then went silent must not keep firing an alert."""
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.set("alert_thresholds", {"HOT": {"max": 30.0}})
    old = datetime.datetime.now() - datetime.timedelta(hours=2)
    db.append(_iso(old), 99.0, 210.2, "HOT")  # a breach, but 2 h stale
    out = build_dashboard(db, cfg, _FakeFinder(), "24h", "celsius")
    assert out[ALERTS] == []  # stale probe skipped — banner agrees with its card


def test_fresh_breach_still_alerts(tmp_path):
    """Guardrail: a fresh breaching probe must still raise its alert."""
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.set("alert_thresholds", {"HOT": {"max": 30.0}})
    db.append(_iso(datetime.datetime.now()), 99.0, 210.2, "HOT")  # fresh breach
    out = build_dashboard(db, cfg, _FakeFinder(), "24h", "celsius")
    assert len(out[ALERTS]) == 1


def test_focus_last_update_reflects_focused_probe(tmp_path):
    """Focus mode's 'Last Update' tracks the focused probe, not the hub newest."""
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    old = datetime.datetime.now() - datetime.timedelta(hours=3)
    db.append(_iso(old), 20.0, 68.0, "A")                        # focused: 3 h stale
    db.append(_iso(datetime.datetime.now()), 21.0, 69.8, "B")    # other: fresh
    out = build_dashboard(db, cfg, _FakeFinder(), "24h", "celsius", focus_probe="A")
    assert out[LAST_UPDATE] != "Just now"   # must NOT show B's freshness
    assert "ago" in out[LAST_UPDATE]         # reflects A's real ~3 h age


def test_graph_uirevision_preserves_zoom_but_resets_on_view_change(tmp_path):
    """The history graph sets uirevision so a 5 s refresh keeps the user's zoom,
    keyed to range/unit/focus so it still resets when the view domain changes."""
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    now = datetime.datetime.now()
    for i in range(4):
        db.append(_iso(now - datetime.timedelta(minutes=4 - i)), 20.0 + i, 68.0, "A")

    def rev(rng, unit):
        return build_dashboard(db, cfg, _FakeFinder(), rng, unit)[1].layout.uirevision

    base = rev("24h", "celsius")
    assert base                                   # present
    assert rev("24h", "celsius") == base          # stable across a plain refresh -> zoom kept
    assert rev("7d", "celsius") != base           # range change -> view resets
    assert rev("24h", "fahrenheit") != base       # unit change -> view resets


def test_graph_renders_mixed_second_and_millisecond_timestamps(tmp_path):
    """A probe whose window mixes pre-flash whole-second and post-flash
    millisecond timestamps must render EVERY point on the graph.

    Regression: firmware >= 2.5.0 stamps milliseconds, so after a probe is
    flashed its 24 h window contains both precisions. pandas' default
    ``to_datetime`` infers one format from the first row and coerces the other
    precision to NaT — the probe records fine (stats count it) but its points
    disappear from the chart. The parse must use ``format="ISO8601"``.
    """
    import pandas as pd
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    now = datetime.datetime.now().replace(microsecond=0)
    # pre-flash whole-second rows, then post-flash millisecond rows (oldest first)
    db.append((now - datetime.timedelta(seconds=4)).isoformat(), 20.0, 68.0, "A")
    db.append((now - datetime.timedelta(seconds=3)).isoformat(), 20.1, 68.2, "A")
    db.append((now - datetime.timedelta(seconds=2)).isoformat() + ".500", 20.2, 68.4, "A")
    db.append((now - datetime.timedelta(seconds=1)).isoformat() + ".250", 20.3, 68.5, "A")

    fig = build_dashboard(db, cfg, _FakeFinder(), "24h", "celsius")[1]
    xs = list(fig.data[0].x)
    assert len(xs) == 4                                   # all points present
    assert not any(pd.isna(x) for x in xs)               # none coerced to NaT


def test_probe_fresh_window_floor_and_interval_aware():
    # 5-minute floor out of the box
    assert probe_fresh_window({"interval_sec": 5}, "x") == 300
    # ~2.5x a slow per-probe interval wins over the floor
    assert probe_fresh_window({"probe_intervals": {"slow": 300}, "interval_sec": 5}, "slow") == 750
    # a widened offline_after_sec is honored
    assert probe_fresh_window({"offline_after_sec": 600, "interval_sec": 5}, "x") == 600


def test_diagnostics_reporting_matches_dashboard_window(tmp_path):
    """Diagnostics 'reporting' uses the same interval/offline-aware window as the
    dashboard, so the two counts can't disagree for the same probe."""
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.set("offline_after_sec", 600)  # widen the window to 10 min
    old = datetime.datetime.now() - datetime.timedelta(seconds=400)  # 400 s ago
    db.append(_iso(old), 22.0, 71.6, "P")
    d = build_diagnostics(cfg, db, _FakeFinder(), "http://hub", "2.4.1", "Setpoint")
    # 400 s < 600 s window -> counted (the old flat 300 s window would have missed it).
    assert d["probes"]["reporting"] == 1

"""Tests for the dashboard computation (components.dashboard_view.build_dashboard)."""
import datetime

import components.dashboard_view as dashboard_view
from components.dashboard_view import (build_dashboard, build_events,
                                       build_probe_cards, build_probe_stats)
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


def test_clock_format_defaults_to_24h(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    _seed(db)
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius")
    stat_min_time, stat_max_time = out[8], out[10]
    # No clock_format passed -> 24h, so no AM/PM marker.
    assert "AM" not in stat_min_time and "PM" not in stat_min_time
    assert "AM" not in stat_max_time and "PM" not in stat_max_time


def test_clock_format_12h_adds_am_pm(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    _seed(db)
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", "all", clock_format="12h")
    stat_min_time, stat_max_time = out[8], out[10]
    assert "AM" in stat_min_time or "PM" in stat_min_time
    assert "AM" in stat_max_time or "PM" in stat_max_time


def test_clock_format_12h_sets_graph_tickformatstops(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    _seed(db)
    fig_24h = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", "all", clock_format="24h")[1]
    fig_12h = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", "all", clock_format="12h")[1]
    # 24h leaves Plotly's own (already-24h) defaults untouched -> no override set.
    assert fig_24h.layout.xaxis.tickformatstops in (None, ())
    # 12h explicitly overrides with AM/PM-bearing format strings.
    stops = fig_12h.layout.xaxis.tickformatstops
    assert stops and any("%p" in s.value for s in stops)


def test_build_dashboard_fahrenheit_unit(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    db.append(_iso(datetime.datetime.now()), 25.0, 77.0, "p")
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "fahrenheit")
    gauge = out[0]
    # Gauge value converted to °F (25C -> 77F)
    assert abs(gauge.data[0].value - 77.0) < 0.01
    assert gauge.data[0].number.suffix.strip() == "°F"


def test_build_dashboard_kelvin_unit(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    db.append(_iso(datetime.datetime.now()), 25.0, 77.0, "p")
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "kelvin")
    gauge = out[0]
    # Gauge value converted to K (25C -> 298.15K)
    assert abs(gauge.data[0].value - 298.15) < 0.01
    # Kelvin uses no degree symbol
    assert gauge.data[0].number.suffix.strip() == "K"


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


def test_probe_stats_single_probe_is_empty(tmp_path):
    # One probe: the global Min/Max/Avg row already covers it, so the per-probe
    # breakdown renders nothing (no redundant clutter).
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    for i in range(3):
        db.append(_iso(datetime.datetime.now()), 20.0 + i, 0.0, "solo")
    assert build_probe_stats(db, cfg, "24h", "celsius") == []


def test_probe_stats_multi_probe_renders(tmp_path):
    # Two probes of different ranges: the per-probe breakdown appears and keeps
    # each probe's stats separate (no meaningless cross-probe average).
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"probe_names": {"A": "Freezer", "B": "Room"}})
    now = datetime.datetime.now()
    for t in (-20.0, -18.0, -16.0):
        db.append(_iso(now), t, 0.0, "A")
    for t in (20.0, 22.0, 24.0):
        db.append(_iso(now), t, 0.0, "B")
    out = build_probe_stats(db, cfg, "24h", "celsius")
    assert out != []  # rendered for 2+ probes
    # Both friendly names appear somewhere in the rendered component tree.
    text = str(out)
    assert "Freezer" in text and "Room" in text


def test_probe_stats_empty_db(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    assert build_probe_stats(db, cfg, "24h", "celsius") == []


def test_focus_mode_filters_to_one_probe(tmp_path):
    # "Focus one probe" restricts the gauge, graph and stats to the selected
    # probe, instead of the all-probes overview.
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"probe_names": {"A": "Freezer", "B": "Room"}})
    now = datetime.datetime.now()
    for t in (-20.0, -18.0, -16.0):
        db.append(_iso(now), t, 0.0, "A")
    for t in (20.0, 22.0, 24.0):
        db.append(_iso(now), t, 0.0, "B")

    allm = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", "all")
    assert len(allm[1].data) == 2          # graph overlays both probes
    # The overview no longer headlines a blended cross-probe average (a freezer
    # + a room averaged together is meaningless); it points to the per-probe
    # breakdown instead. Global Min/Max stay as the coldest/hottest anywhere.
    assert allm[11] != "2.0 °C"
    assert "probe" in allm[12].lower()     # avg tile points to per-probe stats
    assert allm[7] == "-20.0 °C"           # global min = coldest reading anywhere
    assert allm[9] == "24.0 °C"            # global max = hottest reading anywhere

    foc = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", "A")
    assert len(foc[0].data) == 1           # gauge shows one probe
    assert len(foc[1].data) == 1           # graph shows only that probe's trace
    assert foc[7] == "-20.0 °C"            # stat-min is the focused probe's own
    assert foc[9] == "-16.0 °C"            # stat-max is the focused probe's own
    assert "Freezer" in foc[6]             # range info names the focused probe


def test_focus_mode_unknown_probe_falls_back(tmp_path):
    # Selecting a probe with no data in the window falls back to the overview.
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    _seed(db)  # two probes A/B
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", "does-not-exist")
    assert len(out[1].data) == 2  # overview graph with both probes


def _line_shapes(fig):
    return [s for s in (fig.layout.shapes or ()) if s.type == "line"]


def _rect_shapes(fig):
    return [s for s in (fig.layout.shapes or ()) if s.type == "rect"]


def test_focus_mode_draws_threshold_bands(tmp_path):
    # Focus mode plots exactly one probe, so its min/max limits are drawn on the
    # history figure: a dashed hline per limit plus a wash beyond it.
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"alert_thresholds": {"A": {"min": -20.0, "max": -15.0}}})
    now = datetime.datetime.now()
    for t in (-18.0, -17.5, -17.0):
        db.append(_iso(now), t, 0.0, "A")
    db.append(_iso(now), 22.0, 71.6, "B")
    fig = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", "A")[1]
    lines, rects = _line_shapes(fig), _rect_shapes(fig)
    assert len(lines) == 2 and len(rects) == 2
    ys = sorted(s.y0 for s in lines)
    assert ys == [-20.0, -15.0]  # limit lines sit at the configured thresholds
    # y-range widened so both bands are visible beyond the data.
    y_range = fig.layout.yaxis.range
    assert y_range[0] < -20.0 and y_range[1] > -15.0


def test_focus_mode_threshold_bands_use_current_unit(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"alert_thresholds": {"A": {"max": 30.0}}})
    db.append(_iso(datetime.datetime.now()), 25.0, 77.0, "A")
    fig = build_dashboard(db, cfg, FakeFinder(), "24h", "fahrenheit", "A")[1]
    lines = _line_shapes(fig)
    assert len(lines) == 1
    assert abs(lines[0].y0 - 86.0) < 0.01  # 30 C limit drawn at 86 F


def test_focus_mode_no_thresholds_no_bands(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    db.append(_iso(datetime.datetime.now()), 21.0, 69.8, "A")
    fig = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", "A")[1]
    assert _line_shapes(fig) == [] and _rect_shapes(fig) == []


def test_single_probe_overview_draws_bands_multi_does_not(tmp_path):
    # An overview with ONE probe still gets its bands; once a second probe's
    # series is overlaid the bands are skipped (whose limits would they be?).
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"alert_thresholds": {"default": {"min": 2.0, "max": 8.0}}})
    now = datetime.datetime.now()
    db.append(_iso(now), 5.0, 41.0, "A")
    fig = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", "all")[1]
    assert len(_line_shapes(fig)) == 2
    db.append(_iso(now), 6.0, 42.8, "B")
    fig = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", "all")[1]
    assert _line_shapes(fig) == [] and _rect_shapes(fig) == []


def test_build_events_empty_returns_empty_list(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    assert build_events(db, cfg, "celsius") == []


def test_build_events_renders_compact_rows(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"probe_names": {"F": "Freezer"}})
    db.record_event("high", "F", temperature_c=-14.8, limit=-15.0)
    db.record_event("recovery", "F", temperature_c=-15.4)
    out = build_events(db, cfg, "celsius")
    text = str(out)
    assert "Recent events" in text
    assert "HIGH" in text and "RECOVERY" in text
    assert "Freezer" in text
    assert "-14.8 °C" in text and "limit -15.0" in text


def test_build_events_converts_temperature_unit(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    db.record_event("high", "F", temperature_c=30.0, limit=25.0)
    text = str(build_events(db, cfg, "fahrenheit"))
    assert "86.0 °F" in text and "limit 77.0" in text


def test_build_events_caps_at_limit(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    for i in range(12):
        db.record_event("high", "F", temperature_c=30.0 + i, limit=25.0)
    out = build_events(db, cfg, "celsius", limit=8)
    rows = out.children[1].children
    assert len(rows) == 8


class _HeldStub:
    def __init__(self, states=None):
        self._s = states or {}

    def get(self, pid):
        return self._s.get(pid)


def test_probe_card_recovering_when_held(tmp_path, monkeypatch):
    # Reading back inside the limit but still HELD by the alert monitor's
    # hysteresis -> the card shows amber "recovering", not green OK.
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"alert_thresholds": {"A": {"max": 30.0}}})
    db.append(_iso(datetime.datetime.now()), 29.5, 85.1, "A")  # inside the limit
    monkeypatch.setattr(dashboard_view, "HELD", _HeldStub({"A": "high"}))
    text = str(build_probe_cards(db, cfg, "celsius"))
    assert "recovering" in text and "warning" in text
    assert "● OK" not in text


def test_probe_card_ok_when_not_held(tmp_path, monkeypatch):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"alert_thresholds": {"A": {"max": 30.0}}})
    db.append(_iso(datetime.datetime.now()), 29.5, 85.1, "A")
    monkeypatch.setattr(dashboard_view, "HELD", _HeldStub())
    text = str(build_probe_cards(db, cfg, "celsius"))
    assert "● OK" in text and "recovering" not in text


def test_probe_card_breach_outranks_held(tmp_path, monkeypatch):
    # A live breach must still show HIGH even while the registry holds it.
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"alert_thresholds": {"A": {"max": 30.0}}})
    db.append(_iso(datetime.datetime.now()), 31.0, 87.8, "A")
    monkeypatch.setattr(dashboard_view, "HELD", _HeldStub({"A": "high"}))
    text = str(build_probe_cards(db, cfg, "celsius"))
    assert "HIGH" in text and "recovering" not in text


def test_probe_card_shows_battery_when_present(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    db.append(_iso(datetime.datetime.now()), 21.0, 69.8, "A", battery=87.0)
    db.append(_iso(datetime.datetime.now()), 22.0, 71.6, "B")  # no battery field
    text = str(build_probe_cards(db, cfg, "celsius"))
    assert "Batt 87%" in text
    assert text.count("Batt") == 1  # probe without battery gets no line


def test_probe_card_battery_low_is_warning(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    db.append(_iso(datetime.datetime.now()), 21.0, 69.8, "A", battery=15.0)
    text = str(build_probe_cards(db, cfg, "celsius"))
    assert "Batt 15%" in text and "text-warning" in text


def test_focus_stays_on_probe_with_no_in_range_data(tmp_path):
    # A probe whose last reading is older than the chosen range but within the
    # last week (so it's still selectable) must STAY focused — the gauge shows its
    # last value and the graph/stats are its own (empty), never silently reverting
    # to the all-probes overview while the selector still names it.
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"probe_names": {"A": "Freezer", "B": "Room"}})
    now = datetime.datetime.now()
    three_h_ago = _iso(now - datetime.timedelta(hours=3))
    db.append(three_h_ago, -18.0, 0.0, "A")     # A: only an old reading
    db.append(_iso(now), 22.0, 0.0, "B")        # B: live
    out = build_dashboard(db, cfg, FakeFinder(), "1h", "celsius", "A")
    assert len(out[0].data) == 1        # gauge shows the focused probe (last value)
    assert abs(out[0].data[0].value - (-18.0)) < 0.01
    assert len(out[1].data) == 0        # no A data in the last hour -> empty graph
    assert "Freezer" in out[6]          # range info stays scoped to A
    assert out[7] == "N/A"              # stats are A's own (none in range)

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


def _series(fig):
    """The visible probe line traces, excluding the invisible y-fit anchor trace
    (mode='markers') the graph adds to drive autorange without pinning a range."""
    return [t for t in fig.data if getattr(t, "mode", None) == "lines"]


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
    # 14 values + the three stat-value classNames, which are driven now so an
    # empty hub does not colour "MAX" in alarm red when nothing is wrong.
    assert len(out) == 17
    # metric-lastupdate is "(no data)" when empty
    assert out[3] == "(no data)"


def test_build_dashboard_with_data(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    _seed(db)
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius")
    gauge, fig, probes, lastupd, logging_status, hb, range_info = out[:7]
    # Two probes -> two traces, legend shown
    assert len(_series(fig)) == 2
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
    # Regression: NO tier may fall back to the 24-hour %H token in 12h mode — the
    # sub-second tier used to, so a zoomed-in high-cadence chart mixed
    # "14:30:05.1" ticks with "2:30:05 PM" hovers.
    assert not any("%H" in s.value for s in stops)


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
    names = {tr.name for tr in _series(fig)}
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
    for i, t in enumerate((-20.0, -18.0, -16.0)):
        db.append(_iso(now - datetime.timedelta(seconds=i)), t, 0.0, "A")
    for i, t in enumerate((20.0, 22.0, 24.0)):
        db.append(_iso(now - datetime.timedelta(seconds=i)), t, 0.0, "B")

    allm = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", "all")
    assert len(_series(allm[1])) == 2      # graph overlays both probes
    # The overview no longer headlines a blended cross-probe average (a freezer
    # + a room averaged together is meaningless); it points to the per-probe
    # breakdown instead. Global Min/Max stay as the coldest/hottest anywhere.
    assert allm[11] != "2.0 °C"
    assert "probe" in allm[12].lower()     # avg tile points to per-probe stats
    assert allm[7] == "-20.0 °C"           # global min = coldest reading anywhere
    assert allm[9] == "24.0 °C"            # global max = hottest reading anywhere

    foc = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", "A")
    assert len(foc[0].data) == 1           # gauge shows one probe
    assert len(_series(foc[1])) == 1       # graph shows only that probe's trace
    assert foc[7] == "-20.0 °C"            # stat-min is the focused probe's own
    assert foc[9] == "-16.0 °C"            # stat-max is the focused probe's own
    assert "Freezer" in foc[6]             # range info names the focused probe


def test_focus_mode_unknown_probe_falls_back(tmp_path):
    # Selecting a probe with no data in the window falls back to the overview.
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    _seed(db)  # two probes A/B
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", "does-not-exist")
    assert len(_series(out[1])) == 2  # overview graph with both probes


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
    # The y-fit is carried by an invisible anchor trace (not an explicit
    # yaxis.range, which would fight uirevision on refresh — see
    # test_graph_uirevision_preserves_zoom_but_resets_on_view_change). No range
    # is pinned, and the anchor spans beyond both bands so autorange shows them.
    assert fig.layout.yaxis.range is None
    anchor = fig.data[-1]
    assert min(anchor.y) < -20.0 and max(anchor.y) > -15.0


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


def test_build_events_coalesces_connectivity_flaps(tmp_path):
    # A probe flapping online/offline collapses to ONE summary row, not many.
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"probe_names": {"R": "Refrigerator"}})
    now = datetime.datetime.now()
    for i in range(4):  # 4 offline/online pairs = 8 raw connectivity events
        db.record_event("offline", "R", ts=_iso(now - datetime.timedelta(minutes=40 - i * 8)))
        db.record_event("online", "R", ts=_iso(now - datetime.timedelta(minutes=39 - i * 8)))
    out = build_events(db, cfg, "celsius")
    rows = out.children[1].children
    assert len(rows) == 1                       # coalesced, not 8
    text = str(out)
    assert "Refrigerator" in text and "flapping (4" in text


def test_build_events_alert_survives_connectivity_noise(tmp_path):
    # Heavy connectivity churn must not bury a real threshold alert.
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    now = datetime.datetime.now()
    db.record_event("high", "F", temperature_c=-14.8, limit=-15.0,
                    ts=_iso(now - datetime.timedelta(minutes=5)))
    for i in range(10):  # 20 connectivity events from one probe
        db.record_event("offline", "R", ts=_iso(now - datetime.timedelta(minutes=30 - i)))
        db.record_event("online", "R", ts=_iso(now - datetime.timedelta(minutes=30 - i, seconds=-30)))
    out = build_events(db, cfg, "celsius", limit=8)
    rows = out.children[1].children
    assert len(rows) == 2                        # 1 alert + 1 coalesced connectivity
    text = str(out)
    assert "HIGH" in text and "-14.8 °C" in text  # the alert is still shown
    assert "flapping (10" in text


def test_build_events_alert_survives_connectivity_flood_beyond_fetch_window(tmp_path):
    # Regression for the fetch-window eviction bug: a flapping probe emitting FAR
    # more connectivity events than a single fetch would hold must NOT evict a
    # genuine alert. With limit=8 the old combined query capped at 64 raw rows,
    # so ~90 online/offline events newer than the alert dropped the breach from
    # the feed entirely. Alerts are now fetched in their own kind-filtered query.
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    now = datetime.datetime.now()
    db.record_event("high", "F", temperature_c=-14.8, limit=-15.0,
                    ts=_iso(now - datetime.timedelta(hours=3)))
    for i in range(45):  # 90 connectivity events, all NEWER than the alert
        db.record_event("offline", "R", ts=_iso(now - datetime.timedelta(minutes=90 - i)))
        db.record_event("online", "R", ts=_iso(now - datetime.timedelta(minutes=90 - i, seconds=-30)))
    out = build_events(db, cfg, "celsius", limit=8)
    rows = out.children[1].children
    assert len(rows) == 2                          # 1 alert + 1 coalesced connectivity
    text = str(out)
    assert "HIGH" in text and "-14.8 °C" in text   # breach NOT evicted by the flood


def test_relative_time_buckets():
    from components.dashboard_view import _relative_time
    now = 1_000_000
    assert _relative_time(now - 10, now=now) == "just now"
    assert _relative_time(now - 120, now=now) == "2m ago"
    assert _relative_time(now - 7200, now=now) == "2h ago"
    assert _relative_time(now - 172800, now=now) == "2d ago"
    assert _relative_time("bad", now=now) == ""


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


def test_graph_layout_is_zoom_stable(tmp_path):
    """The plot rectangle must not move while the user zooms.

    Plotly's margin.autoexpand re-measures the plot area whenever a tick label
    changes width, and zooming changes both: the y labels gain decimals and the
    final x label lengthens. With the old tight margins (l=0, r=10) and a free
    y tick format, that dragged the chart's edges 13-20 px (left) and 14-24 px
    (right) as the user zoomed — measured in Chromium at 900x360.

    Two things hold it still, and both must stay:
      * generous fixed margins, so autoexpand has slack it never needs to claim;
      * a pinned 2-decimal y tick format, so every label is the same width at
        every zoom depth. Margins alone cannot fix the y side — there is always
        one more decimal a deeper zoom can add.
    """
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    _seed(db)
    for unit in ("celsius", "fahrenheit"):
        for clock in ("24h", "12h"):
            fig = build_dashboard(db, cfg, FakeFinder(), "24h", unit, "all",
                                  clock_format=clock)[1]
            m = fig.layout.margin
            assert m.l >= 72, f"left margin {m.l} too tight ({unit}/{clock})"
            assert m.r >= 48, f"right margin {m.r} too tight ({unit}/{clock})"
            assert fig.layout.yaxis.tickformat == ".2f", (
                f"y tickformat must be pinned ({unit}/{clock}); a free format "
                "widens labels as the user zooms and drags the plot area left")


def test_gauge_number_matches_shared_formatter_in_every_unit():
    """The gauge's big number must use the same precision as every other readout.

    Plotly's Indicator picks ~3 significant digits from the value's magnitude
    when valueformat is unset. That happens to render one decimal in C and F
    but drops it in Kelvin, so the same reading showed "19.8 °C" / "67.7 °F"
    but "293 K" while the stat cards beside it — which all go through _fmt() —
    said "293.0 K". Pinning valueformat keeps the largest number on the page
    consistent with the small ones.
    """
    from components.dashboard_view import _make_gauge, _fmt, _unit_symbol
    for unit in ("celsius", "fahrenheit", "kelvin"):
        sym = _unit_symbol(unit)
        ind = _make_gauge("P", 19.83, 2.0, 5.0, unit, " " + sym).data[0]
        assert ind.number.valueformat == ".1f", f"{unit}: gauge valueformat unpinned"
        assert f"{ind.value:.1f} {sym}" == _fmt(19.83, unit), (
            f"{unit}: gauge number disagrees with _fmt()")


def test_empty_hub_uses_muted_stat_colours_not_alarm_red(tmp_path):
    """A brand-new hub showed "N/A" for MAX in text-danger red, which reads as a
    fault on a hub whose only condition is that nobody has connected a probe
    yet. The three value classNames are the last three outputs."""
    db = Database(tmp_path / "empty.db")
    cfg = Config(tmp_path / "c.json")
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius")
    min_cls, max_cls, avg_cls = out[-3], out[-2], out[-1]
    assert "text-danger" not in max_cls, "empty MAX still painted as an alarm"
    for cls in (min_cls, max_cls, avg_cls):
        assert "text-muted" in cls


def test_populated_hub_keeps_the_scannable_stat_colours(tmp_path):
    """Muting must apply only to the empty state — the tiles still need to be
    readable at a glance. Colour must not be alarm red for a peak that never
    crossed anything, though; see the tests below."""
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    db.append(datetime.datetime.now().isoformat(timespec="milliseconds"), 4.0, 39.2, "P1")
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius")
    for cls in (out[-3], out[-2], out[-1]):
        assert "text-muted" not in cls, "live values are muted as though empty"
    assert "text-info" in out[-3] and "text-success" in out[-1]


def _stat_classes(tmp_path, temp_c, thresholds, name="s.db"):
    db = Database(tmp_path / name)
    cfg = Config(tmp_path / (name + ".json"))
    if thresholds:
        cfg.update({"alert_thresholds": {"P1": thresholds}})
    db.append(datetime.datetime.now().isoformat(timespec="milliseconds"),
              temp_c, temp_c * 9 / 5 + 32, "P1")
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius")
    return out[-3], out[-2]          # min class, max class


def test_the_max_tile_is_not_alarm_red_for_a_peak_inside_its_limits(tmp_path):
    """MAX was painted text-danger unconditionally — in the static markup and in
    the callback — so a Prep Room peaking at 22.9 °C inside an 18–25 °C band sat
    in the KPI row looking like an incident. Red means "a limit was crossed"
    everywhere else on this page; a colour that fires for every reading teaches
    the operator to ignore the one colour that must never be ignored."""
    _min_cls, max_cls = _stat_classes(tmp_path, 22.9, {"min": 18.0, "max": 25.0})
    assert "text-danger" not in max_cls, "a normal peak is still painted as an alarm"


def test_the_max_tile_is_alarm_red_when_the_peak_really_did_breach(tmp_path):
    _min_cls, max_cls = _stat_classes(tmp_path, 26.5, {"min": 18.0, "max": 25.0},
                                      name="hot.db")
    assert "text-danger" in max_cls


def test_the_min_tile_is_alarm_red_when_the_low_really_did_breach(tmp_path):
    min_cls, _max = _stat_classes(tmp_path, -30.0, {"min": -22.0, "max": -15.0},
                                  name="cold.db")
    assert "text-danger" in min_cls


def test_an_unwatched_probe_never_paints_either_tile_red(tmp_path):
    """With no limits set nothing has been crossed, because nothing is being
    checked. Inventing a breach here would be the same false signal."""
    min_cls, max_cls = _stat_classes(tmp_path, 95.0, None, name="wild.db")
    assert "text-danger" not in min_cls and "text-danger" not in max_cls


def test_the_overview_average_is_not_a_word_in_the_number_slot(tmp_path):
    """Across a −18 °C freezer and a 21 °C room a blended average is a number no
    probe is near, so the overview does not headline one. But it used to print
    the WORD "Per-probe" in the big bold slot the other two tiles fill with a
    temperature, which reads as a failed render — in the KPI row, the part of the
    page people scan first."""
    db = Database(tmp_path / "multi.db")
    cfg = Config(tmp_path / "multi.json")
    now = datetime.datetime.now().isoformat(timespec="milliseconds")
    db.append(now, -18.5, -1.3, "Freezer")
    db.append(now, 21.4, 70.5, "Room")
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius")
    stat_avg, stat_avg_info = out[11], out[12]
    assert stat_avg == "—", f"still a word where a number goes: {stat_avg!r}"
    assert "More detail" in stat_avg_info, "the explanation went missing with it"
    assert "text-success" not in out[-1], \
        "an em-dash is not a value and must not be dressed as a healthy one"


def test_a_single_probe_still_gets_a_real_average(tmp_path):
    """The em-dash is only for the mixed-fleet overview. One probe — or one
    focused probe — has a meaningful window average, and it is what a compliance
    report is built from."""
    db = Database(tmp_path / "one.db")
    cfg = Config(tmp_path / "one.json")
    now = datetime.datetime.now()
    for i in range(5):
        ts = (now - datetime.timedelta(minutes=i)).isoformat(timespec="milliseconds")
        db.append(ts, 4.0, 39.2, "P1")
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius")
    assert out[11] != "—" and "°C" in out[11]

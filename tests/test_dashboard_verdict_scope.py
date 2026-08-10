"""Every verdict on the dashboard, resolved by the same rule.

``core.status.limits_for`` is the one place that answers "which limits may THIS
hub judge this probe by?", and its answer for a forwarded probe is "none" --
thresholds are per hub and are not forwarded, so head office running fridges
(0..8 C) judging a store freezer at -19 C is not a near miss, it is a different
question. ``build_probe_cards`` was migrated to it. Four other verdicts in the
same file were not, and each disagreed with the card sitting next to it:

  * the alert banner, which raised a red "below threshold" for every healthy
    forwarded freezer;
  * the worst-breach gauge picker, which then chose one of those as the thing
    most needing attention;
  * the gauge's own threshold zones and the chart's threshold bands, which
    painted a healthy trace inside a red wash;
  * the MIN/MAX stat tiles, whose lookup was also the only one in the codebase
    with no ``default`` fallback -- so on a hub whose limits are global rather
    than per probe they could never turn red at all.

Plus two things that were not about limits: the focus-mode gauge only knew a
reading was stale when alert thresholds happened to be configured, and chart
line colours were keyed to a probe's position in the selected window, so two
probes swapped colours when the range changed.
"""
import datetime

import pytest

from components.dashboard_view import build_dashboard
from core.db import Database

ALERTS = 13
GAUGE = 0
STAT_MIN_CLASS = 14
STAT_MAX_CLASS = 15
STAT_BREACH = "fw-bold text-danger mb-0"


class _Cfg(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


class _NoFinder:
    def list_probes(self):
        return {}


def _hq(tmp_path, thresholds):
    """Head office: its own fridge at 5 C, plus a store freezer at -19 C."""
    db = Database(tmp_path / "hq.db")
    now = datetime.datetime.now()

    def add(pid, temp_c, site="", seconds_ago=5):
        ts = now - datetime.timedelta(seconds=seconds_ago)
        db.append(ts.isoformat(timespec="milliseconds"), temp_c, temp_c * 9 / 5 + 32,
                  pid, site=site, epoch=ts.timestamp())

    add("HQ-Fridge", 5.0)
    add("Walkin", -19.0, site="savannah")
    cfg = _Cfg({"alert_thresholds": thresholds, "settings": {},
                "notifications": {}, "calibration_offsets": {}, "probe_names": {}})
    return db, cfg


def test_the_banner_does_not_alarm_on_another_hubs_probe(tmp_path):
    db, cfg = _hq(tmp_path, {"default": {"min": 0.0, "max": 8.0}})
    out = build_dashboard(db, cfg, _NoFinder(), "24h", "celsius")
    text = str(out[ALERTS])
    assert "Walkin" not in text, "head office judged a store freezer by its own limits"


def test_this_hubs_own_probes_still_alarm_beside_a_forwarded_one(tmp_path):
    db, cfg = _hq(tmp_path, {"default": {"min": 10.0, "max": 20.0}})
    out = build_dashboard(db, cfg, _NoFinder(), "24h", "celsius")
    text = str(out[ALERTS])
    assert "HQ-Fridge" in text, "the local probe must still be judged"
    assert "Walkin" not in text


def test_the_gauge_picks_a_local_breach_over_a_forwarded_one(tmp_path):
    # -19 against a 0 C floor is a 19-degree "breach" and would win the
    # worst-breach contest outright, if this hub were entitled to judge it.
    db, cfg = _hq(tmp_path, {"default": {"min": 0.0, "max": 4.0}})
    out = build_dashboard(db, cfg, _NoFinder(), "24h", "celsius")
    assert "Walkin" not in str(out[GAUGE])


def test_the_stat_tiles_turn_red_on_a_default_only_threshold(tmp_path):
    db = Database(tmp_path / "d.db")
    now = datetime.datetime.now()
    for temp in (26.5, 4.0):
        ts = now - datetime.timedelta(seconds=5)
        db.append(ts.isoformat(timespec="milliseconds"), temp, temp * 9 / 5 + 32,
                  "P1", epoch=ts.timestamp() + temp)
    cfg = _Cfg({"alert_thresholds": {"default": {"min": 2.0, "max": 8.0}},
                "settings": {}, "notifications": {}, "calibration_offsets": {},
                "probe_names": {}})
    out = build_dashboard(db, cfg, _NoFinder(), "24h", "celsius")
    assert out[STAT_MAX_CLASS] == STAT_BREACH
    assert len(out[ALERTS]) == 1, "the banner agreed all along — the tile did not"


def test_a_forwarded_extreme_does_not_redden_a_stat_tile(tmp_path):
    db, cfg = _hq(tmp_path, {"default": {"min": 0.0, "max": 8.0}})
    out = build_dashboard(db, cfg, _NoFinder(), "24h", "celsius")
    assert out[STAT_MIN_CLASS] != STAT_BREACH, \
        "the MIN came from a store freezer this hub may not judge"


# --- the focused gauge knows it is stale without needing thresholds ---------

@pytest.mark.parametrize("thresholds", [{}, {"P1": {"min": 0.0, "max": 8.0}}])
def test_a_focused_gauge_is_muted_when_its_probe_has_gone_quiet(tmp_path, thresholds):
    db = Database(tmp_path / "f.db")
    now = datetime.datetime.now()
    old = now - datetime.timedelta(hours=3)
    db.append(old.isoformat(timespec="milliseconds"), 4.0, 39.2, "P1",
              epoch=old.timestamp())
    fresh = now - datetime.timedelta(seconds=5)
    db.append(fresh.isoformat(timespec="milliseconds"), 4.0, 39.2, "P2",
              epoch=fresh.timestamp())
    cfg = _Cfg({"alert_thresholds": thresholds, "settings": {}, "notifications": {},
                "calibration_offsets": {}, "probe_names": {}})
    out = build_dashboard(db, cfg, _NoFinder(), "24h", "celsius", focus_probe="P1")
    assert "last known" in str(out[GAUGE]), \
        "gauge freshness must not depend on whether alerts are configured"


def test_a_focused_live_probe_is_not_muted(tmp_path):
    db = Database(tmp_path / "f.db")
    fresh = datetime.datetime.now() - datetime.timedelta(seconds=5)
    db.append(fresh.isoformat(timespec="milliseconds"), 4.0, 39.2, "P1",
              epoch=fresh.timestamp())
    cfg = _Cfg({"alert_thresholds": {}, "settings": {}, "notifications": {},
                "calibration_offsets": {}, "probe_names": {}})
    out = build_dashboard(db, cfg, _NoFinder(), "24h", "celsius", focus_probe="P1")
    assert "last known" not in str(out[GAUGE])


# --- a probe keeps its colour when the range changes ------------------------

def _colors(fig):
    return [t.line.color for t in fig.data if getattr(t, "line", None) is not None]


def test_a_probe_keeps_its_line_colour_across_range_changes(tmp_path):
    # A's points are old and recent; B's are only recent. Ordering by first row
    # inside the window therefore puts B first at "1h" and A first at "24h".
    db = Database(tmp_path / "c.db")
    now = datetime.datetime.now()
    for pid, mins in (("A", (300, 10)), ("B", (50, 5))):
        for m in mins:
            ts = now - datetime.timedelta(minutes=m)
            db.append(ts.isoformat(timespec="milliseconds"), 4.0, 39.2, pid,
                      epoch=ts.timestamp())
    cfg = _Cfg({"alert_thresholds": {}, "settings": {}, "notifications": {},
                "calibration_offsets": {}, "probe_names": {}})
    by_range = {}
    for rng in ("1h", "24h"):
        fig = build_dashboard(db, cfg, _NoFinder(), rng, "celsius")[GAUGE + 1]
        by_range[rng] = {t.name: t.line.color for t in fig.data}
    assert by_range["1h"]["A"] == by_range["24h"]["A"]
    assert by_range["1h"]["B"] == by_range["24h"]["B"]
    assert by_range["24h"]["A"] != by_range["24h"]["B"], "and still distinguishable"


# --- the download button exports what the screen is showing -----------------

@pytest.mark.parametrize("picked,expected", [
    ("all", []),
    (None, []),
    ("savannah", ["site=savannah"]),
    ("", []),                       # the picker's "nothing selected" == all
])
def test_the_site_picker_becomes_a_download_parameter(picked, expected):
    from components.dashboard_view import _site_param
    assert _site_param(picked) == expected


def test_an_export_scoped_to_one_store_leaves_the_others_out(tmp_path):
    db, _cfg = _hq(tmp_path, {})
    import io
    for site, expect_in, expect_out in (("savannah", "Walkin", "HQ-Fridge"),
                                        ("", "HQ-Fridge", "Walkin")):
        buf = io.StringIO()
        db.export_csv(buf, site=site)
        body = buf.getvalue()
        assert expect_in in body
        assert expect_out not in body, f"site={site!r} leaked another hub's rows"


def test_an_export_with_no_site_still_carries_every_store(tmp_path):
    db, _cfg = _hq(tmp_path, {})
    import io
    buf = io.StringIO()
    db.export_csv(buf)
    assert "Walkin" in buf.getvalue() and "HQ-Fridge" in buf.getvalue()


def test_count_readings_can_be_scoped_to_a_store(tmp_path):
    db, _cfg = _hq(tmp_path, {})
    assert db.count_readings() == 2
    assert db.count_readings(site="savannah") == 1
    assert db.count_readings(site="") == 1, \
        "'' means this hub's own probes, not 'no filter'"


def test_two_probes_on_one_chart_never_share_a_colour(tmp_path):
    """Stability must not be bought with ambiguity.

    Keying colour to a store-wide ordinal is perfectly stable, but PROBE_COLORS
    has twelve entries — so on a hub with more than twelve probes two lines on
    the same chart could land on the same colour, which is worse than the
    instability being fixed. Sorted-among-those-present gives both.
    """
    from components.dashboard_view import PROBE_COLORS
    db = Database(tmp_path / "many.db")
    now = datetime.datetime.now()
    # 20 probes in the store, 6 of them in the visible window.
    for n in range(20):
        ts = now - datetime.timedelta(days=30)
        db.append(ts.isoformat(timespec="milliseconds"), 4.0, 39.2, f"P{n:02d}",
                  epoch=ts.timestamp() + n)
    for n in (0, 3, 7, 12, 15, 19):
        ts = now - datetime.timedelta(minutes=n + 1)
        db.append(ts.isoformat(timespec="milliseconds"), 4.0, 39.2, f"P{n:02d}",
                  epoch=ts.timestamp())
    cfg = _Cfg({"alert_thresholds": {}, "settings": {}, "notifications": {},
                "calibration_offsets": {}, "probe_names": {}})
    fig = build_dashboard(db, cfg, _NoFinder(), "1h", "celsius")[GAUGE + 1]
    # Line traces only — the chart also carries an unnamed marker trace for the
    # latest point.
    colours = [t.line.color for t in fig.data
               if t.name and getattr(t.line, "color", None)]
    assert len(colours) == 6, colours
    assert len(set(colours)) == len(colours), \
        f"two probes drawn in the same colour: {colours}"
    assert set(colours) <= set(PROBE_COLORS)

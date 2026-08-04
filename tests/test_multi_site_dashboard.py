"""HQ roll-up: the dashboard's site filter and per-card site attribution.

A hub that no other hub forwards to must look exactly as it always did — the
site control is invisible and every query is unfiltered. A hub holding forwarded
readings gets an "all sites / one store" picker, and cards say which building a
probe is in, because "Walk-in" alone is ambiguous across six stores.
"""
import datetime

from components.dashboard_view import (build_dashboard, build_events,
                                       build_probe_cards, build_probe_stats,
                                       _render_sig)
from core.config import Config
from core.db import Database
from core.status import reporting_probe_ids


class FakeFinder:
    def list_probes(self):
        return {}


def _seed(db, probe, site="", n=3, base=4.0):
    now = datetime.datetime.now()
    for i in range(n):
        ts = (now - datetime.timedelta(seconds=n - i)).isoformat(timespec="milliseconds")
        db.append(ts, base + i * 0.1, 39.0, probe, site=site)


def test_single_site_hub_is_unchanged(tmp_path):
    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    _seed(db, "Local-1")
    assert db.sites() == []            # nothing forwarded -> no picker
    out = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius")
    assert out[6]                       # range info still renders


def test_site_filter_narrows_every_number(tmp_path):
    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    _seed(db, "ATL-Walkin", site="atlanta", n=3, base=4.0)
    _seed(db, "MAR-Walkin", site="marietta", n=5, base=20.0)
    assert db.sites() == ["atlanta", "marietta"]

    all_sites = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", site="all")
    atl = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", site="atlanta")

    # Chart traces: both stores vs one.
    assert len([t for t in all_sites[1].data if getattr(t, "mode", "") == "lines"]) == 2
    assert len([t for t in atl[1].data if getattr(t, "mode", "") == "lines"]) == 1
    # Min/max describe only the selected store (atlanta sits near 4 °C, not 20).
    assert "4." in atl[7] and "20" not in atl[7]


def test_denominator_is_scoped_to_the_selected_site(tmp_path):
    """'Showing 3 of 8' across stores would read as catastrophic data loss."""
    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    _seed(db, "ATL", site="atlanta", n=3)
    _seed(db, "MAR", site="marietta", n=5)
    info = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", site="atlanta")[6]
    assert "of 3" in info, info


def test_probe_cards_name_the_site_only_when_there_is_one(tmp_path):
    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    _seed(db, "Fwd", site="atlanta")
    _seed(db, "Local", site="")
    rendered = str(build_probe_cards(db, cfg, "celsius"))
    assert "atlanta" in rendered            # forwarded probe is attributed
    assert rendered.count("⌂") == 1         # the local probe gains no badge


def test_probe_cards_narrow_to_the_selected_site(tmp_path):
    """The chart filtering while the card grid still shows all six stores would
    be worse than no filter at all — the two halves of the page would disagree."""
    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    _seed(db, "ATL-Walkin", site="atlanta")
    _seed(db, "MAR-Walkin", site="marietta")
    _seed(db, "HQ-Rack", site="")

    everything = str(build_probe_cards(db, cfg, "celsius", site="all"))
    assert "ATL-Walkin" in everything and "MAR-Walkin" in everything and "HQ-Rack" in everything

    atl = str(build_probe_cards(db, cfg, "celsius", site="atlanta"))
    assert "ATL-Walkin" in atl
    assert "MAR-Walkin" not in atl
    assert "HQ-Rack" not in atl          # HQ's own probes are a site too


def test_probe_stats_narrow_to_the_selected_site(tmp_path):
    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    _seed(db, "ATL-A", site="atlanta")
    _seed(db, "ATL-B", site="atlanta")
    _seed(db, "MAR-A", site="marietta")
    _seed(db, "MAR-B", site="marietta")

    atl = str(build_probe_stats(db, cfg, "24h", "celsius", site="atlanta"))
    assert "ATL-A" in atl and "ATL-B" in atl
    assert "MAR-A" not in atl and "MAR-B" not in atl


def test_one_probe_in_a_site_hides_the_per_probe_breakdown(tmp_path):
    """The 2+ probe rule has to be evaluated AFTER the site filter, or a store
    with one probe gets a per-probe panel that just repeats the headline stats."""
    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    _seed(db, "ATL-Only", site="atlanta")
    _seed(db, "MAR-A", site="marietta")
    _seed(db, "MAR-B", site="marietta")
    assert build_probe_stats(db, cfg, "24h", "celsius", site="atlanta") == []
    assert build_probe_stats(db, cfg, "24h", "celsius", site="all") != []


def test_connected_probes_kpi_is_scoped_to_the_selected_site(tmp_path):
    """'Connected Probes 8' over three cards reads as six missing probes."""
    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    _seed(db, "ATL-A", site="atlanta")
    _seed(db, "ATL-B", site="atlanta")
    _seed(db, "MAR-A", site="marietta")
    _seed(db, "HQ", site="")
    assert build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", site="all")[2] == "4"
    assert build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", site="atlanta")[2] == "2"


def test_metrics_and_api_still_count_the_whole_hub(tmp_path):
    """The dashboard's site filter is a view control. A Prometheus scrape wants
    the hub, not whatever a browser tab happens to be showing."""
    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    _seed(db, "ATL", site="atlanta")
    _seed(db, "MAR", site="marietta")
    _seed(db, "HQ", site="")
    assert len(reporting_probe_ids(cfg, db)) == 3
    assert reporting_probe_ids(cfg, db, site="atlanta") == {"ATL"}


def test_gauge_follows_the_selected_site(tmp_path):
    """The gauge picks the worst active breach. Captioned with a Savannah probe
    over an Atlanta chart it would be worse than useless."""
    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    cfg.set("alert_thresholds", {"default": {"min": 0.0, "max": 8.0}})
    _seed(db, "ATL-Walkin", site="atlanta", base=4.0)          # in spec
    _seed(db, "SAV-Walkin", site="savannah", base=31.0)        # badly HIGH

    everything = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", site="all")
    assert "SAV-Walkin" in str(everything[0].data[0].title.text)

    atl = build_dashboard(db, cfg, FakeFinder(), "24h", "celsius", site="atlanta")
    assert "ATL-Walkin" in str(atl[0].data[0].title.text)


def test_recent_events_narrow_to_the_hub_that_recorded_them(tmp_path):
    """An event belongs to the hub whose alert engine decided it.

    Filtering to a store therefore shows what THAT store alerted on, against its
    own thresholds — the record an auditor asks for — rather than head office's
    re-evaluation of the same readings.
    """
    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    _seed(db, "ATL-Walkin", site="atlanta")
    _seed(db, "SAV-Freezer", site="savannah")
    db.record_event("high", "ATL-Walkin", 9.1, 8.0, site="atlanta")
    db.record_event("offline", "SAV-Freezer", site="savannah")
    db.record_event("high", "HQ-Rack", 40.0, 35.0)          # head office's own

    everything = str(build_events(db, cfg, "celsius", site="all"))
    assert all(p in everything for p in ("ATL-Walkin", "SAV-Freezer", "HQ-Rack"))

    atl = str(build_events(db, cfg, "celsius", site="atlanta"))
    assert "ATL-Walkin" in atl
    assert "SAV-Freezer" not in atl
    assert "HQ-Rack" not in atl


def test_forwarded_events_are_deduped_but_local_ones_are_not(tmp_path):
    """Event epochs are whole seconds, so a blanket unique key would treat two
    genuinely distinct same-second events as a replay. The constraint covers
    forwarded rows only — the one place a replay can actually happen."""
    db = Database(tmp_path / "d.db")
    ts = "2026-08-04T10:00:00"
    for _ in range(5):                       # a store's batch, re-sent 5 times
        db.record_event("high", "walkin", 9.1, 8.0, ts=ts, site="atlanta")
    assert len(db.list_events(site="atlanta")) == 1

    for _ in range(5):                       # local events keep their old freedom
        db.record_event("high", "walkin", 9.1, 8.0, ts=ts)
    assert len(db.list_events(site="")) == 5


def test_alerts_still_see_every_site(tmp_path):
    """A breach in store 3 is still a breach while head office looks at store 1,
    so the alert path must keep querying unfiltered."""
    db = Database(tmp_path / "d.db")
    _seed(db, "ATL", site="atlanta")
    _seed(db, "MAR", site="marietta")
    _seed(db, "HQ", site="")
    assert sorted(db.latest_per_probe()["probe_id"]) == ["ATL", "HQ", "MAR"]
    assert sorted(db.latest_per_probe(site="")["probe_id"]) == ["HQ"]


def test_render_signature_changes_with_site(tmp_path):
    """Otherwise switching site would be swallowed by the refresh tick gate."""
    latest = {"timestamp": "2026-08-04T00:00:00"}
    a = _render_sig(latest, "24h", "celsius", "all", "24h", now=0, site="all")
    b = _render_sig(latest, "24h", "celsius", "all", "24h", now=0, site="atlanta")
    assert a != b


def test_empty_site_means_this_hubs_own_probes_in_every_query(tmp_path):
    """All five site-aware queries must read '' the same way.

    A truthiness test instead of `is not None` makes site='' mean "no filter" in
    some methods and "HQ's own probes" in others — which is exactly how the chart
    ends up showing six stores while the cards correctly show one.
    """
    db = Database(tmp_path / "d.db")
    _seed(db, "LOCAL", site="")
    _seed(db, "ATL", site="atlanta")

    assert db.window_stats(site="")["count"] == 3
    assert sorted(db.window_df(site="")["probe_id"].unique()) == ["LOCAL"]
    assert sorted(db.stats_per_probe(site="")) == ["LOCAL"]
    assert sorted(db.latest_per_probe(site="")["probe_id"]) == ["LOCAL"]
    assert sorted(db.last_reading_epoch_per_probe(site="")) == ["LOCAL"]

    # ...and None still means every site, for all five.
    assert db.window_stats()["count"] == 6
    assert sorted(db.window_df()["probe_id"].unique()) == ["ATL", "LOCAL"]
    assert sorted(db.stats_per_probe()) == ["ATL", "LOCAL"]
    assert sorted(db.latest_per_probe()["probe_id"]) == ["ATL", "LOCAL"]
    assert sorted(db.last_reading_epoch_per_probe()) == ["ATL", "LOCAL"]


def test_sites_uses_the_index_not_a_full_scan(tmp_path):
    """The picker re-reads sites() on every 5 s tick. A plain SELECT DISTINCT
    over a low-cardinality column is a full table scan (883 ms measured on a
    six-store HQ at 1.5M rows); the loose index scan is O(sites x log N)."""
    db = Database(tmp_path / "d.db")
    _seed(db, "LOCAL", site="")
    _seed(db, "ATL", site="atlanta")
    _seed(db, "MAR", site="marietta")
    assert db.sites() == ["atlanta", "marietta"]

    conn = db._conn()
    assert "idx_readings_site" in [r[1] for r in conn.execute("PRAGMA index_list(readings)")]
    plan = " ".join(str(r[-1]) for r in conn.execute(
        "EXPLAIN QUERY PLAN "
        "WITH RECURSIVE t(s) AS (SELECT MIN(site) FROM readings WHERE site != ''"
        " UNION ALL SELECT (SELECT MIN(site) FROM readings WHERE site > t.s AND site != '')"
        " FROM t WHERE t.s IS NOT NULL) SELECT s FROM t WHERE s IS NOT NULL ORDER BY s"))
    assert "idx_readings_site" in plan, plan
    assert "SCAN readings" not in plan, f"fell back to a table scan: {plan}"


def test_partial_index_costs_a_single_site_hub_nothing(tmp_path):
    """`WHERE site != ''` makes the index empty on a hub nobody forwards to —
    which is every hub until a chain runs one."""
    db = Database(tmp_path / "d.db")
    _seed(db, "LOCAL", site="", n=200)
    indexed = db._conn().execute(
        "SELECT COUNT(*) FROM readings WHERE site != ''").fetchone()[0]
    assert indexed == 0
    assert db.sites() == []


def test_two_stores_may_name_a_probe_the_same_thing(tmp_path):
    """The dedup key must include the site.

    Probe ids are operator-visible strings, not just MAC-derived ones — two
    managers both calling their cooler "walkin" is the expected case, not a
    pathological one. With UNIQUE(probe_id, epoch), head office's
    INSERT OR IGNORE silently discarded the second store's reading: a hole in a
    food-safety record caused by nothing worse than two people picking the same
    obvious name, and invisible from either end.
    """
    db = Database(tmp_path / "hq.db")
    ts = "2026-08-04T10:00:00.000"
    db.append(ts, 3.5, 38.3, "walkin", site="atlanta")
    db.append(ts, -18.9, -2.0, "walkin", site="marietta")
    db.append(ts, 21.0, 69.8, "walkin", site="")        # HQ's own, same name again

    assert db.window_stats(site="atlanta")["count"] == 1
    assert db.window_stats(site="marietta")["count"] == 1
    assert db.window_stats(site="")["count"] == 1
    assert db.count() == 3


def test_replay_from_one_store_is_still_idempotent(tmp_path):
    """Widening the key must not cost the property the forwarder depends on:
    re-sending a batch after a dropped response cannot duplicate rows."""
    db = Database(tmp_path / "hq.db")
    ts = "2026-08-04T10:00:00.000"
    for _ in range(5):
        db.append(ts, 3.5, 38.3, "walkin", site="atlanta")
    assert db.count() == 1


def test_per_probe_seek_still_uses_the_index(tmp_path):
    """site is the THIRD column precisely so (probe_id, epoch) stays a usable
    prefix — latest_per_probe's per-probe seek must not fall back to a scan."""
    db = Database(tmp_path / "hq.db")
    db.append("2026-08-04T10:00:00.000", 3.5, 38.3, "walkin", site="atlanta")
    plan = " ".join(str(r[-1]) for r in db._conn().execute(
        "EXPLAIN QUERY PLAN SELECT ts FROM readings WHERE probe_id=? "
        "ORDER BY epoch DESC, id DESC LIMIT 1", ("walkin",)))
    assert "idx_readings_probe_epoch_site_uniq" in plan, plan
    assert "SCAN readings" not in plan, plan

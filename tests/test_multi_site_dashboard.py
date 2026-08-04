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


def test_recent_events_narrow_to_the_selected_site(tmp_path):
    """The events log has no site column — membership is inferred from which
    probes report under that site."""
    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    _seed(db, "ATL-Walkin", site="atlanta")
    _seed(db, "SAV-Freezer", site="savannah")
    db.record_event("high", "ATL-Walkin", 9.1, 8.0)
    db.record_event("offline", "SAV-Freezer")

    everything = str(build_events(db, cfg, "celsius", site="all"))
    assert "ATL-Walkin" in everything and "SAV-Freezer" in everything

    atl = str(build_events(db, cfg, "celsius", site="atlanta"))
    assert "ATL-Walkin" in atl
    assert "SAV-Freezer" not in atl


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

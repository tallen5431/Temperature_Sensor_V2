"""Tests for live hub-status derivation (core.status.hub_status) and the
footer text/colour mapping (components.layout_main.footer_status_display)."""
import time

from core.status import REPORTING_LOOKBACK_SEC, hub_status, reporting_probe_ids
from components.layout_main import footer_status_display


def _probe(last_seen):
    return {"name": "p", "ip": "10.0.0.2", "last_seen": last_seen}


def test_waiting_when_nothing_ever_seen():
    s = hub_status([], online_timeout=60, total_readings=0, now=1000)
    assert s["state"] == "waiting"
    text, css = footer_status_display(s)
    assert "Waiting" in text and "muted" in css


def test_idle_when_readings_exist_but_no_probe():
    s = hub_status([], online_timeout=60, total_readings=500, now=1000)
    assert s["state"] == "idle"
    text, _ = footer_status_display(s)
    assert "Idle" in text


def test_online_counts_fresh_probes():
    probes = [_probe(990), _probe(995), _probe(100)]  # third is stale
    s = hub_status(probes, online_timeout=60, total_readings=10, now=1000)
    assert s["state"] == "online"
    assert s["online"] == 2 and s["total"] == 3
    text, css = footer_status_display(s)
    assert "2 probes online" in text and "success" in css


def test_offline_when_all_probes_stale():
    probes = [_probe(100), _probe(200)]
    s = hub_status(probes, online_timeout=60, total_readings=10, now=1000)
    assert s["state"] == "offline"
    text, css = footer_status_display(s)
    assert "2 probes offline" in text and "warning" in css


def test_singular_pluralisation():
    s = hub_status([_probe(995)], online_timeout=60, total_readings=10, now=1000)
    text, _ = footer_status_display(s)
    assert "1 probe online" in text   # no trailing "s"


def test_reporting_online_counts_db_probes_without_mdns():
    # A probe posting to the DB but not mDNS-visible (deep sleep / demo data)
    # still reads as online, so the footer agrees with the dashboard's
    # "Connected Probes" instead of showing "idle".
    s = hub_status([], online_timeout=60, total_readings=500, now=1000, reporting_online=2)
    assert s["state"] == "online" and s["online"] == 2 and s["total"] == 2
    text, css = footer_status_display(s)
    assert "2 probes online" in text and "success" in css


def test_reporting_online_takes_the_max_of_both_sources():
    # mDNS sees 1 fresh probe; the DB reports 3 fresh — take the larger.
    s = hub_status([_probe(995)], online_timeout=60, total_readings=10, now=1000,
                   reporting_online=3)
    assert s["state"] == "online" and s["online"] == 3 and s["total"] == 3


def test_handles_object_style_probes():
    class P:
        def __init__(self, ls):
            self.last_seen = ls
    s = hub_status([P(990)], online_timeout=60, total_readings=1, now=1000)
    assert s["state"] == "online" and s["online"] == 1


def test_reporting_probe_ids_bounds_the_probe_scan():
    # The per-probe GROUP BY behind reporting_probe_ids is bounded to a 7-day
    # window: probes silent longer than any possible fresh window can't affect
    # the answer, and the query cost must track recent rows, not all history.
    class _Db:
        def __init__(self, now):
            self.window = "unset"
            self._now = now

        def last_reading_epoch_per_probe(self, window_seconds=None):
            self.window = window_seconds
            return {"fresh": self._now - 10, "stale": self._now - 86400}

    now = time.time()
    db = _Db(now)
    out = reporting_probe_ids({}, db, now=now)
    assert db.window == REPORTING_LOOKBACK_SEC == 7 * 86400
    # fresh probe within its window is reporting; a day-silent probe is not
    assert out == {"fresh"}

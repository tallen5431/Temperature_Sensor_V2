"""The /metrics latest-reading registry must be bounded.

A probe id arrives as an X-Probe-ID header on the open-by-default ingest API and
sanitizes to 32 chars of ``[A-Za-z0-9_-]``, so its cardinality is effectively
unlimited -- the exposure ``probe_discovery._MAX_PROBES`` and
``mqtt_publish._MAX_ANNOUNCED`` already bound. Here every distinct id added both
a permanent dict entry AND a permanent series to the scrape body, so the leak
doubled as scrape amplification: 20k ids produced a 2.9 MB /metrics response,
pulled by Prometheus every 15-30 s.

Eviction, not refusal, is the right policy here -- the opposite of the MQTT
announce cap. This map is "current temperature per probe", so a real sensor
reporting for the first time must be able to displace the stalest entry rather
than be locked out because noise arrived first.
"""
import time

from core.metrics import LatestReadings, render_prometheus, _MAX_TRACKED

_HEALTH = {"rows_written": 0, "ingest_rejected": 0,
           "write_failures": 0, "healthy": True}


def _flood(lr, n, base_ts=1000.0):
    for i in range(n):
        lr.record(f"Spoofed-{i:08d}", 21.0, ts_epoch=base_ts + i)


def test_registry_is_capped():
    lr = LatestReadings()
    _flood(lr, _MAX_TRACKED + 2000)
    assert len(lr.snapshot()) == _MAX_TRACKED


def test_scrape_body_stays_bounded():
    lr = LatestReadings()
    _flood(lr, 20000)
    body = render_prometheus(_HEALTH, lr.snapshot(), len(lr.snapshot()), "test")
    assert len(body) < 200_000        # was ~2.9 MB before the cap


def test_a_real_probe_can_still_register_after_a_flood():
    """Refusing instead of evicting would lock a genuine sensor out forever."""
    lr = LatestReadings()
    _flood(lr, _MAX_TRACKED + 500)
    lr.record("Setpoint-REAL", 4.0, ts_epoch=time.time())
    assert "Setpoint-REAL" in lr.snapshot()


def test_eviction_drops_the_stalest_entry_first():
    lr = LatestReadings()
    lr.record("OLDEST", 1.0, ts_epoch=1.0)
    for i in range(_MAX_TRACKED):
        lr.record(f"P{i}", 2.0, ts_epoch=1000.0 + i)
    assert "OLDEST" not in lr.snapshot()


def test_a_normal_fleet_is_untouched_by_repeated_readings():
    lr = LatestReadings()
    for round_ in range(50):
        for pid in ("A", "B", "C"):
            lr.record(pid, 20.0 + round_)
    assert sorted(lr.snapshot()) == ["A", "B", "C"]


def test_updating_an_existing_probe_never_evicts():
    lr = LatestReadings()
    for i in range(_MAX_TRACKED):
        lr.record(f"P{i}", 1.0, ts_epoch=1000.0 + i)
    before = set(lr.snapshot())
    lr.record("P0", 99.0, ts_epoch=9999.0)      # already present -> no eviction
    assert set(lr.snapshot()) == before
    assert lr.snapshot()["P0"]["temp_c"] == 99.0

from conftest import make_client
from core.metrics import LatestReadings, render_prometheus, LATEST


def test_latest_readings_record_and_snapshot():
    lr = LatestReadings()
    lr.record("Setpoint-1", 21.5, ts_epoch=1000.0)
    snap = lr.snapshot()
    assert snap["Setpoint-1"]["temp_c"] == 21.5
    lr.record("", 5)  # empty id ignored
    assert "" not in lr.snapshot()


def test_latest_readings_evict_and_clear():
    lr = LatestReadings()
    lr.record("A", 1.0)
    lr.record("B", 2.0)
    lr.evict("A")
    assert "A" not in lr.snapshot() and "B" in lr.snapshot()
    lr.evict("")  # empty id is a harmless no-op
    lr.clear()
    assert lr.snapshot() == {}


def test_render_prometheus_probes_online_gauge():
    health = {"rows_written": 0, "healthy": True}
    out = render_prometheus(health, {}, probes_count=3, version="2.0.0", probes_online=2)
    assert "# TYPE setpoint_probes_online gauge" in out
    assert "setpoint_probes_online 2" in out
    # Backwards compatible: omitted entirely when the count isn't supplied.
    out2 = render_prometheus(health, {}, probes_count=3, version="2.0.0")
    assert "setpoint_probes_online" not in out2


def test_render_prometheus_format():
    health = {"rows_written": 3, "ingest_rejected": 1, "write_failures": 0, "healthy": True}
    latest = {"Setpoint-9A3F2C": {"temp_c": 4.25, "ts": 1000.0}}
    out = render_prometheus(health, latest, probes_count=2, version="2.0.0")
    assert "# TYPE setpoint_probe_temperature_celsius gauge" in out
    assert 'setpoint_probe_temperature_celsius{probe_id="Setpoint-9A3F2C"} 4.250' in out
    assert "setpoint_rows_written_total 3" in out
    assert "setpoint_healthy 1" in out
    assert 'setpoint_up{version="2.0.0"} 1' in out
    # Every non-comment line must be "name value" (well-formed exposition).
    for line in out.splitlines():
        if line and not line.startswith("#"):
            assert len(line.rsplit(" ", 1)) == 2


def test_render_prometheus_includes_humidity_and_vpd():
    health = {"rows_written": 1, "healthy": True}
    latest = {"P1": {"temp_c": 25.0, "ts": 1000.0, "humidity": 55.0, "vpd": 1.4}}
    out = render_prometheus(health, latest, probes_count=1, version="2.0.0")
    assert 'setpoint_probe_humidity_percent{probe_id="P1"} 55.00' in out
    assert 'setpoint_probe_vpd_kpa{probe_id="P1"} 1.400' in out
    # Temperature-only probes must NOT emit humidity/vpd lines.
    out2 = render_prometheus(health, {"P2": {"temp_c": 4.0, "ts": 1000.0}}, 1, "2.0.0")
    assert "setpoint_probe_humidity_percent" not in out2


def test_ingest_records_latest_reading(tmp_db):
    client, _ = make_client(tmp_db, token="")
    client.post("/api/ingest", json={"temperature_c": 7.7, "probe_id": "Setpoint-METRIC"})
    assert LATEST.snapshot().get("Setpoint-METRIC", {}).get("temp_c") == 7.7


def test_ingest_records_humidity_and_vpd(tmp_db):
    client, _ = make_client(tmp_db, token="")
    client.post("/api/ingest", json={"temperature_c": 25, "humidity_pct": 50, "probe_id": "Setpoint-HUM"})
    entry = LATEST.snapshot().get("Setpoint-HUM", {})
    assert entry.get("humidity") == 50.0
    assert entry.get("vpd", 0) > 1.0

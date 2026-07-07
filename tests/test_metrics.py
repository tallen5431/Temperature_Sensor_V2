from conftest import make_client
from core.metrics import LatestReadings, render_prometheus, LATEST


def test_latest_readings_record_and_snapshot():
    lr = LatestReadings()
    lr.record("ThermaProbe-1", 21.5, ts_epoch=1000.0)
    snap = lr.snapshot()
    assert snap["ThermaProbe-1"]["temp_c"] == 21.5
    lr.record("", 5)  # empty id ignored
    assert "" not in lr.snapshot()


def test_render_prometheus_format():
    health = {"rows_written": 3, "ingest_rejected": 1, "write_failures": 0, "healthy": True}
    latest = {"ThermaProbe-9A3F2C": {"temp_c": 4.25, "ts": 1000.0}}
    out = render_prometheus(health, latest, probes_count=2, version="2.0.0")
    assert "# TYPE thermahub_probe_temperature_celsius gauge" in out
    assert 'thermahub_probe_temperature_celsius{probe_id="ThermaProbe-9A3F2C"} 4.250' in out
    assert "thermahub_rows_written_total 3" in out
    assert "thermahub_healthy 1" in out
    assert 'thermahub_up{version="2.0.0"} 1' in out
    # Every non-comment line must be "name value" (well-formed exposition).
    for line in out.splitlines():
        if line and not line.startswith("#"):
            assert len(line.rsplit(" ", 1)) == 2


def test_render_prometheus_includes_humidity_and_vpd():
    health = {"rows_written": 1, "healthy": True}
    latest = {"P1": {"temp_c": 25.0, "ts": 1000.0, "humidity": 55.0, "vpd": 1.4}}
    out = render_prometheus(health, latest, probes_count=1, version="2.0.0")
    assert 'thermahub_probe_humidity_percent{probe_id="P1"} 55.00' in out
    assert 'thermahub_probe_vpd_kpa{probe_id="P1"} 1.400' in out
    # Temperature-only probes must NOT emit humidity/vpd lines.
    out2 = render_prometheus(health, {"P2": {"temp_c": 4.0, "ts": 1000.0}}, 1, "2.0.0")
    assert "thermahub_probe_humidity_percent" not in out2


def test_ingest_records_latest_reading(tmp_csv):
    client, _ = make_client(tmp_csv, token="")
    client.post("/api/ingest", json={"temperature_c": 7.7, "probe_id": "ThermaProbe-METRIC"})
    assert LATEST.snapshot().get("ThermaProbe-METRIC", {}).get("temp_c") == 7.7


def test_ingest_records_humidity_and_vpd(tmp_csv):
    client, _ = make_client(tmp_csv, token="")
    client.post("/api/ingest", json={"temperature_c": 25, "humidity_pct": 50, "probe_id": "ThermaProbe-HUM"})
    entry = LATEST.snapshot().get("ThermaProbe-HUM", {})
    assert entry.get("humidity") == 50.0
    assert entry.get("vpd", 0) > 1.0

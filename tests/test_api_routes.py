import csv

from conftest import make_client, FakeDiscovery
from core.storage import COLUMNS

PID_COL = COLUMNS.index("probe_id")


def _rows(csv_path):
    with open(csv_path, newline="") as f:
        return list(csv.reader(f))


def test_ingest_open_writes_row(tmp_csv):
    client, disc = make_client(tmp_csv, token="")
    r = client.post("/api/ingest", json={"temperature_c": 21.5, "probe_id": "ThermaProbe-1"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    rows = _rows(tmp_csv)
    assert len(rows) == 2  # header + one reading
    assert rows[1][PID_COL] == "ThermaProbe-1"


def test_ingest_with_humidity_logs_vpd(tmp_csv):
    client, _ = make_client(tmp_csv, token="")
    r = client.post("/api/ingest", json={"temperature_c": 25, "humidity_pct": 50, "probe_id": "P1"})
    assert r.status_code == 200
    rows = _rows(tmp_csv)
    hum = rows[1][COLUMNS.index("humidity_pct")]
    vpd = rows[1][COLUMNS.index("vpd_kpa")]
    assert hum == "50.00"
    assert float(vpd) > 1.0  # VPD computed and logged


def test_ingest_registers_posting_only_probe(tmp_csv):
    # A probe that posts but was never seen over mDNS must still show up — the
    # old code mutated a throwaway dict copy, so it never appeared.
    client, disc = make_client(tmp_csv, token="")
    client.post("/api/ingest", json={"temperature_c": 20, "probe_id": "ThermaProbe-XYZ"})
    assert "ThermaProbe-XYZ" in disc.list_probes()


def test_auth_required_when_token_set(tmp_csv):
    client, _ = make_client(tmp_csv, token="secret")
    # No token → 401
    assert client.post("/api/ingest", json={"temperature_c": 20}).status_code == 401
    # Header token → 200
    assert client.post("/api/ingest", json={"temperature_c": 20},
                       headers={"X-Token": "secret"}).status_code == 200
    # Query token → 200
    assert client.post("/api/ingest?token=secret", json={"temperature_c": 20}).status_code == 200
    # Body token → 200
    assert client.post("/api/ingest", json={"temperature_c": 20, "token": "secret"}).status_code == 200


def test_ingest_get_is_removed(tmp_csv):
    client, _ = make_client(tmp_csv, token="")
    # GET used to mutate the CSV (drive-by CSRF). Now 405 and writes nothing.
    r = client.get("/api/ingest?temperature_c=99")
    assert r.status_code == 405
    assert len(_rows(tmp_csv)) == 1  # header only


def test_malformed_temp_returns_400(tmp_csv):
    client, _ = make_client(tmp_csv, token="")
    assert client.post("/api/ingest", json={"humidity": 5}).status_code == 400
    assert client.post("/api/ingest", json={"temperature_c": "NaN"}).status_code == 400
    assert client.post("/api/ingest", json={"temperature_c": 9999}).status_code == 400


def test_health_reports_version(tmp_csv):
    client, _ = make_client(tmp_csv, token="")
    body = client.get("/api/health").get_json()
    assert body["ok"] is True
    assert "version" in body and "protocol" in body


def test_config_get_requires_auth_and_redacts(tmp_csv, config):
    config.set("provision_token", "supersecret")
    client, _ = make_client(tmp_csv, token="tok", cfg=config)
    assert client.get("/api/config").status_code == 401
    body = client.get("/api/config", headers={"X-Token": "tok"}).get_json()
    # Secret must never be serialized verbatim.
    assert body["provision_token"] != "supersecret"


def test_provision_requires_auth(tmp_csv):
    client, _ = make_client(tmp_csv, token="tok")
    assert client.post("/api/provision", json={"host": "1.2.3.4"}).status_code == 401

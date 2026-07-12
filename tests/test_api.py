"""Integration tests for the REST API blueprint (api.routes)."""
import time

import pytest
from flask import Flask

from api.routes import create_api
from core.config import Config
from core.db import Database


class FakeDiscovery:
    """Minimal stand-in for ProbeDiscovery (no Zeroconf/network)."""
    def __init__(self):
        self.seen = {}

    def list_probes(self):
        return self.seen

    def update_last_seen(self, probe_id, host="", ip=""):
        self.seen[probe_id] = {"name": probe_id, "host": host, "ip": ip,
                               "port": 80, "properties": {"id": probe_id},
                               "last_seen": time.time()}


def _make_client(tmp_path, token=""):
    db = Database(tmp_path / "api.db")
    cfg = Config(tmp_path / "config.json")
    cfg.update({"provision_token": "supersecret"})
    disc = FakeDiscovery()
    app = Flask(__name__)
    app.register_blueprint(create_api(cfg, db, disc, lambda: "http://hub:8088", token))
    return app.test_client(), db, disc


def test_ingest_post_stores_reading(tmp_path):
    client, db, disc = _make_client(tmp_path)
    r = client.post("/api/ingest", json={"temperature_c": 21.5, "probe_id": "p1"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert db.count() == 1
    assert db.latest()["temperature_c"] == 21.5
    assert "p1" in disc.seen  # discovery last_seen updated


def test_ingest_get_is_rejected_405(tmp_path):
    # Ingest is POST-only (PROTOCOL.md §6): a mutating GET is a CSRF/poisoning
    # vector and must not write, so a drive-by <img> can't inject readings.
    client, db, _ = _make_client(tmp_path)
    r = client.get("/api/ingest?temperature_c=19.0&probe_id=p2")
    assert r.status_code == 405
    assert db.count() == 0


def test_ingest_rejects_non_finite_and_out_of_range(tmp_path):
    # NaN/inf and sensor fault codes must be rejected with 400, not stored
    # (a stored inf would poison stats/exports; -127 would fire a false alert).
    client, db, _ = _make_client(tmp_path)
    for bad in ("NaN", "inf", "1e999", "-127", "200", "-100"):
        r = client.post("/api/ingest", json={"temperature_c": bad, "probe_id": "p1"})
        assert r.status_code == 400, bad
    assert db.count() == 0
    # A value inside the -60..150 band still stores.
    assert client.post("/api/ingest",
                       json={"temperature_c": 84.9, "probe_id": "p1"}).status_code == 200
    assert db.count() == 1


def test_ingest_missing_temperature_is_400(tmp_path):
    client, db, _ = _make_client(tmp_path)
    r = client.post("/api/ingest", json={"probe_id": "p1"})
    assert r.status_code == 400
    assert db.count() == 0


def test_config_get_redacts_secret(tmp_path):
    client, _, _ = _make_client(tmp_path)
    body = client.get("/api/config").get_json()
    # The real secret value must never be exposed.
    assert body["provision_token"] != "supersecret"
    assert body["provision_token"] == "***set***"


def test_health_reports_counts(tmp_path):
    client, db, _ = _make_client(tmp_path)
    client.post("/api/ingest", json={"temperature_c": 20, "probe_id": "p1"})
    body = client.get("/api/health").get_json()
    assert body["ok"] is True
    assert body["readings"] == 1
    assert body["probes"] >= 1
    assert body["probes_online"] >= 1


def test_diagnostics_endpoint(tmp_path):
    client, db, _ = _make_client(tmp_path)
    client.post("/api/ingest", json={"temperature_c": 20, "probe_id": "p1"})
    body = client.get("/api/diagnostics").get_json()
    assert body["database"]["readings"] == 1
    assert body["probes"]["total"] >= 1
    assert "version" in body
    # the configured secret must not leak into diagnostics
    assert "supersecret" not in str(body)


def test_probes_listing_has_online_flag(tmp_path):
    client, _, _ = _make_client(tmp_path)
    client.post("/api/ingest", json={"temperature_c": 20, "probe_id": "p1"})
    probes = client.get("/api/probes").get_json()
    assert any(p["probe_id"] == "p1" and p["online"] is True for p in probes)


def test_calibration_offset_applied_at_ingest(tmp_path):
    client, db, _ = _make_client(tmp_path)
    # Probe p1 reads 1.5 C too high -> offset corrects it down (set via the API).
    client.post("/api/config", json={"calibration_offsets": {"p1": -1.5}})

    client.post("/api/ingest", json={"temperature_c": 20.0, "probe_id": "p1"})
    latest = db.latest()
    assert latest["temperature_c"] == 18.5            # 20.0 - 1.5
    assert abs(latest["temperature_f"] - 65.3) < 0.05  # recomputed from corrected C
    # A probe without an offset is stored unchanged.
    client.post("/api/ingest", json={"temperature_c": 20.0, "probe_id": "p2"})
    assert db.latest()["temperature_c"] == 20.0


def test_auth_required_when_token_set(tmp_path):
    client, db, _ = _make_client(tmp_path, token="abc123")
    # No token -> rejected
    assert client.post("/api/ingest", json={"temperature_c": 20}).status_code == 401
    assert db.count() == 0
    # Correct token in header -> accepted
    ok = client.post("/api/ingest", json={"temperature_c": 20},
                     headers={"X-Token": "abc123"})
    assert ok.status_code == 200
    assert db.count() == 1
    # Wrong token -> rejected
    assert client.post("/api/ingest", json={"temperature_c": 20},
                       headers={"X-Token": "nope"}).status_code == 401

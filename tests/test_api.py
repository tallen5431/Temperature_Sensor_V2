"""Integration tests for the REST API blueprint (api.routes)."""
import time

import pytest
from flask import Flask

from api.routes import _is_safe_provision_target, create_api
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


def test_non_object_json_body_is_4xx_not_500(tmp_path):
    # Regression: a top-level JSON array/number/string reached `data.get(...)`
    # before any dict guard and raised AttributeError -> HTTP 500. It must now be
    # a clean 4xx from the normal validation path.
    client, db, _ = _make_client(tmp_path)
    for body in ([1, 2, 3], 5, "hello"):
        assert client.post("/api/ingest", json=body).status_code == 400, body   # no temperature
        assert client.post("/api/provision", json=body).status_code != 500, body
    assert db.count() == 0


def test_auth_survives_non_object_json_body(tmp_path):
    # The token check reads a JSON body for a `token` field; a non-object body
    # (no X-Token header) must fail auth with 401, not 500.
    client, _, _ = _make_client(tmp_path, token="sekret")
    assert client.post("/api/ingest", json=[1, 2, 3]).status_code == 401


def test_health_stays_200_when_db_read_fails(tmp_path):
    # /api/health is what monitors poll to detect trouble, so a momentarily
    # locked/unreadable DB must degrade (readings=None) rather than 500.
    client, db, _ = _make_client(tmp_path)

    def boom():
        raise RuntimeError("database is locked")

    db.count = boom
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True and body["readings"] is None


def test_ingest_battery_pct_rides_along(tmp_path):
    # battery_pct rides along the ingest payload into the nullable battery_pct
    # column. Extraction lives in core.storage.extract_battery; on a build where
    # that helper has not landed yet the reading still stores, just with a NULL
    # battery — tolerate both so a partial upgrade never fails ingest.
    import core.storage as storage
    client, db, _ = _make_client(tmp_path)
    r = client.post("/api/ingest", json={"temperature_c": 21.0, "probe_id": "p1",
                                         "battery_pct": 87})
    assert r.status_code == 200
    assert db.count() == 1
    stored = db.latest_per_probe().iloc[0]["battery_pct"]
    if hasattr(storage, "extract_battery"):
        assert float(stored) == 87.0
    else:
        assert stored is None


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


def test_redact_masks_nested_and_apikey_secrets():
    from api.routes import _redact
    out = _redact({
        "api_key": "sk-live-123",                 # credential-shaped key
        "creds": {"password": "p"},               # nested secret leaf
        "secret_bundle": {"a": "x", "b": "y"},    # secret-NAMED container
        "mqtt": {"host": "localhost", "password": "z"},  # keep host, mask password
    })
    assert out["api_key"] == "***set***"
    assert out["creds"]["password"] == "***set***"
    # A secret-named container is masked whole, not recursed into (no leaf leaks).
    assert out["secret_bundle"] == "***set***"
    assert out["mqtt"]["host"] == "localhost"
    assert out["mqtt"]["password"] == "***set***"


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


def test_ingest_batch_csv_stores_all(tmp_path):
    # The probe drains its on-flash buffer as one CSV chunk (ts,tC,tF,pid per
    # line) in a single round-trip instead of one POST per reading.
    client, db, disc = _make_client(tmp_path)
    csv = ("2026-07-24T10:00:00,4.0,39.2,p1\n"
           "2026-07-24T10:00:05,4.1,39.4,p1\n"
           "2026-07-24T10:00:10,4.2,39.6,p1\n")
    r = client.post("/api/ingest_csv", data=csv, content_type="text/csv")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True and body["accepted"] == 3 and body["rejected"] == 0
    assert db.count() == 3
    assert db.latest()["temperature_c"] == 4.2     # newest reading wins
    assert "p1" in disc.seen                        # probe marked seen once


def test_ingest_batch_replay_is_idempotent(tmp_path):
    # A dropped ACK on a bulk flush makes the probe re-POST the identical chunk.
    # The hub must dedupe by (probe_id, timestamp) so the replay can't inflate
    # the log with up to a whole chunk of duplicate rows.
    client, db, _ = _make_client(tmp_path)
    csv = ("2026-07-24T10:00:00,4.0,39.2,p1\n"
           "2026-07-24T10:00:05,4.1,39.4,p1\n"
           "2026-07-24T10:00:10,4.2,39.6,p1\n")
    first = client.post("/api/ingest_csv", data=csv, content_type="text/csv").get_json()
    assert first["accepted"] == 3 and db.count() == 3
    # Re-send the exact same chunk (the lost-ACK case).
    second = client.post("/api/ingest_csv", data=csv, content_type="text/csv").get_json()
    assert second["ok"] is True
    assert second["accepted"] == 0        # nothing new stored — all deduped
    assert db.count() == 3                # still three rows, no duplicates


def test_ingest_single_replay_is_idempotent(tmp_path):
    # The same guarantee protects the single-reading path: a re-sent POST with an
    # explicit timestamp does not create a duplicate row.
    client, db, _ = _make_client(tmp_path)
    payload = {"timestamp": "2026-07-24T10:00:00", "temperature_c": 4.0, "probe_id": "p1"}
    assert client.post("/api/ingest", json=payload).status_code == 200
    assert client.post("/api/ingest", json=payload).status_code == 200
    assert db.count() == 1


def test_ingest_batch_without_timestamps_keeps_all_rows(tmp_path):
    # Timestamp-less bulk rows must be receipt-stamped 1 ms apart, not collapsed
    # onto one epoch and silently dropped by the UNIQUE(probe_id, epoch) index.
    client, db, _ = _make_client(tmp_path)
    r = client.post("/api/ingest_csv", json={"readings": [
        {"temperature_c": 4.0, "probe_id": "p1"},
        {"temperature_c": 4.1, "probe_id": "p1"},
        {"temperature_c": 4.2, "probe_id": "p1"},
    ]})
    assert r.status_code == 200
    body = r.get_json()
    assert body["accepted"] == 3 and body["rejected"] == 0
    assert db.count() == 3          # all three kept, none collapsed away


def test_ingest_batch_json_array(tmp_path):
    client, db, _ = _make_client(tmp_path)
    r = client.post("/api/ingest_csv", json={"readings": [
        {"timestamp": "2026-07-24T10:00:00", "temperature_c": 5.0, "probe_id": "p2"},
        {"timestamp": "2026-07-24T10:00:05", "temperature_c": 5.5, "probe_id": "p2"},
    ]})
    assert r.status_code == 200 and r.get_json()["accepted"] == 2
    assert db.count() == 2


def test_ingest_batch_rejects_bad_rows_keeps_good(tmp_path):
    # A -127 fault code and an out-of-range value are rejected; the valid rows in
    # the same chunk still store — one corrupt line can't poison the whole backlog.
    client, db, _ = _make_client(tmp_path)
    csv = ("2026-07-24T10:00:00,4.0,39.2,p1\n"
           "2026-07-24T10:00:05,-127.0,-196.6,p1\n"
           "2026-07-24T10:00:10,999,1830,p1\n"
           "2026-07-24T10:00:15,4.3,39.7,p1\n")
    body = client.post("/api/ingest_csv", data=csv,
                       content_type="text/csv").get_json()
    assert body["accepted"] == 2 and body["rejected"] == 2
    assert db.count() == 2


def test_ingest_batch_requires_auth_when_token_set(tmp_path):
    client, db, _ = _make_client(tmp_path, token="abc123")
    csv = "2026-07-24T10:00:00,4.0,39.2,p1\n"
    assert client.post("/api/ingest_csv", data=csv,
                       content_type="text/csv").status_code == 401
    assert db.count() == 0
    ok = client.post("/api/ingest_csv", data=csv, content_type="text/csv",
                     headers={"X-Token": "abc123"})
    assert ok.status_code == 200 and db.count() == 1


def test_config_get_requires_auth_when_token_set(tmp_path):
    # GET /api/config exposes SMTP/MQTT/threshold detail, so with a token set it
    # must be gated like the write path (not readable by any LAN device).
    client, _, _ = _make_client(tmp_path, token="abc123")
    assert client.get("/api/config").status_code == 401
    assert client.get("/api/config", headers={"X-Token": "abc123"}).status_code == 200


def test_provision_rejects_ssrf_targets(tmp_path):
    client, _, _ = _make_client(tmp_path)  # open (no token) — isolates the SSRF check
    for bad in ("127.0.0.1", "169.254.169.254"):  # loopback, cloud metadata
        r = client.post("/api/provision", json={"host": bad, "port": 80})
        assert r.status_code == 400, bad


def test_is_safe_provision_target():
    assert _is_safe_provision_target("192.168.1.50") is True
    assert _is_safe_provision_target("10.0.0.5") is True
    assert _is_safe_provision_target("127.0.0.1") is False      # loopback
    assert _is_safe_provision_target("169.254.169.254") is False  # metadata
    assert _is_safe_provision_target("8.8.8.8") is False        # public
    assert _is_safe_provision_target("") is False


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

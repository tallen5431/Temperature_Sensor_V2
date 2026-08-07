"""Integration tests for the REST API blueprint (api.routes)."""
import time

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
    # onto one epoch and silently dropped by the UNIQUE(probe_id, epoch, site) index.
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


def test_ingest_returns_desired_config_for_probe(tmp_path):
    # A deep-sleeping probe is almost never reachable for the hub's PUSH to
    # /provision (it serves HTTP ~3 s every Nth wake), so the ingest reply
    # carries the desired config for the probe to PULL. Without this, a settings
    # change made in the dashboard could never reach a long-interval probe.
    client, _, _ = _make_client(tmp_path)
    r = client.post("/api/ingest", json={"temperature_c": 4.0, "probe_id": "p1"})
    assert r.status_code == 200
    cfgblk = r.get_json()["config"]
    assert cfgblk["interval_ms"] == 5000          # global interval_sec default
    assert 9 <= cfgblk["resolution_bits"] <= 12


def test_ingest_config_honours_per_probe_override(tmp_path):
    # The per-probe override the Devices page writes must be what the probe is
    # told — and it must match what the auto-provisioner would have pushed.
    from provisioning import desired_probe_config
    client, _, _ = _make_client(tmp_path)
    from core.config import Config
    cfg = Config(tmp_path / "config.json")
    cfg.update({"probe_intervals": {"p1": 900}, "probe_resolutions": {"p1": 9}})

    client2, _, _ = _make_client(tmp_path)   # rebuilt against the updated config
    r = client2.post("/api/ingest", json={"temperature_c": 4.0, "probe_id": "p1"})
    got = r.get_json()["config"]
    assert got == desired_probe_config(cfg, "p1")      # push and pull agree
    assert got["interval_ms"] == 900000 and got["resolution_bits"] == 9


def test_bulk_drain_future_stamps_are_restamped_not_collapsed(tmp_path):
    # Data-loss regression: a probe whose clock ran ahead during the outage that
    # filled its buffer drains rows stamped in the future. normalize_payload
    # clamped each row to its own "now", so a 100-row chunk collapsed onto ~1 ms
    # and UNIQUE(probe_id, epoch, site) silently dropped almost all of it — while the
    # hub still answered 200, so the probe advanced its checkpoint and deleted
    # the buffer. Such rows are now receipt-stamped 1 ms apart like
    # timestamp-less rows, and the count is reported.
    import datetime
    client, db, _ = _make_client(tmp_path)
    base = datetime.datetime.now() + datetime.timedelta(minutes=11)
    csv = "\n".join(
        f"{(base + datetime.timedelta(seconds=i)).isoformat(timespec='milliseconds')},"
        f"{20 + i * 0.01:.2f},68.0,P1" for i in range(100))
    r = client.post("/api/ingest_csv", data=csv, headers={"Content-Type": "text/csv"})
    body = r.get_json()
    assert body["accepted"] == 100 and body["restamped"] == 100
    assert db.count() == 100

    # A normally-stamped chunk is untouched and still deduped on replay.
    past = datetime.datetime.now() - datetime.timedelta(hours=1)
    csv2 = "\n".join(
        f"{(past + datetime.timedelta(seconds=i)).isoformat(timespec='milliseconds')},"
        f"5.0,41.0,P2" for i in range(10))
    b2 = client.post("/api/ingest_csv", data=csv2,
                     headers={"Content-Type": "text/csv"}).get_json()
    assert b2["accepted"] == 10 and b2["restamped"] == 0
    b3 = client.post("/api/ingest_csv", data=csv2,
                     headers={"Content-Type": "text/csv"}).get_json()
    assert b3["accepted"] == 0            # replay still deduped, not re-stamped
    assert db.count() == 110


def test_ingest_body_host_cannot_poison_discovery(tmp_path):
    # SSRF: a body-supplied `host` became a discovery hostname, and the
    # auto-provisioner would then resolve it and POST the hub's device token
    # there. Only the transport peer address may be trusted.
    client, _, disc = _make_client(tmp_path)
    client.post("/api/ingest", json={"temperature_c": 20.0, "probe_id": "p1",
                                     "host": "evil.example.com"})
    assert "evil.example.com" not in str(disc.seen)


def test_ingest_config_omitted_when_auto_provision_disabled(tmp_path):
    # auto_provision=false means "the hub does not manage my probes". It gated
    # only the background pusher, so the ingest reply kept overwriting a
    # hand-configured probe with the hub's global interval, with no way to opt
    # out. An omitted `config` key is a no-op on the probe.
    from core.config import Config
    Config(tmp_path / "config.json").update({"auto_provision": False})
    client, _, _ = _make_client(tmp_path)
    body = client.post("/api/ingest",
                       json={"temperature_c": 4.0, "probe_id": "p1"}).get_json()
    assert body["ok"] is True and "config" not in body


def test_unauthorized_is_counted_and_visible(tmp_path):
    # A stale device token made a probe 401 on every wake, invisibly. The count
    # must surface so the cause is findable.
    client, _, _ = _make_client(tmp_path, token="right-token")
    before = client.get("/api/health").get_json().get("unauthorized", 0)
    for _ in range(3):
        client.post("/api/ingest", json={"temperature_c": 1.0, "probe_id": "p1"},
                    headers={"X-Token": "stale-token"})
    assert client.get("/api/health").get_json()["unauthorized"] == before + 3


def test_bulk_drain_preserves_humidity_vpd_and_battery(tmp_path):
    # A grow probe (SHT4x) draining a backlog used to come back temperature-only:
    # the bulk path never extracted humidity/VPD/battery even though the live path
    # does and PROTOCOL documents them, so an outage left a hole in exactly the
    # data that niche buys the product for.
    client, db, _ = _make_client(tmp_path)
    r = client.post("/api/ingest_csv", json={"readings": [
        {"timestamp": "2026-07-28T10:00:00.000", "temperature_c": 24.0,
         "humidity_pct": 55.0, "battery_pct": 80, "probe_id": "grow1"},
    ]})
    assert r.get_json()["accepted"] == 1
    row = db.latest_per_probe().iloc[0]
    assert float(row["humidity_pct"]) == 55.0
    assert row["vpd_kpa"] is not None and float(row["vpd_kpa"]) > 0
    assert float(row["battery_pct"]) == 80.0


def test_ingest_config_uses_sanitized_probe_id(tmp_path):
    # The row is stored under the sanitized id and the Devices page writes
    # overrides under it, so looking the config up with the raw header would
    # silently miss a per-probe setting.
    from core.config import Config
    Config(tmp_path / "config.json").update({"probe_intervals": {"Setpoint-ABC123": 900}})
    client, _, _ = _make_client(tmp_path)
    body = client.post("/api/ingest", json={"temperature_c": 4.0},
                       headers={"X-Probe-ID": "Setpoint-ABC123!!"}).get_json()
    assert body["config"]["interval_ms"] == 900000


def test_bulk_drain_accepts_clockless_buffer_lines(tmp_path):
    # A probe whose NTP never synced (a LAN with no internet — the local-first
    # deployment this product is sold for) buffers readings with an EMPTY
    # timestamp field rather than dropping them. The hub must receipt-stamp
    # those rows 1 ms apart so every reading survives and stays ordered.
    client, db, _ = _make_client(tmp_path)
    csv = "\n".join(f",{20.0 + i:.3f},{68.0 + i:.3f},Setpoint-NOCLK" for i in range(5))
    body = client.post("/api/ingest_csv", data=csv,
                       headers={"Content-Type": "text/csv"}).get_json()
    assert body["accepted"] == 5 and body["rejected"] == 0
    rows = db.fetch_readings(probe_id="Setpoint-NOCLK")
    assert len(rows) == 5
    stamps = [r["timestamp"] for r in rows]
    assert stamps == sorted(stamps)          # distinct and in order
    assert len(set(stamps)) == 5             # not collapsed onto one instant


def test_dst_fallback_hour_keeps_both_readings(tmp_path, monkeypatch):
    # During the DST fall-back hour two UTC instants an hour apart map to the
    # SAME local wall time. Re-deriving the epoch from that local-naive string
    # gave them one epoch, so UNIQUE(probe_id, epoch, site) dropped one and everything
    # that sorts by epoch interleaved the whole repeated hour. The probe stamps
    # in UTC, so the unambiguous instant is carried through instead.
    import os, time as _time
    monkeypatch.setenv("TZ", "America/New_York")
    try:
        _time.tzset()
    except AttributeError:                      # non-POSIX; nothing to assert
        return
    client, db, _ = _make_client(tmp_path)
    for z, temp in (("2025-11-02T05:30:00.000Z", 4.0),      # 01:30 EDT
                    ("2025-11-02T06:30:00.000Z", 9.0)):     # 01:30 EST, 1 h later
        client.post("/api/ingest",
                    json={"temperature_c": temp, "probe_id": "P1", "timestamp": z})
    rows = db._conn().execute(
        "SELECT ts, epoch, temperature_c FROM readings ORDER BY epoch").fetchall()
    assert len(rows) == 2                                   # neither deduped away
    assert rows[0]["ts"] == rows[1]["ts"]                   # same wall clock, correctly
    assert abs(rows[1]["epoch"] - rows[0]["epoch"]) == 3600.0
    assert [r["temperature_c"] for r in rows] == [4.0, 9.0]  # true order preserved
    os.environ.pop("TZ", None)
    _time.tzset()


def test_bulk_rejects_truncated_line_under_mangled_probe_id(tmp_path):
    # A buffer line cut mid-write by a dying battery still splits into 4 fields —
    # the cut lands in the probe id — so it was stored as a real reading under a
    # phantom probe like "Setpo". A probe only drains its own buffer, so a row
    # disagreeing with X-Probe-ID is corrupt.
    client, db, _ = _make_client(tmp_path)
    csv = ("2026-07-30T12:00:00.000Z,20.5,68.9,Setpoint-000079\n"
           "2026-07-30T12:00:05.000Z,20.6,69.1,Setpo")
    body = client.post("/api/ingest_csv", data=csv,
                       headers={"Content-Type": "text/csv",
                                "X-Probe-ID": "Setpoint-000079"}).get_json()
    assert body["accepted"] == 1 and body["rejected"] == 1
    assert sorted({r["probe_id"] for r in db.fetch_readings()}) == ["Setpoint-000079"]


def test_the_bulk_drain_does_not_log_backfill_breaches_itself(tmp_path):
    """It used to, and the requirement it served is real — but it belongs to the
    alert monitor now, and leaving both in place double-logs.

    What this endpoint did was record the worst excursion PER BATCH. A probe
    drains a backlog in 100-row chunks, so a twelve-hour outage at a 7 s cadence
    is 62 chunks and one thawing freezer produced up to 62 event rows, each
    labelled "worst in this chunk". It also deliberately never notified, on the
    grounds that a backfilled breach is "old news" — a freezer that spent
    thirteen minutes above its limit last night is not old news — and it could
    not cover a probe reconnecting one reading at a time through /api/ingest.

    ``AlertMonitor._check_missed`` collapses a whole excursion to one event,
    notifies, and covers both ingest paths.
    ``tests/test_missed_excursions.py`` owns that behaviour; this only pins that
    the endpoint no longer does it too.
    """
    import datetime
    Config(tmp_path / "config.json").update(
        {"alert_thresholds": {"Freezer": {"min": -30.0, "max": -15.0}}})
    client, db, _disc = _make_client(tmp_path)
    base = datetime.datetime.now() - datetime.timedelta(hours=6)
    temps = [-22, -20, -12, -5, -9, -18, -21, -22]      # thaw, then recovery
    csv = "\n".join(
        f"{(base + datetime.timedelta(minutes=10 * i)).isoformat(timespec='milliseconds')},"
        f"{tc:.2f},{tc * 9 / 5 + 32:.2f},Freezer" for i, tc in enumerate(temps))
    resp = client.post("/api/ingest_csv", data=csv,
                       headers={"Content-Type": "text/csv", "X-Probe-ID": "Freezer"})
    assert resp.get_json()["accepted"] == len(temps), "the readings must still store"
    assert db.list_events(limit=10) == [], \
        "the endpoint must leave excursion reporting to the monitor"


def test_the_monitor_still_catches_what_the_bulk_drain_used_to(tmp_path):
    """The requirement the removed block existed for, asserted end to end through
    the real HTTP endpoint: an excursion whose newest row is back in spec is one
    the alert engine can never see, and something has to report it."""
    import datetime
    from alert_monitor import AlertMonitor

    client, db, _disc = _make_client(tmp_path)
    cfg = Config(tmp_path / "config.json")
    cfg.update({"alert_thresholds": {"Freezer": {"min": -30.0, "max": -15.0}},
                "notifications": {"enabled": False}})
    mon = AlertMonitor(db, cfg, notifier=None)
    mon.check_once()                       # seed the arrival watermark

    base = datetime.datetime.now() - datetime.timedelta(hours=6)
    temps = [-22, -20, -12, -5, -9, -18, -21, -22]      # thaw, then recovery
    csv = "\n".join(
        f"{(base + datetime.timedelta(minutes=10 * i)).isoformat(timespec='milliseconds')},"
        f"{tc:.2f},{tc * 9 / 5 + 32:.2f},Freezer" for i, tc in enumerate(temps))
    client.post("/api/ingest_csv", data=csv,
                headers={"Content-Type": "text/csv", "X-Probe-ID": "Freezer"})

    events = [e for e in mon.check_once() if e["kind"] == "missed"]
    assert len(events) == 1, "one excursion, one event"
    assert events[0]["temperature_c"] == -5.0, "and it carries the worst reading"
    assert events[0]["limit"] == -15.0


def test_ingest_without_a_probe_id_lands_where_the_operator_can_see_it(client):
    """The end-to-end half of the storage-level guard: a reading posted with no
    X-Probe-ID and no body probe_id used to be stored under "" and then hidden by
    every surface that renders probes, with the API still answering ok:true."""
    from core.storage import UNIDENTIFIED_PROBE_ID
    r = client.post("/api/ingest", json={"temperature_c": 4.2})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    listed = client.get("/api/probes").get_json()
    probes = listed if isinstance(listed, list) else listed.get("probes", [])
    ids = [p.get("probe_id") or p.get("name") for p in probes]
    assert UNIDENTIFIED_PROBE_ID in ids, (
        f"the reading was accepted but no probe appeared for it: {ids}")


def test_bulk_ingest_without_a_probe_id_lands_the_same_place(client):
    from core.storage import UNIDENTIFIED_PROBE_ID
    r = client.post("/api/ingest_csv",
                    json={"readings": [{"temperature_c": 6.0,
                                        "timestamp": "2026-08-05T10:00:00"},
                                       {"temperature_c": 6.5,
                                        "timestamp": "2026-08-05T10:01:00"}]})
    assert r.status_code == 200 and r.get_json()["accepted"] == 2
    rows = client.get("/api/readings").get_json()["readings"]
    assert {row["probe_id"] for row in rows} == {UNIDENTIFIED_PROBE_ID}


def test_a_batch_reports_the_rows_it_could_not_even_parse(client):
    """PROTOCOL.md §7 defines `rejected` as "rows the hub refused". Rows the
    parser dropped on the way in — a JSON element that is not an object, a CSV
    line truncated to fewer than four fields — were filtered out silently, so a
    chunk that was partly thrown away came back as `rejected: 0`. A probe
    draining a buffer its battery died mid-append was told every line was fine."""
    r = client.post("/api/ingest_csv", json={"readings": [
        {"temperature_c": 4.0, "timestamp": "2026-08-05T09:00:00"},
        "not a reading", 42, None,
    ]})
    body = r.get_json()
    assert body["accepted"] == 1
    assert body["rejected"] == 3, f"three junk elements went unreported: {body}"


def test_a_truncated_csv_line_is_reported_not_swallowed(client):
    body = ("2026-08-05T09:00:00,4.0,39.2,P1\n"
            "2026-08-05T09:01:00,4.1\n"            # truncated mid-write
            "\n"                                    # blank padding: not a row
            "2026-08-05T09:02:00,4.2,39.6,P1\n")
    r = client.post("/api/ingest_csv", data=body, content_type="text/csv")
    got = r.get_json()
    assert got["accepted"] == 2
    assert got["rejected"] == 1, f"the truncated line was swallowed: {got}"


def test_a_wholly_unusable_body_is_still_a_400(client):
    assert client.post("/api/ingest_csv", json={"readings": "nope"}).status_code == 400


# --- replay of a drained buffer chunk --------------------------------------
# A probe re-sends its last un-checkpointed chunk when the ACK is lost. Three
# places asserted that is always free; it is free only for rows that carry a
# timestamp. These pin BOTH halves so the promise and the behaviour cannot drift
# apart again — the firmware comment claiming "bufferAppend refuses an empty one"
# had been wrong ever since 2.8.2 deliberately started writing empty ones.

def _csv_post(client, body, probe_id):
    return client.post("/api/ingest_csv", data=body, content_type="text/csv",
                       headers={"X-Probe-ID": probe_id}).get_json()


def test_replaying_a_stamped_chunk_stores_nothing_extra(client):
    body = "".join(f"2026-08-05T10:0{i}:00.000,-18.{i},-0.4,Stamped\n" for i in range(5))
    assert _csv_post(client, body, "Stamped")["accepted"] == 5
    for _ in range(2):
        assert _csv_post(client, body, "Stamped")["accepted"] == 0, \
            "a stamped chunk must be idempotent — this is what the checkpoint rests on"
    rows = client.get("/api/readings?probe=Stamped&limit=1000").get_json()["readings"]
    assert len(rows) == 5


def test_replaying_an_unstamped_chunk_does_duplicate(client):
    """Not the behaviour anyone wants, but the behaviour there is — and the
    documentation now says so. Pinned deliberately: if a later change makes this
    idempotent, PROTOCOL.md §7's caveat and the bufferFlush() comment must be
    revisited in the same commit, and this failing test is what says so."""
    body = "".join(f",-18.{i},-0.4,Clockless\n" for i in range(5))
    assert _csv_post(client, body, "Clockless")["accepted"] == 5
    _csv_post(client, body, "Clockless")
    _csv_post(client, body, "Clockless")
    rows = client.get("/api/readings?probe=Clockless&limit=1000").get_json()["readings"]
    assert len(rows) > 5, (
        "unstamped rows now dedupe on replay — good, but PROTOCOL.md §7 and the "
        "bufferFlush() comment both document that they do NOT. Update them.")


def test_an_unstamped_row_is_still_stored_rather_than_dropped(client):
    """The 2.8.2 trade-off that created the replay exposure. Dropping the reading
    outright — what it replaced — lost data on exactly the no-internet
    deployment this product is sold for, which was worse."""
    got = _csv_post(client, ",-18.5,-1.3,NoClock\n", "NoClock")
    assert got["accepted"] == 1 and got["rejected"] == 0
    rows = client.get("/api/readings?probe=NoClock&limit=10").get_json()["readings"]
    assert rows and rows[0]["temperature_c"] == -18.5
    assert rows[0]["timestamp"], "the hub must receipt-stamp what it accepts"

"""Tests for the diagnostics snapshot (core.diagnostics)."""
from core.diagnostics import build_diagnostics, db_size_bytes, human_size


class _FakeDB:
    def __init__(self, n, newest=None, path=None):
        self._n, self._newest, self.path = n, newest, path

    def count(self):
        return self._n

    def latest(self):
        return {"timestamp": self._newest} if self._newest else None


class _FakeFinder:
    def __init__(self, probes):
        self._p = probes

    def list_probes(self):
        return self._p


def test_human_size():
    assert human_size(0) == "0 B"
    assert human_size(None) == "—"
    assert human_size(512) == "512 B"
    assert human_size(2048) == "2.0 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"


def test_db_size_missing(tmp_path):
    assert db_size_bytes(str(tmp_path / "nope.db")) is None


def test_db_size_sums_wal_sidecar(tmp_path):
    base = tmp_path / "x.db"
    base.write_bytes(b"a" * 100)
    (tmp_path / "x.db-wal").write_bytes(b"b" * 50)
    assert db_size_bytes(str(base)) == 150


def test_build_counts_online_and_offline():
    probes = {
        "p1": {"name": "Fridge", "ip": "10.0.0.2", "properties": {"id": "p1"}, "last_seen": 995},
        "p2": {"name": "Freezer", "ip": "10.0.0.3", "properties": {"id": "p2"}, "last_seen": 100},
    }
    cfg = {
        "probe_online_timeout_sec": 60, "retention_days": 7,
        "notifications": {"enabled": True, "email": {"enabled": True},
                          "webhook": {"enabled": False}, "offline_alerts": True},
    }
    d = build_diagnostics(cfg, _FakeDB(42, newest="2026-06-09T00:00:00"),
                          _FakeFinder(probes), "http://hub:8088", "2.2.1", "Temperature Hub",
                          now=1000.0)
    assert d["probes"]["total"] == 2 and d["probes"]["online"] == 1
    assert d["database"]["readings"] == 42
    assert d["database"]["newest_reading"] == "2026-06-09T00:00:00"
    assert d["retention_days"] == 7
    assert d["notifications"] == {"enabled": True, "email": True,
                                  "webhook": False, "offline_alerts": True}
    assert d["server"]["base"] == "http://hub:8088"
    assert d["version"] == "2.2.1"


def test_probe_rows_overlay_db_reporting_freshness():
    # A probe that is mDNS-stale but still freshly POSTING to the DB (a
    # deep-sleep battery probe between radio wakes) must read online in the
    # per-probe rows — the same overlay /api/probes applies.
    class _ReportingDB(_FakeDB):
        def last_reading_epoch_per_probe(self, window_seconds=None):
            return {"p2": 950}  # posted 50 s before now=1000

    probes = {
        "p1": {"name": "Fridge", "ip": "10.0.0.2", "properties": {"id": "p1"}, "last_seen": 995},
        "p2": {"name": "Freezer", "ip": "10.0.0.3", "properties": {"id": "p2"}, "last_seen": 100},
    }
    cfg = {"probe_online_timeout_sec": 60}
    d = build_diagnostics(cfg, _ReportingDB(3), _FakeFinder(probes), "http://hub",
                          "2.4.0", "Setpoint", now=1000.0)
    rows = {p["probe_id"]: p for p in d["probes"]["list"]}
    assert rows["p1"]["online"] is True   # fresh via mDNS
    assert rows["p2"]["online"] is True   # stale via mDNS, fresh via readings
    assert d["probes"]["online"] == 2
    assert d["probes"]["reporting"] == 1


def test_build_contains_no_secrets():
    # Notification host/url/password/token must never appear in the snapshot.
    cfg = {
        "provision_token": "supersecret",
        "notifications": {"enabled": True,
                          "email": {"enabled": True, "password": "hunter2", "smtp_host": "smtp.example.com"},
                          "webhook": {"enabled": True, "url": "https://hooks.example.com/abc"}},
    }
    d = build_diagnostics(cfg, _FakeDB(1), _FakeFinder({}), "http://hub:8088",
                          "2.2.1", "Temperature Hub", now=1000.0)
    blob = repr(d)
    for secret in ("supersecret", "hunter2", "smtp.example.com", "hooks.example.com"):
        assert secret not in blob


def test_build_survives_broken_db():
    class _BoomDB:
        path = None

        def count(self):
            raise RuntimeError("db down")

        def latest(self):
            raise RuntimeError("db down")

    d = build_diagnostics({}, _BoomDB(), _FakeFinder({}), "", "2.2.1", "Temperature Hub", now=1.0)
    assert d["database"]["readings"] is None
    assert d["probes"]["total"] == 0


def test_build_includes_health_block(tmp_path):
    import datetime
    from core.db import Database
    db = Database(tmp_path / "h.db")
    db.append(datetime.datetime.now().isoformat(timespec="seconds"), 22.0, 71.6, "A")
    d = build_diagnostics({}, db, _FakeFinder({}), "http://hub", "2.4.0", "Setpoint")
    h = d["health"]
    assert {"healthy", "uptime_sec", "disk_free_bytes", "readings_24h", "rows_written",
            "ingest_rejected", "write_failures", "last_write_age_sec"} <= set(h)
    assert h["uptime_sec"] >= 0
    assert h["readings_24h"] == 1
    assert isinstance(h["disk_free_bytes"], int)  # real path -> real free space

"""Tests for the JSON read API (/api/readings*) and cross-surface online parity.

These lock in v2.4.3's "your data, everywhere" work:
  * a read-only JSON feed of latest + historical readings (the JSON twin of the
    CSV download and /metrics), and
  * /api/probes + /api/health counting a deep-sleep, DB-only probe as online so
    they agree with the dashboard's "Connected Probes".
"""
import datetime

from flask import Flask

from api.routes import create_api
from core.config import Config
from core.db import Database
from core.metrics import LATEST
from core.status import reporting_probe_ids


class _EmptyDiscovery:
    """mDNS sees nothing — models a deep-sleep probe whose radio is off between
    wakes, so any 'online' verdict must come from the database, not discovery."""

    def list_probes(self):
        return {}

    def update_last_seen(self, *a, **k):
        pass


def _client(tmp_path):
    db = Database(tmp_path / "r.db")
    cfg = Config(tmp_path / "c.json")
    app = Flask(__name__)
    app.register_blueprint(create_api(cfg, db, _EmptyDiscovery(),
                                      lambda: "http://hub:8088", ""))
    return app.test_client(), db, cfg


def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


def test_readings_latest_one_row_per_probe(tmp_path):
    client, db, _ = _client(tmp_path)
    now = datetime.datetime.now()
    db.append(_iso(now - datetime.timedelta(seconds=10)), 20.0, 68.0, "A")
    db.append(_iso(now), 21.0, 69.8, "A")                       # newer A wins
    db.append(_iso(now), 4.0, 39.2, "B", humidity=55.0, vpd=0.8)
    body = client.get("/api/readings/latest").get_json()
    assert body["count"] == 2
    rows = {r["probe_id"]: r for r in body["readings"]}
    assert rows["A"]["temperature_c"] == 21.0
    assert rows["B"]["humidity_pct"] == 55.0
    # A never reported humidity: a missing value must be JSON null, never "NaN".
    assert rows["A"]["humidity_pct"] is None


def test_readings_history_window_probe_and_stats(tmp_path):
    client, db, _ = _client(tmp_path)
    now = datetime.datetime.now()
    for i in range(5):
        db.append(_iso(now - datetime.timedelta(minutes=i)), 20.0 + i, 0.0, "A")
    db.append(_iso(now), 99.0, 0.0, "B")                        # must be filtered out
    body = client.get("/api/readings?window=24h&probe=A").get_json()
    assert body["probe"] == "A" and body["window"] == "24h"
    assert body["count"] == 5
    assert all(r["probe_id"] == "A" for r in body["readings"])
    ts = [r["timestamp"] for r in body["readings"]]
    assert ts == sorted(ts)                                     # oldest-first
    # stats are computed over the full window, not just the returned rows.
    assert body["stats"]["count"] == 5
    assert body["stats"]["max_c"] == 24.0


def test_readings_limit_caps_and_keeps_newest(tmp_path):
    client, db, _ = _client(tmp_path)
    now = datetime.datetime.now()
    for i in range(10):
        db.append(_iso(now - datetime.timedelta(minutes=10 - i)), float(i), 0.0, "A")
    body = client.get("/api/readings?probe=A&limit=3").get_json()
    assert body["count"] == 3
    # The newest 3 rows, returned oldest-first.
    assert [r["temperature_c"] for r in body["readings"]] == [7.0, 8.0, 9.0]


def test_readings_absolute_range_omits_window_stats(tmp_path):
    client, db, _ = _client(tmp_path)
    db.append(_iso(datetime.datetime.now()), 20.0, 0.0, "A")
    body = client.get("/api/readings?from=2000-01-01&to=2000-01-02").get_json()
    assert body["count"] == 0
    # window_stats can't honour an absolute range, so it's omitted rather than
    # reporting numbers that disagree with the returned rows.
    assert body["stats"] is None


def test_online_parity_db_only_probe_counts(tmp_path):
    # A probe never seen via mDNS but freshly reporting to the DB must read online
    # on /api/probes and be counted in /api/health — matching the dashboard.
    client, db, cfg = _client(tmp_path)
    db.append(_iso(datetime.datetime.now()), 20.0, 68.0, "DEEP")
    probes = client.get("/api/probes").get_json()
    assert any(p["probe_id"] == "DEEP" and p["online"] is True for p in probes)
    assert client.get("/api/health").get_json()["probes_online"] >= 1
    # ...and it comes from the same helper the dashboard/Diagnostics/metrics use.
    assert "DEEP" in reporting_probe_ids(cfg, db)


def test_clear_demo_data_evicts_metrics_series(tmp_path):
    # Removing/clearing a probe must drop it from the Prometheus registry too, so
    # /metrics stops serving a frozen ghost series after the UI has dropped it.
    from core.demo import load_demo_data, clear_demo_data
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    load_demo_data(db, cfg, hours=1, step_min=30)
    LATEST.record("DEMO-Fridge", 4.0)                # as the ingest path would
    assert "DEMO-Fridge" in LATEST.snapshot()
    clear_demo_data(db, cfg)
    assert "DEMO-Fridge" not in LATEST.snapshot()

import sys
import time
from pathlib import Path

import pytest
from flask import Flask

# Make the project root importable when pytest is run from anywhere.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeDiscovery:
    """Minimal stand-in for ProbeDiscovery with the update_last_seen contract."""

    def __init__(self):
        self._probes = {}

    def list_probes(self):
        return dict(self._probes)

    def update_last_seen(self, probe_id, host="", ip="", port=80):
        now = time.time()
        p = self._probes.get(probe_id)
        if p:
            p["last_seen"] = now
            if ip:
                p["ip"] = ip
            return
        self._probes[probe_id] = {
            "name": probe_id, "ip": ip, "host": host, "port": port,
            "properties": {"id": probe_id}, "last_seen": now, "source": "ingest",
        }


@pytest.fixture
def config(tmp_path):
    from core.config import Config
    return Config(tmp_path / "config.json")


def make_client(db_path, token="", discovery=None, cfg=None):
    """Build a Flask test client wired to a real SQLite-backed API blueprint."""
    from api.routes import create_api
    from core.db import Database
    if cfg is None:
        class _Cfg:
            def get(self, k, d=None):
                return {"probe_names": {}, "calibration_offsets": {}, "alert_thresholds": {},
                        "notifications": {}, "settings": {}}.get(k, d)
        cfg = _Cfg()
    if discovery is None:
        discovery = FakeDiscovery()
    db = Database(str(db_path))
    app = Flask(__name__)
    app.register_blueprint(create_api(cfg, db, discovery, lambda: "http://hub:8088", token))
    return app.test_client(), discovery


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "temperature_log.db"


@pytest.fixture
def client(tmp_db):
    c, _ = make_client(tmp_db, token="")
    return c

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
    """Minimal stand-in for ProbeDiscovery with the register_seen contract."""

    def __init__(self):
        self._probes = {}

    def list_probes(self):
        return dict(self._probes)

    def register_seen(self, probe_id, ip="", port=80, host=""):
        now = time.time()
        for p in self._probes.values():
            if p.get("properties", {}).get("id") == probe_id or p.get("name") == probe_id:
                p["last_seen"] = now
                if ip:
                    p["ip"] = ip
                return
        self._probes[probe_id] = {
            "name": probe_id, "ip": ip, "host": host, "port": port,
            "properties": {"id": probe_id}, "last_seen": now, "source": "ingest",
        }


@pytest.fixture
def tmp_csv(tmp_path):
    from core.storage import ensure_csv
    p = tmp_path / "temperature_log.csv"
    ensure_csv(p)
    return p


@pytest.fixture
def config(tmp_path):
    from core.config import Config
    return Config(tmp_path / "config.json")


def make_client(csv_path, token="", discovery=None, cfg=None):
    from api.routes import create_api
    if cfg is None:
        class _Cfg:
            def get(self, k, d=None):
                return {"probe_names": {}, "calibration": {}, "alert_thresholds": {},
                        "notifications": {}}.get(k, d)
        cfg = _Cfg()
    if discovery is None:
        discovery = FakeDiscovery()
    app = Flask(__name__)
    app.register_blueprint(create_api(cfg, str(csv_path), discovery, lambda: "http://hub:8080", token))
    return app.test_client(), discovery


@pytest.fixture
def client(tmp_csv):
    c, _ = make_client(tmp_csv, token="")
    return c

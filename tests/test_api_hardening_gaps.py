"""Small holes in the API and the background threads, each with a real consequence.

  * ``POST /api/config`` answered ``ok:true`` for a body it could not parse. The
    ``invalid_json`` error existed for exactly that case and could never fire,
    because ``get_json(silent=True) or {}`` turned a corrupt body into an empty
    one before the guard saw it — so a truncated write reported success and
    changed nothing.
  * ``POST /api/provision`` guarded ``port`` and then read ``interval_ms`` and
    ``token`` straight out of the same untrusted body, so either could 500.
  * ``_is_safe_provision_target`` decided "is this a LAN address?" with
    ``ipaddress.is_private``, which ``core/netaddr.py`` documents at length as
    the wrong test — it disagreed with the auto-provisioner in both directions.
  * A forwarded batch registered the SENDING HUB's probe ids in this hub's local
    mDNS registry, pointing at that hub's IP — which put another hub's probes on
    the Devices grid and handed them to the auto-provisioner to POST a token to.
  * ``AutoProvisioner`` shadowed ``threading.Thread._stop``, a real method, with
    a bool, so ``is_alive()`` and ``join()`` raised ``TypeError`` on it.
  * ``SSIDWatcher.stop()`` raced an in-flight scan, so a sighting from before
    the stop survived it — the one thing its docstring says must not happen.
"""
import threading
import time

import pytest

from flask import Flask

from api.routes import _is_safe_provision_target, create_api
from core.config import Config
from core.db import Database


class _Registry:
    """Stand-in discovery registry that records what gets filed in it."""

    def __init__(self):
        self.seen = []

    def update_last_seen(self, pid, host="", ip=""):
        self.seen.append(pid)

    def list_probes(self):
        return {}


def _make_client(tmp_path, token="", discovery=None):
    db = Database(tmp_path / "api.db")
    cfg = Config(tmp_path / "config.json")
    disc = discovery if discovery is not None else _Registry()
    app = Flask(__name__)
    app.register_blueprint(create_api(cfg, db, disc, lambda: "http://hub:8088", token))
    return app.test_client(), db, cfg


# --- POST /api/config -------------------------------------------------------

def test_an_unparseable_config_body_is_rejected_not_reported_as_saved(tmp_path):
    client, _db, _cfg = _make_client(tmp_path)
    r = client.post("/api/config", data="notjson{",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_json"


def test_a_valid_config_body_still_saves(tmp_path):
    client, _db, cfg = _make_client(tmp_path)
    r = client.post("/api/config", json={"retention_days": 90})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert cfg.get("retention_days") == 90


# --- POST /api/provision ----------------------------------------------------

@pytest.mark.parametrize("body", [
    {"host": "192.168.1.50", "interval_ms": "soon"},
    {"host": "192.168.1.50", "interval": [1, 2]},
    {"host": "192.168.1.50", "interval_ms": float("nan")},
    {"host": "192.168.1.50", "token": {"nested": "object"}},
    {"host": "192.168.1.50", "token": 12345},
])
def test_a_malformed_provision_body_is_a_400_not_a_500(tmp_path, body):
    client, _db, _cfg = _make_client(tmp_path)
    r = client.post("/api/provision", json=body)
    assert r.status_code == 400, r.get_data(as_text=True)


def test_a_well_formed_provision_body_is_not_rejected(tmp_path):
    client, _db, _cfg = _make_client(tmp_path)
    # No probe is actually there, so this fails to deliver — but it must get
    # past validation to find that out.
    r = client.post("/api/provision", json={"host": "192.168.1.50",
                                            "interval_ms": 30000, "token": "abc"})
    assert r.status_code == 200
    assert r.get_json()["total"] == 1


# --- who may be handed the device token -------------------------------------

@pytest.mark.parametrize("host,allowed", [
    ("192.168.1.50", True),
    ("10.0.0.5", True),
    ("100.64.0.1", True),        # RFC 6598 / Tailscale — is_private said no
    ("203.0.113.5", False),      # RFC 5737 doc space — is_private said yes
    ("198.18.0.1", False),       # RFC 2544 benchmarking — is_private said yes
    ("240.0.0.1", False),        # reserved — is_private said yes
    ("127.0.0.1", False),        # loopback: this endpoint stays stricter
    ("169.254.169.254", False),  # cloud metadata
    ("8.8.8.8", False),
    ("", False),
])
def test_the_provision_target_rule_matches_core_netaddr(host, allowed):
    assert _is_safe_provision_target(host) is allowed


def test_the_checked_address_is_what_gets_provisioned(tmp_path, monkeypatch):
    """One resolve, and the caller sends to the address that was checked — a
    second lookup at send time is a second answer to the same question."""
    import api.routes as routes
    sent = []
    monkeypatch.setattr(routes, "resolve_host", lambda h: "192.168.1.77")
    monkeypatch.setattr(routes, "provision_probe",
                        lambda h, p, *a, **k: sent.append(h) or True)
    client, _db, _cfg = _make_client(tmp_path)
    r = client.post("/api/provision", json={"host": "probe.local", "port": 80})
    assert r.status_code == 200
    assert sent == ["192.168.1.77"], "the name was re-resolved instead of reused"


# --- a forwarded batch is not a local probe ---------------------------------

def _client_with_registry(tmp_path):
    reg = _Registry()
    client, db, _cfg = _make_client(tmp_path, discovery=reg)
    return client, db, reg


def test_a_forwarded_batch_does_not_register_the_senders_probes_locally(tmp_path):
    client, _db, reg = _client_with_registry(tmp_path)
    csv = "2026-07-30T12:00:00.000Z,4.0,39.2,Store-Walkin"
    r = client.post("/api/ingest_csv", data=csv,
                    headers={"Content-Type": "text/csv", "X-Site": "savannah"})
    assert r.get_json()["accepted"] == 1, "the readings must still be stored"
    assert reg.seen == [], "another hub's probe landed in the local mDNS registry"


def test_a_probes_own_batch_still_registers(tmp_path):
    client, _db, reg = _client_with_registry(tmp_path)
    csv = "2026-07-30T12:00:00.000Z,4.0,39.2,Setpoint-000079"
    r = client.post("/api/ingest_csv", data=csv,
                    headers={"Content-Type": "text/csv"})
    assert r.get_json()["accepted"] == 1
    assert reg.seen == ["Setpoint-000079"]


# --- the ingest reply's per-probe settings ----------------------------------

def test_an_unidentified_probe_gets_the_settings_saved_on_its_own_card(tmp_path):
    # A reading with no usable id is FILED under "unidentified" so it lands
    # somewhere a screen can show it. Its settings must be looked up there too.
    client, _db, cfg = _make_client(tmp_path)
    cfg.update({"probe_intervals": {"unidentified": 900}})
    r = client.post("/api/ingest", json={"temperature_c": 4.0})
    conf = r.get_json().get("config") or {}
    assert conf.get("interval_ms") == 900_000, conf


# --- background threads -----------------------------------------------------

def test_the_auto_provisioner_is_a_working_thread_object():
    from provisioner import AutoProvisioner

    class _NoProbes:
        def list_probes(self):
            return {}

    prov = AutoProvisioner(_NoProbes(), lambda: "http://127.0.0.1:8088",
                           token="t", period_sec=1)
    # Both of these called Thread._stop internally and raised
    # "TypeError: 'bool' object is not callable" while it was shadowed.
    assert prov.is_alive() is False
    prov.start()
    prov.stop()
    prov.join(timeout=5)
    assert prov.is_alive() is False


def test_a_stopped_ssid_watcher_never_reports_a_pre_stop_sighting(monkeypatch):
    import wifi_scan

    started = threading.Event()
    release = threading.Event()

    def _slow_scan():
        started.set()
        release.wait(5)
        return {"Setpoint-9A3F2C"}

    monkeypatch.setattr(wifi_scan, "scan_ssids", _slow_scan)
    w = wifi_scan.SSIDWatcher("Setpoint-", interval_sec=60)
    w.start()
    assert started.wait(5), "the watcher never scanned"
    w.stop()                      # lands while the scan is still in flight
    release.set()
    for _ in range(100):          # let the worker try to commit its result
        if not w.running():
            break
        time.sleep(0.02)
    time.sleep(0.1)
    assert w.latest == set(), "a sighting from before the stop survived it"
    assert w.scanned is False


def test_a_running_ssid_watcher_still_reports_what_it_finds(monkeypatch):
    import wifi_scan
    monkeypatch.setattr(wifi_scan, "scan_ssids", lambda: {"Setpoint-9A3F2C"})
    w = wifi_scan.SSIDWatcher("Setpoint-", interval_sec=60)
    w.start()
    try:
        for _ in range(100):
            if w.scanned:
                break
            time.sleep(0.02)
        assert w.matched() == ["Setpoint-9A3F2C"]
    finally:
        w.stop()


# --- numbers the hub cannot represent ---------------------------------------

@pytest.mark.parametrize("field", ["temperature_c", "humidity_pct", "battery_pct",
                                   "battery_v"])
def test_an_oversized_json_integer_is_a_rejected_reading_not_a_500(tmp_path, field):
    # json.loads yields arbitrary-precision ints, and float(10**400) raises
    # OverflowError -- which is not a ValueError subclass, so it escaped both
    # ingest handlers. On the bulk path that loses the probe's WHOLE batch and
    # counts a write failure, so the hub also starts reporting itself unhealthy.
    client, _db, _cfg = _make_client(tmp_path)
    huge = "1" + "0" * 400
    body = '{"probe_id": "P1", "temperature_c": 4.0, "%s": %s}' % (field, huge)
    r = client.post("/api/ingest", data=body,
                    headers={"Content-Type": "application/json"})
    assert r.status_code in (200, 400), r.get_data(as_text=True)
    assert r.status_code != 500


def test_an_oversized_temperature_does_not_lose_the_rest_of_a_batch(tmp_path):
    client, db, _cfg = _make_client(tmp_path)
    huge = "1" + "0" * 400
    body = ('{"readings": ['
            '{"probe_id": "P1", "temperature_c": 4.0},'
            '{"probe_id": "P1", "temperature_c": %s},'
            '{"probe_id": "P1", "temperature_c": 5.0}]}' % huge)
    r = client.post("/api/ingest_csv", data=body,
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 200, r.get_data(as_text=True)
    payload = r.get_json()
    assert payload["accepted"] == 2 and payload["rejected"] == 1
    assert db.count() == 2


def test_a_numeric_probe_name_does_not_break_the_canonical_export(tmp_path):
    # normalize_config does not coerce probe_names values, so a hand-edited or
    # API-set numeric name reached export_csv and .strip() raised there — while
    # the Excel exports, which funnel every value through _csv_safe, were fine.
    import io
    from core.db import Database
    db = Database(tmp_path / "n.db")
    db.append("2026-07-30T12:00:00.000", 4.0, 39.2, "P1")
    buf = io.StringIO()
    db.export_csv(buf, name_map={"P1": 42})
    assert "4.0" in buf.getvalue()


# --- the manual provision push carries the threshold watch ------------------

def test_the_manual_provision_push_sends_the_watch(tmp_path, monkeypatch):
    """PROTOCOL.md §4.1 makes the three watch fields part of /provision, and
    desired_probe_config is the single source of truth for them — but this
    endpoint never passed `watch=`, so the documented manual push could not arm
    or disarm the watch on any firmware, whatever Settings reported."""
    import api.routes as routes
    sent = {}
    monkeypatch.setattr(routes, "resolve_host", lambda h: "192.168.1.77")
    monkeypatch.setattr(routes, "provision_probe",
                        lambda h, p, base, **kw: sent.update(kw) or True)
    client, _db, cfg = _make_client(tmp_path)
    cfg.update({"alert_thresholds": {"default": {"min": -30.0, "max": -12.0}},
                "probe_sample_sec": 60, "interval_sec": 900})
    r = client.post("/api/provision",
                    json={"host": "192.168.1.77", "port": 80, "interval_ms": 900000})
    assert r.status_code == 200
    assert sent.get("watch") == (-30.0, -12.0, 60000), sent


def test_the_watch_is_judged_by_the_interval_this_request_sends(tmp_path, monkeypatch):
    """desired_probe_config applies the always-on rule to the interval in
    CONFIG. This request can carry a different one — so a body asking for a 6 s
    interval must not be paired with a cadence resolved from the hub's
    configured 15 minutes, which is exactly the "reads as armed, is not"
    behaviour DEEP_SLEEP_MIN_MS was moved into core/protocol.py to stop."""
    import api.routes as routes
    sent = {}
    monkeypatch.setattr(routes, "resolve_host", lambda h: "192.168.1.77")
    monkeypatch.setattr(routes, "provision_probe",
                        lambda h, p, base, **kw: sent.update(kw) or True)
    client, _db, cfg = _make_client(tmp_path)
    cfg.update({"alert_thresholds": {"default": {"min": -30.0, "max": -12.0}},
                "probe_sample_sec": 60, "interval_sec": 900})
    client.post("/api/provision",
                json={"host": "192.168.1.77", "port": 80, "interval_ms": 6000})
    assert sent.get("watch")[2] == 0, sent


def test_the_manual_push_refuses_to_arm_a_watch_the_probe_cannot_run(tmp_path,
                                                                     monkeypatch):
    """Same rule as the auto-provisioner: below DEEP_SLEEP_MIN_MS the probe is
    always-on and cannot skip the radio on a sample wake, so a cadence there
    would promise behaviour the probe will not perform."""
    import api.routes as routes
    sent = {}
    monkeypatch.setattr(routes, "resolve_host", lambda h: "192.168.1.77")
    monkeypatch.setattr(routes, "provision_probe",
                        lambda h, p, base, **kw: sent.update(kw) or True)
    client, _db, cfg = _make_client(tmp_path)
    cfg.update({"alert_thresholds": {"default": {"min": -30.0, "max": -12.0}},
                "probe_sample_sec": 5, "interval_sec": 6})
    client.post("/api/provision", json={"host": "192.168.1.77", "port": 80})
    assert sent.get("watch")[2] == 0, sent


def test_the_ui_auth_gate_normalises_a_trailing_slash():
    """The allowlist is an exact-path set now, where it used to be a prefix
    test — so "/api/health/" would have drawn a 401 challenge instead of the
    redirect Flask answers with. Asserted against the source, like the rest of
    tests/test_ui_auth_gate.py, because importing app.py boots a whole hub."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "app.py").read_text()
    gate = src.split("def _ui_auth_gate()")[1].split("\ndef ")[0]
    assert 'rstrip("/")' in gate, (
        "the gate compares request.path verbatim, so a trailing slash turns an "
        "endpoint SECURITY.md documents as open into a 401")

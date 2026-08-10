"""Places the hub told the operator something it had not checked.

Each of these reports a state rather than measuring one, and each says the
reassuring thing:

  * ``MqttPublisher.is_ready()`` answered "a broker connection is up and
    readings will be published" from two flags set right after ``connect()`` --
    which returns before CONNACK. Wrong credentials, wrong port, an ACL
    rejection: all produced a green "publishing to <host>" in Settings while
    nothing was published, because ``publish()`` on a disconnected client
    RETURNS an error code instead of raising.
  * The Diagnostics health block is a hand-copied subset of
    ``HEALTH.snapshot()`` and left out the two worker keys, so the "Background
    tasks" row and the red "Alerting has stopped" banner were both unreachable
    in production -- the one failure this product most needs to announce.
  * Multi-site Save reported "connected to head office" off a cycle that
    short-circuited before making any request at all, so an unreachable address
    or a wrong token looked like a working one.
  * The audit log could not report the loudest tamper there is: deleting a
    field raised KeyError inside the hash, which ``verify()`` returned as a read
    error with no ``intact`` key at all. A malformed anchor was worse -- an
    unguarded ``int(tip["count"])`` at import time meant a corrupt 40-byte file
    stopped the hub from starting.
  * The Devices edit modal showed blank limits and "nothing is being checked"
    for a probe inheriting the hub-wide default, while the card behind it
    correctly showed that probe alarming.
  * And the Wi-Fi scanner thread outlived the page that started it.
"""
import json
import time

import pytest

from core.audit import AuditLog, _hash_entry
from core.mqtt_publish import MqttPublisher


class _FakeCfg(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


# --- MQTT says "publishing" only when it is --------------------------------

class _Client:
    def __init__(self, connected):
        self._connected = connected
        self.published = []

    def username_pw_set(self, *a, **k):
        pass

    def connect(self, *a, **k):
        pass

    def loop_start(self):
        pass

    def is_connected(self):
        return self._connected

    def publish(self, topic, payload, retain=False):
        self.published.append(topic)


@pytest.mark.parametrize("connected", [True, False])
def test_mqtt_readiness_asks_the_client_not_the_start_flag(monkeypatch, connected):
    import paho.mqtt.client as mqtt_mod
    monkeypatch.setattr(mqtt_mod, "Client", lambda *a, **k: _Client(connected))
    pub = MqttPublisher()
    pub.start(_FakeCfg({"mqtt": {"enabled": True, "host": "localhost"}}))
    assert pub.is_ready() is connected


def test_a_client_that_cannot_report_its_connection_is_taken_at_face_value(monkeypatch):
    class _Old:
        def username_pw_set(self, *a, **k): pass
        def connect(self, *a, **k): pass
        def loop_start(self): pass

    import paho.mqtt.client as mqtt_mod
    monkeypatch.setattr(mqtt_mod, "Client", lambda *a, **k: _Old())
    pub = MqttPublisher()
    pub.start(_FakeCfg({"mqtt": {"enabled": True, "host": "localhost"}}))
    assert pub.is_ready() is True


# --- Diagnostics can actually show a dead worker ---------------------------

class _DeadThread:
    def is_alive(self):
        return False


def _diagnostics_with_a_dead_alert_monitor(tmp_path):
    from core.applog import HEALTH
    from core.config import Config
    from core.db import Database
    from core.diagnostics import build_diagnostics

    HEALTH.register_worker("alert-monitor", _DeadThread(), required=True)
    try:
        return build_diagnostics(Config(tmp_path / "c.json"),
                                 Database(tmp_path / "d.db"), None,
                                 "http://hub:8088", "2.6.2", "Setpoint")
    finally:
        with HEALTH._lock:
            HEALTH._workers.pop("alert-monitor", None)


def test_the_diagnostics_health_block_carries_the_worker_keys(tmp_path):
    d = _diagnostics_with_a_dead_alert_monitor(tmp_path)
    assert "workers" in d["health"], "the Background tasks row can never render"
    assert "workers_down" in d["health"], "the 'Alerting has stopped' banner is dead"
    assert "alert-monitor" in d["health"]["workers_down"]


def test_the_banner_renders_from_what_build_diagnostics_actually_returns(tmp_path):
    from components.diagnostics_view import _health_card
    d = _diagnostics_with_a_dead_alert_monitor(tmp_path)
    assert "Alerting has stopped" in str(_health_card(d["health"]))


# --- Save says whether head office was reached -----------------------------

def test_an_idle_cycle_does_not_report_a_completed_request(tmp_path):
    from core.config import Config
    from core.db import Database
    from core.forwarder import UpstreamForwarder

    db = Database(tmp_path / "s.db")
    cfg = Config(tmp_path / "s.json")
    cfg.set("upstream", {"enabled": True, "url": "http://hq:8088",
                         "token": "T", "site": "atl"})
    fwd = UpstreamForwarder(db, cfg)          # nothing queued at all
    result = fwd.run_once_detailed()
    assert result.posted is False, "no request was made, so nothing was proved"


def test_a_completed_post_is_reported_as_contacted(tmp_path):
    import datetime
    import core.forwarder as fw
    from core.config import Config
    from core.db import Database
    from core.forwarder import UpstreamForwarder

    db = Database(tmp_path / "s.db")
    cfg = Config(tmp_path / "s.json")
    cfg.set("upstream", {"enabled": True, "url": "http://hq:8088",
                         "token": "T", "site": "atl"})
    db.append(datetime.datetime.now().isoformat(timespec="milliseconds"),
              4.0, 39.2, "P1")
    fwd = UpstreamForwarder(db, cfg)
    real, fw.post_batch = fw.post_batch, lambda *a, **k: 200
    try:
        assert fwd.run_once_detailed().posted is True
    finally:
        fw.post_batch = real


def test_the_save_notice_does_not_claim_a_connection_that_was_never_made(tmp_path,
                                                                        monkeypatch):
    import dash
    import components.settings_panel as sp
    from core.config import Config

    class _Fwd:
        def sync_now_detailed(self):
            return 0, "", False           # nothing queued: no request attempted

        def status(self):
            return {"pending": 0}

    monkeypatch.setattr(sp, "FORWARDER", _Fwd())
    monkeypatch.setattr(sp, "_upstream_is_cleartext_offsite", lambda url: False)
    app = dash.Dash(__name__)
    app.layout = dash.html.Div()
    app.config.suppress_callback_exceptions = True
    sp.register_settings_callbacks(app, Config(tmp_path / "c.json"))
    key, = [k for k in app.callback_map if "upstream-status.children" in k]
    fn = app.callback_map[key]["callback"].__wrapped__
    out, _site = fn(1, True, "http://hq.local:8088", "atlanta", "tok", 60)
    text = str(out.children)
    assert "connected to head office" not in text, text
    assert "has not been contacted" in text


# --- the audit log reports the loudest tamper there is ---------------------

def _configured_log(tmp_path):
    a = AuditLog()
    a.configure(tmp_path / "audit.log")
    a.record("config.change", detail="retention_days=90", actor="op")
    a.record("data.export", detail="temperature_log.csv", actor="op")
    return a, tmp_path / "audit.log"


def test_deleting_a_field_from_an_entry_reads_as_tampering(tmp_path):
    a, path = _configured_log(tmp_path)
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    del lines[0]["detail"]
    path.write_text("\n".join(json.dumps(e) for e in lines) + "\n", encoding="utf-8")
    result = a.verify()
    assert result["intact"] is False, result
    assert result.get("broken_at") == 0


def test_an_edited_field_still_reads_as_tampering(tmp_path):
    a, path = _configured_log(tmp_path)
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    lines[0]["detail"] = "retention_days=1"
    path.write_text("\n".join(json.dumps(e) for e in lines) + "\n", encoding="utf-8")
    assert a.verify()["intact"] is False


def test_an_untouched_log_still_verifies(tmp_path):
    a, _path = _configured_log(tmp_path)
    r = a.verify()
    assert r["intact"] is True and r["entries"] == 2


def test_a_missing_field_hashes_differently_from_an_empty_one():
    base = {"ts": "t", "actor": "a", "action": "x", "detail": "", "prev": "p"}
    stripped = {k: v for k, v in base.items() if k != "detail"}
    assert _hash_entry(base) != _hash_entry(stripped)


@pytest.mark.parametrize("anchor", ["[]", "5", '"x"', '{"count": "abc"}', "not json"])
def test_a_corrupt_anchor_does_not_stop_the_hub_from_starting(tmp_path, anchor):
    log_path = tmp_path / "audit.log"
    log_path.write_text("", encoding="utf-8")
    (tmp_path / "audit.log.tip").write_text(anchor, encoding="utf-8")
    a = AuditLog()
    a.configure(log_path)          # app.py calls this at import — must not raise
    a.record("config.change", detail="x", actor="op")
    assert "intact" in a.verify()


def test_an_unreadable_log_never_reports_itself_as_intact(tmp_path):
    a, path = _configured_log(tmp_path)
    path.write_text("{not json at all\n", encoding="utf-8")
    r = a.verify()
    assert r["intact"] is False, r
    assert "reason" in r


# --- the Devices modal agrees with the card behind it ----------------------

def test_the_edit_modal_shows_an_inherited_limit(tmp_path):
    import datetime
    import dash
    import components.devices_panel as dp
    from core.config import Config
    from core.db import Database

    db = Database(tmp_path / "d.db")
    now = datetime.datetime.now()
    db.append(now.isoformat(timespec="milliseconds"), 4.0, 39.2, "P1")
    cfg = Config(tmp_path / "c.json")
    cfg.update({"alert_thresholds": {"default": {"min": 1.0, "max": 5.0}}})

    app = dash.Dash(__name__)
    app.layout = dash.html.Div()
    app.config.suppress_callback_exceptions = True
    dp.register_devices_callbacks(app, None, cfg, db)
    key, = [k for k in app.callback_map
            if "edit-probe-min-input.placeholder" in k]
    entry = app.callback_map[key]
    fn = entry["callback"].__wrapped__
    n_state = len(entry["inputs"]) + len(entry.get("state", []))

    import dash as _dash
    ctx = [{"prop_id": '{"index":"P1","type":"edit-probe-btn"}.n_clicks', "value": 1}]
    args = [[1], 0, 0, False] + [None] * (n_state - 5) + ["celsius"]
    with _patch_ctx(_dash, ctx):
        out = fn(*args)
    # Value fields stay blank — a filled field is an override on the next Save.
    assert out[5] is None and out[6] is None
    # ...but the placeholders say what the probe is actually held to.
    assert "inherits 1" in str(out[12]), out[12]
    assert "inherits 5" in str(out[13]), out[13]


class _patch_ctx:
    """Stand in for ``dash.callback_context`` — the callback reads it by
    attribute at call time, so replacing the module attribute is enough."""

    def __init__(self, dash_mod, triggered):
        self.dash_mod = dash_mod
        self.triggered = triggered
        self._saved = None

    def __enter__(self):
        self._saved = self.dash_mod.callback_context
        outer = self

        class _Ctx:
            triggered = outer.triggered
        self.dash_mod.callback_context = _Ctx()
        return self

    def __exit__(self, *exc):
        self.dash_mod.callback_context = self._saved
        return False


# --- the scanner thread does not outlive the page --------------------------

def test_the_ssid_watcher_gives_up_when_nothing_is_polling(monkeypatch):
    import wifi_scan
    monkeypatch.setattr(wifi_scan, "scan_ssids", lambda: {"Setpoint-9A3F2C"})
    w = wifi_scan.SSIDWatcher("Setpoint-", interval_sec=0.02, idle_timeout_sec=0.1)
    w.start()
    deadline = time.monotonic() + 5
    while w.running() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not w.running(), "the thread outlived the page that started it"


def test_polling_keeps_the_watcher_alive(monkeypatch):
    import wifi_scan
    monkeypatch.setattr(wifi_scan, "scan_ssids", lambda: {"Setpoint-9A3F2C"})
    w = wifi_scan.SSIDWatcher("Setpoint-", interval_sec=0.02, idle_timeout_sec=0.3)
    w.start()
    try:
        for _ in range(15):
            time.sleep(0.04)
            w.start()          # what each ap-poll tick does
        assert w.running(), "a page that is still watching had its scan stopped"
    finally:
        w.stop()

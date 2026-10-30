"""Running unattended and being reachable: the availability batch.

One launch per hub, a name that survives an IP change, a QR code for phones, an
alert after the hub was away, a firewall rule for admin installs, a service
guide that does not orphan the data, and each probe's own status one click
from the Devices page.
"""
import http.server
import json
import os
import pathlib
import socket
import subprocess
import sys
import threading
import time

import pytest

import alert_monitor
from components.dashboard_view import build_events
from components.phone_modal import phone_modal_body
from components.probe_details import (fetch_probe_status, find_probe,
                                      not_answering_message, probe_page_url,
                                      status_rows)
from core.alerts import format_event
from core.mdns_advert import hub_hostname
from core.phone_access import access_urls, qr_data_uri
from core.single_instance import BUSY, FREE, HUB, probe_port

REPO = pathlib.Path(__file__).resolve().parent.parent


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(body: bytes):
    """A one-route HTTP server on a free port; returns (port, shutdown)."""
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1], srv.shutdown


# --- one hub per port -------------------------------------------------------------

def test_a_free_port_is_free():
    assert probe_port(_free_port()) == (FREE, None)


def test_a_running_hub_is_recognised_by_its_health_answer():
    port, stop = _serve(json.dumps({"ok": True, "version": "2.8.0",
                                    "base": "http://x:8088"}).encode())
    try:
        state, health = probe_port(port)
        assert state == HUB and health["version"] == "2.8.0"
    finally:
        stop()


def test_some_other_program_on_the_port_is_busy_not_a_hub():
    port, stop = _serve(b"<html>router admin</html>")
    try:
        assert probe_port(port) == (BUSY, None)
    finally:
        stop()


def _hub_env(tmp, port):
    env = {**os.environ, "MDNS_ENABLE": "0", "DATA_DIR": str(tmp), "PORT": str(port),
           "OPEN_BROWSER": "0", "PYTHONUNBUFFERED": "1"}
    env.pop("UI_USERNAME", None)
    return env


def test_a_second_launch_opens_the_running_hub_instead_of_starting_another(tmp_path):
    """Live, because the bug was ORDER: the second copy used to start its alert
    monitor before discovering the port was taken, judging the same readings
    twice until it crashed."""
    port = _free_port()
    first = subprocess.Popen([sys.executable, "app.py"], cwd=REPO,
                             env=_hub_env(tmp_path / "a", port),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(120):
            if probe_port(port)[0] == HUB:
                break
            time.sleep(0.5)
        else:
            pytest.fail("first hub never came up")
        second = subprocess.run([sys.executable, "app.py"], cwd=REPO,
                                env=_hub_env(tmp_path / "b", port),
                                capture_output=True, text=True, timeout=120)
        out = second.stdout + second.stderr
        assert second.returncode == 0, out[-2000:]
        assert "already running" in out
        assert "alert monitor started" not in out     # no duplicate background services
    finally:
        first.terminate()
        first.wait(timeout=30)


def test_a_port_held_by_something_else_fails_with_a_reason(tmp_path):
    port, stop = _serve(b"not a hub")
    try:
        res = subprocess.run([sys.executable, "app.py"], cwd=REPO,
                             env=_hub_env(tmp_path, port),
                             capture_output=True, text=True, timeout=120)
        assert res.returncode == 2
        assert "already in use by another program" in res.stdout + res.stderr
    finally:
        stop()


# --- a name that survives an IP change --------------------------------------------

def test_the_hub_is_advertised_as_setpoint_local(monkeypatch):
    monkeypatch.delenv("MDNS_HOSTNAME", raising=False)
    assert hub_hostname() == "setpoint.local."


@pytest.mark.parametrize("raw", ["kitchen-hub", "kitchen-hub.local", "kitchen-hub.local."])
def test_a_second_hub_can_be_given_its_own_name(monkeypatch, raw):
    monkeypatch.setenv("MDNS_HOSTNAME", raw)
    assert hub_hostname() == "kitchen-hub.local."


# --- open on your phone -----------------------------------------------------------

def test_phone_addresses_in_the_order_to_try_them():
    urls = access_urls("http://192.168.1.50:8088", True, ["192.168.1.50", "100.101.5.7"])
    assert [u["url"] for u in urls] == ["http://192.168.1.50:8088",
                                        "http://setpoint.local:8088",
                                        "http://100.101.5.7:8088"]


def test_loopback_is_never_offered_to_a_phone():
    urls = access_urls("http://127.0.0.1:8088", True, [])
    assert all("127.0.0.1" not in u["url"] for u in urls)
    assert access_urls("http://127.0.0.1:8088", False, []) == []


def test_the_qr_code_is_an_svg_a_browser_will_render_as_an_image():
    """The first version passed a check that the data was SVG and still drew
    nothing: inline SVG omits xmlns, which an <img> source cannot do without."""
    pytest.importorskip("segno")
    from urllib.parse import unquote
    uri = qr_data_uri("http://192.168.1.50:8088")
    assert uri.startswith("data:image/svg+xml")
    svg = unquote(uri.split(",", 1)[1])
    assert svg.startswith("<svg") and "xmlns='http://www.w3.org/2000/svg'" in svg


def test_the_modal_says_so_when_there_is_nothing_to_offer():
    body = phone_modal_body([], None)
    assert "no network address" in str(body)


def test_the_modal_warns_the_phone_will_ask_for_the_login():
    urls = access_urls("http://192.168.1.50:8088", False, [])
    assert "ask for the dashboard login" in str(phone_modal_body(urls, None, login_on=True))
    assert "ask for the dashboard login" not in str(phone_modal_body(urls, None))


# --- the hub was away ---------------------------------------------------------------

class _Db:
    def __init__(self, alive=None):
        self.meta = {} if alive is None else {alert_monitor.ALIVE_KEY: str(alive)}
        self.events = []

    def meta_get(self, k, d=""):
        return self.meta.get(k, d)

    def meta_set(self, k, v):
        self.meta[k] = v

    def record_event(self, kind, pid, **kw):
        self.events.append((kind, pid, kw.get("epoch")))


class _Notifier:
    def __init__(self):
        self.sent = []

    def dispatch(self, ev):
        self.sent.append(ev)
        return [("webhook", True, "sent")]


def _monitor(db, alerts_on=True):
    cfg = {"notifications": {"enabled": alerts_on}}
    n = _Notifier()
    return alert_monitor.AlertMonitor(db, cfg, notifier=n, period_sec=0), n


def test_a_long_gap_is_logged_and_sent_with_its_times():
    now = 1_800_000_000.0
    db = _Db(alive=now - 47 * 60)
    mon, n = _monitor(db)
    ev = mon.check_restart_gap(now=now)
    assert ev["kind"] == "hub_down"
    assert db.events == [("hub_down", "", now - 47 * 60), ("hub_up", "", now)]
    assert "47 min" in n.sent[0]["subject"]


def test_an_ordinary_restart_is_not_worth_an_alert():
    now = 1_800_000_000.0
    db = _Db(alive=now - 120)
    mon, n = _monitor(db)
    assert mon.check_restart_gap(now=now) is None
    assert db.events == [] and n.sent == []


def test_a_brand_new_hub_has_nothing_to_report():
    mon, n = _monitor(_Db())
    assert mon.check_restart_gap(now=1_800_000_000.0) is None


def test_the_gap_is_recorded_even_with_notifications_off():
    now = 1_800_000_000.0
    db = _Db(alive=now - 3600)
    mon, n = _monitor(db, alerts_on=False)
    mon.check_restart_gap(now=now)
    assert len(db.events) == 2 and n.sent == []


def test_the_alive_mark_is_written_at_most_once_a_minute():
    db = _Db()
    mon, _ = _monitor(db)
    mon.mark_alive(now=1000.0)
    mon.mark_alive(now=1030.0)
    assert db.meta[alert_monitor.ALIVE_KEY] == "1000"
    mon.mark_alive(now=1061.0)
    assert db.meta[alert_monitor.ALIVE_KEY] == "1061"


def test_the_message_reads_as_history_with_a_window_to_check():
    subject, message = format_event(
        {"probe_id": "", "kind": "hub_down", "start_epoch": 1_800_000_000,
         "end_epoch": 1_800_000_000 + 3 * 3600 + 5 * 60})
    assert "3 h 5 min" in subject
    assert "power cut" in message and "no alerts could be sent" in message


def test_the_event_feed_names_the_hub_not_a_mystery_probe():
    class Db:
        def list_events(self, **kw):
            if kw.get("kinds"):
                return []
            return [{"kind": "hub_down", "probe_id": "", "epoch": time.time() - 60},
                    {"kind": "hub_up", "probe_id": "", "epoch": time.time()}]
    text = str(build_events(Db(), {}, "celsius"))
    assert "HUB STOPPED" in text and "HUB BACK" in text
    assert "Unknown" not in text


# --- each probe's own page and status ----------------------------------------------

@pytest.mark.parametrize("addr,port,url", [
    ("192.168.1.42", 80, "http://192.168.1.42/"),
    ("192.168.1.42", 8080, "http://192.168.1.42:8080/"),
    ("Setpoint-9A3F2C.local.", 80, "http://Setpoint-9A3F2C.local/"),
    ("8.8.8.8", 80, None),             # never a link off the network
    ("N/A", 80, None),
    ("", 80, None),
])
def test_probe_page_links_only_to_the_lan(addr, port, url):
    assert probe_page_url(addr, port) == url


def test_details_are_fetched_by_id_from_the_hubs_own_discovery_table():
    class Finder:
        def list_probes(self):
            return {"a": {"probe_id": "Setpoint-9A3F2C", "name": "x",
                          "ip": "192.168.1.42", "port": 80}}
    assert find_probe(Finder(), "Setpoint-9A3F2C") == ("192.168.1.42", 80)
    assert find_probe(Finder(), "someone-else") is None


def test_an_off_lan_address_is_never_fetched():
    called = []
    assert fetch_probe_status("8.8.8.8", 80, getter=lambda *a: called.append(a)) is None
    assert called == []


def test_status_reads_in_plain_words():
    rows = dict(status_rows({
        "fw_version": "2.9.5", "probe_id": "Setpoint-9A3F2C", "sleep_mode": "deep",
        "temperature_c": 3.25, "timestamp": "2026-10-30T08:00:00Z", "time_valid": True,
        "interval_ms": 300000, "watch_armed": True, "sample_ms": 30000,
        "alert_min_c": 1.0, "alert_max_c": 5.0, "in_breach": False,
        "buffered_est_rows": 0, "fs_free_kb": 1200, "fs_total_kb": 1408}))
    assert rows["Firmware"] == "2.9.5"
    assert rows["Power mode"].startswith("Battery")
    assert rows["Reports every"] == "5 min"
    assert rows["Checks between reports"] == "every 30 s"
    assert rows["Readings waiting to upload"] == "None"
    assert rows["Limits on the probe"] == "1.0 to 5.0 °C"


def test_older_firmware_missing_fields_are_left_out_not_shown_as_none():
    rows = status_rows({"fw_version": "2.7.0", "sleep_mode": "modem"})
    assert dict(rows) == {"Firmware": "2.7.0", "Power mode": "Always on (USB)"}


def test_a_sleeping_probe_is_explained_not_reported_as_broken():
    assert "after each report" in not_answering_message("Walk-in")


# --- packaging ---------------------------------------------------------------------

def test_an_admin_install_adds_and_removes_the_firewall_rule():
    iss = (REPO / "packaging" / "windows" / "setpoint.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequiredOverridesAllowed=dialog" in iss
    add = [ln for ln in iss.splitlines() if "firewall add rule" in ln]
    assert add and "IsAdminInstallMode" in add[0] and "profile=private" in add[0]
    uninstall = iss.split("[UninstallRun]", 1)[1]
    assert "firewall delete rule" in uninstall


def test_the_service_guide_cannot_be_followed_into_an_empty_hub():
    guide = (REPO / "packaging" / "README.md").read_text(encoding="utf-8")
    section = guide.split("### Windows (start at boot", 1)[1].split("### macOS", 1)[0]
    assert "DATA_DIR" in section                       # Option B: the service's data
    assert "**your** account" in section               # Option A: same %LOCALAPPDATA%
    assert "Stop the task if it runs longer than 3 days" in section
    assert "Restore on AC power loss" in section


def test_the_licence_notice_generator_does_not_call_the_firmware_proprietary():
    src = (REPO / "packaging" / "gen_third_party_licenses.py").read_text(encoding="utf-8")
    assert "open source under the MIT License" in src
    assert "Setpoint firmware are proprietary" not in src

"""The "Set up a new probe" helper — and the claim it was not entitled to make.

The helper watches for the probe's ``Setpoint-XXXXXX`` SoftAP and reports what it
sees. When it saw nothing it said:

    Setpoint-XXXXXX: not found
    Waiting for the probe's setup network… Power the probe with no saved Wi-Fi…

That is a statement about the airwaves, and on a large share of real hubs this
machine is in no position to make it:

  * the hub is meant to live on an always-on mini-PC, which is usually wired —
    no Wi-Fi adapter, so nothing to scan with;
  * macOS 14.4 (Sonoma) removed the ``airport`` binary the mac path shells out
    to, so every newer Mac scans nothing;
  * Raspberry Pi OS Lite ships with neither ``nmcli`` nor ``iwlist``.

In all three the customer is told to go power-cycle a probe that may well have
been broadcasting the whole time, and the one instruction that would have worked
— join it from your phone — was never offered.
"""
import dash

from components import setup_helper
from components.setup_helper import SetupHelperBody, register_setup_helper_callbacks
import wifi_scan


class _Watcher:
    """Stand-in for SSIDWatcher: no threads, no shelling out."""

    def __init__(self, latest=(), scanned=True):
        self.latest = set(latest)
        self.scanned = scanned
        self.target = "Setpoint"

    def start(self):
        pass

    def matched(self):
        return sorted(s for s in self.latest
                      if s == self.target or s.startswith(self.target))


def _render(monkeypatch, watcher, can_scan):
    monkeypatch.setattr(setup_helper, "_watcher", watcher)
    monkeypatch.setattr(setup_helper, "scanner_available", lambda: can_scan)
    app = dash.Dash(__name__)
    app.layout = dash.html.Div(SetupHelperBody)
    register_setup_helper_callbacks(app)
    key, = [k for k in app.callback_map if "ap-status.children" in k]
    return app.callback_map[key]["callback"].__wrapped__(1)


def _text(node):
    if isinstance(node, str):
        return node
    if isinstance(node, (list, tuple)):
        return " ".join(_text(c) for c in node)
    children = getattr(node, "children", None)
    return _text(children) if children is not None else ""


def test_a_machine_that_cannot_scan_says_so_instead_of_not_found(monkeypatch):
    msg, color, label, _style = _render(monkeypatch, _Watcher(), can_scan=False)
    body = _text(msg)
    assert "can't scan" in body, body
    assert "not found" not in body.lower(), \
        "claimed the probe was not there on a machine that cannot look"
    assert "192.168.4.1" in body and "phone" in body, \
        "the one route that still works has to be offered"
    assert color == "warning" and "unavailable" in label


def test_seeing_no_networks_at_all_is_reported_as_such(monkeypatch):
    """A scanner that works but returns nothing whatsoever is a wired machine or
    a permissions problem, not a missing probe."""
    msg, color, label, _s = _render(
        monkeypatch, _Watcher(latest=(), scanned=True), can_scan=True)
    body = _text(msg)
    assert "no Wi-Fi networks" in body and "at all" in body
    assert color == "warning" and "No networks" in label


def test_networks_seen_but_no_setpoint_keeps_the_original_advice(monkeypatch):
    """The case the message was written for: scanning works, other networks are
    visible, the probe's is not. Powering the probe up IS the right next step."""
    msg, color, label, _s = _render(
        monkeypatch, _Watcher(latest={"HomeWiFi", "Neighbour5G"}), can_scan=True)
    body = _text(msg)
    assert "Waiting for the probe" in body
    assert color == "secondary" and label == "Setpoint-XXXXXX: not found"


def test_a_found_probe_still_wins_over_every_warning(monkeypatch):
    msg, color, label, style = _render(
        monkeypatch, _Watcher(latest={"Setpoint-9A3F2C", "HomeWiFi"}), can_scan=True)
    assert "Setpoint-9A3F2C" in _text(msg) and color == "success"
    assert "Found: Setpoint-9A3F2C" == label
    assert style == {}, "the config-page button must become clickable"


def test_nothing_is_asserted_before_the_first_scan_completes(monkeypatch):
    """`scanned` False means the section was only just opened. Saying "no
    networks at all" then would be a claim about how fast the user clicked."""
    msg, _c, label, _s = _render(
        monkeypatch, _Watcher(latest=(), scanned=False), can_scan=True)
    assert "no Wi-Fi networks" not in _text(msg)
    assert label == "Setpoint-XXXXXX: not found"


# --- the scanner probe itself ----------------------------------------------

def test_scanner_availability_is_a_real_check(monkeypatch):
    monkeypatch.setattr(wifi_scan.sys, "platform", "linux")
    monkeypatch.setattr(wifi_scan.shutil, "which", lambda name: None)
    assert wifi_scan.scanner_available() is False
    monkeypatch.setattr(wifi_scan.shutil, "which",
                        lambda name: "/usr/bin/nmcli" if name == "nmcli" else None)
    assert wifi_scan.scanner_available() is True


def test_a_sonoma_mac_reports_no_scanner_rather_than_running_a_missing_binary(monkeypatch):
    """macOS 14.4 removed `airport`. The old code ran the hardcoded path anyway,
    caught the resulting error, and returned an empty set indistinguishable from
    a genuine empty scan."""
    monkeypatch.setattr(wifi_scan.sys, "platform", "darwin")
    monkeypatch.setattr(wifi_scan.shutil, "which", lambda name: None)
    monkeypatch.setattr(wifi_scan.os.path, "exists", lambda p: False)
    assert wifi_scan.scanner_available() is False
    assert wifi_scan.scan_ssids() == set()

    monkeypatch.setattr(wifi_scan.os.path, "exists", lambda p: True)
    assert wifi_scan.scanner_available() is True


def test_the_scan_never_shells_out_with_an_empty_program_name(monkeypatch):
    """`_run([""])` would raise, not merely fail — the guard has to be before it."""
    monkeypatch.setattr(wifi_scan.sys, "platform", "darwin")
    monkeypatch.setattr(wifi_scan.shutil, "which", lambda name: None)
    monkeypatch.setattr(wifi_scan.os.path, "exists", lambda p: False)
    called = []
    monkeypatch.setattr(wifi_scan, "_run", lambda cmd: called.append(cmd) or "")
    wifi_scan.scan_ssids()
    assert not called, f"ran a command with no binary to run: {called}"

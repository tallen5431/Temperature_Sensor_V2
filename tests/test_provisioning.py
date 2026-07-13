"""Tests for bounded DNS resolution and the probe HTTP helpers (provisioning)."""
import time

import provisioning
from provisioning import get_probe_status, provision_probe, resolve_host


def test_resolve_host_ip_literal_is_fast():
    # An IP literal needs no DNS lookup and returns itself immediately.
    t0 = time.time()
    assert resolve_host("192.168.1.50") == "192.168.1.50"
    assert time.time() - t0 < 1.0


def test_resolve_host_blank_is_none():
    assert resolve_host("") is None
    assert resolve_host(None) is None


def test_resolve_host_timeout_is_bounded(monkeypatch):
    # A resolver that hangs must not hang the caller past the timeout.
    def _hang(_host):
        time.sleep(30)
    monkeypatch.setattr(provisioning.socket, "gethostbyname", _hang)
    t0 = time.time()
    assert resolve_host("slow.local", timeout=0.3) is None
    assert time.time() - t0 < 2.0  # returned promptly, didn't wait 30s


def test_probe_helpers_fail_fast_on_unresolvable(monkeypatch):
    # get_probe_status/provision_probe must return None/False (not raise, not
    # block) when the host can't be resolved.
    monkeypatch.setattr(provisioning, "resolve_host", lambda *a, **k: None)
    assert get_probe_status("nope.local", 80) is None
    assert provision_probe("nope.local", 80, "http://hub") is False

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


def test_clamp_resolution_bits():
    from provisioning import clamp_resolution_bits
    assert clamp_resolution_bits(11) == 11
    assert clamp_resolution_bits(9) == 9 and clamp_resolution_bits(12) == 12
    assert clamp_resolution_bits(20) == 12   # over max -> clamped
    assert clamp_resolution_bits(3) == 9     # under min -> clamped
    assert clamp_resolution_bits("10") == 10
    assert clamp_resolution_bits(None) == 11         # default
    assert clamp_resolution_bits("junk", default=10) == 10


class _OkResp:
    ok = True
    status_code = 200


def test_provision_probe_includes_resolution(monkeypatch):
    captured = {}
    monkeypatch.setattr(provisioning, "resolve_host", lambda *a, **k: "10.0.0.9")
    monkeypatch.setattr(provisioning.requests, "post",
                        lambda url, json=None, timeout=None: (captured.update(body=json) or _OkResp()))
    assert provision_probe("p.local", 80, "http://hub", interval_ms=5000, resolution_bits=12) is True
    assert captured["body"]["resolution_bits"] == 12
    assert captured["body"]["interval_ms"] == 5000
    # out-of-range is clamped into the payload
    provision_probe("p.local", 80, "http://hub", resolution_bits=99)
    assert captured["body"]["resolution_bits"] == 12


def test_provision_probe_omits_resolution_when_none(monkeypatch):
    captured = {}
    monkeypatch.setattr(provisioning, "resolve_host", lambda *a, **k: "10.0.0.9")
    monkeypatch.setattr(provisioning.requests, "post",
                        lambda url, json=None, timeout=None: (captured.update(body=json) or _OkResp()))
    provision_probe("p.local", 80, "http://hub")  # no resolution_bits arg
    assert "resolution_bits" not in captured["body"]  # backward compatible

"""Tests for the auto-provisioner's token-delivery guarantee (provisioner)."""
import time

import provisioner as prov_mod
from provisioner import AutoProvisioner


class _FakeDiscovery:
    def __init__(self, probes):
        self._probes = probes

    def list_probes(self):
        return self._probes

    def update_probe_ip(self, *a, **k):
        pass

    def prune_stale(self, *a, **k):
        return 0


def _run_one_cycle(ap, timeout=2.0):
    """Start the provisioner, wait until it has done at least one pass, stop it."""
    ap.start()
    deadline = time.time() + timeout
    while time.time() < deadline and not ap._provisioned:
        time.sleep(0.02)
    ap.stop()


def test_force_provisions_matching_probe_once_to_deliver_token(monkeypatch):
    # A probe whose visible config (server_url/interval) already matches would be
    # skipped by the status shortcut — but its token is invisible, so we must push
    # at least once so the current device token actually reaches it.
    calls = []
    monkeypatch.setattr(prov_mod, "get_probe_status",
                        lambda h, p, timeout=3.0: {"server_url": "http://hub/api/ingest",
                                                   "interval_ms": 5000})
    monkeypatch.setattr(prov_mod, "provision_probe",
                        lambda h, p, base, token="", interval_ms=5000, timeout=3.0:
                        (calls.append((h, token)) or True))

    disc = _FakeDiscovery({"A": {"ip": "192.168.1.9", "host": "192.168.1.9",
                                 "port": 80, "properties": {"id": "A"}}})
    ap = AutoProvisioner(disc, lambda: "http://hub", token="TOK",
                         interval_ms=5000, period_sec=30)
    _run_one_cycle(ap)

    assert calls, "probe was skipped and never received the token"
    assert calls[0][1] == "TOK"  # the current token was delivered
    assert "A" in ap._provisioned

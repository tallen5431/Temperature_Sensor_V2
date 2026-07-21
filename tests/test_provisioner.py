"""Tests for the auto-provisioner: token-delivery guarantee, live global
interval, deep-sleep probe skipping and the desired-config hash shortcut."""
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
                        lambda h, p, base, token="", interval_ms=5000, resolution_bits=None, timeout=3.0:
                        (calls.append((h, token)) or True))

    disc = _FakeDiscovery({"A": {"ip": "192.168.1.9", "host": "192.168.1.9",
                                 "port": 80, "properties": {"id": "A"}}})
    ap = AutoProvisioner(disc, lambda: "http://hub", token="TOK",
                         interval_ms=5000, period_sec=30)
    _run_one_cycle(ap)

    assert calls, "probe was skipped and never received the token"
    assert calls[0][1] == "TOK"  # the current token was delivered
    assert "A" in ap._provisioned


def _probe(probe_id, ip="192.168.1.9", last_seen=None):
    d = {"ip": ip, "host": ip, "port": 80, "properties": {"id": probe_id}}
    if last_seen is not None:
        d["last_seen"] = last_seen
    return d


def _make_ap(probes, cfg=None, **kw):
    kwargs = dict(token="TOK", interval_ms=5000, period_sec=30, cfg=cfg)
    kwargs.update(kw)
    return AutoProvisioner(_FakeDiscovery(probes), lambda: "http://hub", **kwargs)


def _patch_net(monkeypatch, resolves=None, statuses=None, provisions=None,
               status_result=None):
    """Stub every network touchpoint, recording calls into the given lists."""
    def _resolve(host, timeout=3.0):
        if resolves is not None:
            resolves.append(host)
        return None

    def _status(h, p, timeout=3.0):
        if statuses is not None:
            statuses.append(h)
        return status_result

    def _provision(h, p, base, token="", interval_ms=5000, resolution_bits=None,
                   timeout=3.0):
        if provisions is not None:
            provisions.append({"host": h, "token": token,
                               "interval_ms": interval_ms,
                               "resolution_bits": resolution_bits})
        return True

    monkeypatch.setattr(prov_mod, "_resolve_with_timeout", _resolve)
    monkeypatch.setattr(prov_mod, "get_probe_status", _status)
    monkeypatch.setattr(prov_mod, "provision_probe", _provision)


def test_interval_sec_change_propagates_without_restart(monkeypatch):
    # The fallback interval must come from live config each cycle — otherwise
    # the provisioner keeps reverting probes to the stale boot-time value.
    provisions = []
    _patch_net(monkeypatch, provisions=provisions)
    cfg = {"interval_sec": 5}
    ap = _make_ap({"A": _probe("A", last_seen=time.time())}, cfg=cfg)
    ap._run_cycle()
    assert [c["interval_ms"] for c in provisions] == [5000]

    cfg["interval_sec"] = 2  # operator changes the global interval, no restart
    ap._run_cycle()
    assert provisions[-1]["interval_ms"] == 2000


def test_sleeping_probe_skipped_without_resolve_or_http(monkeypatch):
    resolves, statuses, provisions = [], [], []
    _patch_net(monkeypatch, resolves=resolves, statuses=statuses,
               provisions=provisions)
    cfg = {"interval_sec": 5}  # fresh window: 300 s (offline_after default)
    ap = _make_ap({"S": _probe("S", last_seen=time.time() - 4000)}, cfg=cfg)
    ap._run_cycle()

    assert resolves == []    # no resolver thread burned on a sleeping probe
    assert statuses == []    # no /status GET either
    assert provisions == []
    assert "S" not in ap._provisioned


def test_sleep_skip_falls_back_to_3600_without_cfg(monkeypatch):
    provisions = []
    _patch_net(monkeypatch, provisions=provisions)
    ap = _make_ap({"S": _probe("S", last_seen=time.time() - 4000)}, cfg=None)
    ap._run_cycle()
    assert provisions == []  # 4000 s silent > 3600 s fallback -> skipped

    ap2 = _make_ap({"S": _probe("S", last_seen=time.time() - 1000)}, cfg=None)
    ap2._run_cycle()
    assert len(provisions) == 1  # 1000 s silent < 3600 s -> still provisioned


def test_unchanged_desired_config_skips_status_get(monkeypatch):
    statuses, provisions = [], []
    _patch_net(monkeypatch, statuses=statuses, provisions=provisions)
    cfg = {"interval_sec": 5}
    ap = _make_ap({"A": _probe("A", last_seen=time.time())}, cfg=cfg)
    ap._run_cycle()  # first cycle always pushes (token delivery)
    assert len(provisions) == 1 and "A" in ap._provisioned

    ap._run_cycle()
    ap._run_cycle()
    assert statuses == []        # steady state: not even a /status GET
    assert len(provisions) == 1  # and no re-provision (no NVS churn)


def test_changed_interval_reprovisions_after_steady_state(monkeypatch):
    statuses, provisions = [], []
    _patch_net(monkeypatch, statuses=statuses, provisions=provisions)
    cfg = {"interval_sec": 5}
    ap = _make_ap({"A": _probe("A", last_seen=time.time())}, cfg=cfg)
    ap._run_cycle()
    ap._run_cycle()  # steady state: desired hash matches, nothing sent
    assert len(provisions) == 1

    cfg["probe_intervals"] = {"A": 2}  # per-probe override changes the config
    ap._run_cycle()
    assert len(provisions) == 2
    assert provisions[-1]["interval_ms"] == 2000

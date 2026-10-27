"""The outbound check-in that reports the one failure the hub cannot: itself.

Every Setpoint alarm is raised by the hub, so a crashed, sleeping or unpowered
hub PC goes silent with nobody told. The heartbeat hands that job to an outside
service. These tests pin what makes it trustworthy: it is off until asked for,
it only checks in when the hub is actually working, a slow host cannot stall
alert evaluation, and the URL — the credential — never reaches a log or the
unauthenticated diagnostics endpoint.
"""
import threading

import pytest

import alert_monitor
from core import heartbeat as hb_mod
from core.config_schema import normalize_config
from core.heartbeat import Heartbeat, heartbeat_settings, ping

URL = "https://hc-ping.com/0f3c-secret-uuid"


class _Cfg(dict):
    def get(self, k, d=None):
        return super().get(k, d)


class _Health:
    def __init__(self, failing=False):
        self.failing = failing

    def write_failing(self):
        return self.failing


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _beat(cfg, clock=None, health=None):
    """A Heartbeat whose 'thread' runs inline (pair with the ``pings`` fixture)."""
    return Heartbeat(cfg, health=health or _Health(), clock=clock or _Clock(),
                     spawn=lambda fn: fn())


@pytest.fixture
def pings(monkeypatch):
    sent = []
    monkeypatch.setattr(hb_mod, "ping", lambda url: (sent.append(url), (True, "ok"))[1])
    return sent


def _on(interval=300, url=URL):
    return _Cfg(heartbeat={"enabled": True, "url": url, "interval_sec": interval})


# --- off until asked for --------------------------------------------------------

@pytest.mark.parametrize("cfg", [
    _Cfg(),
    _Cfg(heartbeat={"enabled": False, "url": URL}),
    _Cfg(heartbeat={"enabled": True, "url": ""}),
    _Cfg(heartbeat={"enabled": True, "url": "hc-ping.com/no-scheme"}),
])
def test_nothing_is_sent_unless_enabled_with_a_real_url(cfg, pings):
    h = _beat(cfg)
    assert h.tick() is False
    assert pings == []


def test_the_interval_cannot_be_set_below_a_minute():
    assert heartbeat_settings(_on(interval=5)) == (URL, 60)


# --- only when the hub is working -----------------------------------------------

def test_checks_in_then_waits_out_the_interval(pings):
    clock = _Clock()
    h = _beat(_on(interval=300), clock=clock)
    assert h.tick() is True
    clock.t += 299
    assert h.tick() is False
    clock.t += 1
    assert h.tick() is True
    assert pings == [URL, URL]


def test_withheld_while_database_writes_are_failing(pings):
    """A hub that cannot store readings is down in every way that matters, even
    though the process is up — the outside service should say so."""
    h = _beat(_on(), health=_Health(failing=True))
    assert h.tick() is False
    assert pings == []


def test_a_slow_host_does_not_stack_requests():
    started = []
    h = Heartbeat(_on(interval=60), health=_Health(), clock=_Clock(),
                  spawn=lambda fn: started.append(fn))      # never runs: in flight
    assert h.tick() is True
    h._clock.t += 3600
    assert h.tick() is False
    assert len(started) == 1


def test_the_monitor_checks_in_only_after_a_clean_cycle(monkeypatch):
    """Sent from the alert monitor's own loop: a monitor that is erroring every
    cycle has stopped raising alarms, so it must stop checking in too."""
    def run_once(fail):
        mon = alert_monitor.AlertMonitor(db=None, cfg=_on(), period_sec=0)
        ticks = []
        if fail:
            monkeypatch.setattr(mon, "check_once", lambda: 1 / 0)
        else:
            monkeypatch.setattr(mon, "check_once", lambda: [])
        for name in ("maybe_purge", "maybe_prune_probes", "maybe_daily_summary"):
            monkeypatch.setattr(mon, name, lambda: None)

        def tick():
            ticks.append(1)
            mon._stop_event.set()
        monkeypatch.setattr(mon.heartbeat, "tick", tick)
        if fail:                       # nothing will tick, so stop after one pass
            threading.Timer(0.2, mon._stop_event.set).start()
        mon.run()
        return ticks

    assert run_once(fail=False) == [1]
    assert run_once(fail=True) == []


# --- the URL is a credential ----------------------------------------------------

def test_a_failed_ping_names_the_host_not_the_url(monkeypatch):
    def boom(url, timeout=None):
        raise ConnectionError(f"Max retries exceeded with url: {url}")
    monkeypatch.setattr(hb_mod.requests, "get", boom)
    ok, detail = ping(URL)
    assert not ok
    assert "hc-ping.com" in detail and "secret-uuid" not in detail


def test_status_reports_outcome_without_the_url(pings):
    h = _beat(_on())
    h.tick()
    st = h.status()
    assert st["enabled"] is True and st["host"] == "hc-ping.com"
    assert st["last_ok_age_sec"] == 0.0
    assert "secret-uuid" not in repr(st)


def test_diagnostics_carries_the_heartbeat_without_the_url(monkeypatch):
    monkeypatch.setattr(hb_mod, "CURRENT", None)
    st = hb_mod.current_status(_on())
    assert st["enabled"] is True and "secret-uuid" not in repr(st)


# --- config ---------------------------------------------------------------------

def test_config_coerces_a_hand_edited_heartbeat_block():
    cfg, warns = normalize_config(
        {"heartbeat": {"enabled": "yes", "url": 5, "interval_sec": "10"},
         "keep_awake": "no"})
    assert cfg["heartbeat"] == {"enabled": True, "url": "5", "interval_sec": 60}
    assert cfg["keep_awake"] is False
    assert warns

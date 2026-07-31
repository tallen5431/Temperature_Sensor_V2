"""Appliance health must be judged on the same clock as the probes.

``HealthState.snapshot`` defaults to a flat 120 s and its docstring invites
callers "monitoring slow-cadence probes" to pass an interval-aware bound —
but no caller did. One probe on a 600 s cadence writes once per 600 s, so
``healthy`` was true for 120 s of every 600 and false for the other 480: the
Diagnostics page rendered "Needs attention" directly above its own probe table
listing that probe online, ``/api/health`` said ``healthy:false``, and
``setpoint_healthy`` flapped 1→0→1 on every scrape — the exact metric a Grafana
alert would watch.

``probe_fresh_window``'s docstring calls itself "the single source of truth for
'is this probe fresh?'" so that the surfaces "can never disagree on the same
screen". The health badge was the one surface not using it.
"""
import time

import pytest

from core.applog import HealthState
from core.status import hub_health_window


@pytest.mark.parametrize("cfg,expected_min", [
    ({}, 300),                                     # floor == OFFLINE_AFTER_SEC
    ({"interval_sec": 5}, 300),                    # fast fleet keeps the floor
    ({"probe_intervals": {"A": 600}}, 1500),       # 600 * 2.5
    ({"probe_intervals": {"A": 7200}}, 18000),     # 2 h cadence
])
def test_window_scales_with_the_slowest_probe(cfg, expected_min):
    assert hub_health_window(cfg) == expected_min


def test_widest_probe_wins_in_a_mixed_fleet():
    cfg = {"probe_intervals": {"FAST": 5, "SLOW": 7200}}
    assert hub_health_window(cfg) == 18000


def test_garbage_config_falls_back_to_the_floor():
    """Config is user-editable; health must never raise."""
    assert hub_health_window({"probe_intervals": "not a dict"}) >= 120
    assert hub_health_window({"health_fresh_sec": "abc"}) >= 120


def test_a_slow_probe_no_longer_reads_unhealthy_between_writes():
    """The regression itself: a 600 s cadence, 5 minutes since the last write."""
    h = HealthState()
    h.record_write()
    h.last_write_ts = time.time() - 300      # 5 min ago; next write due at 600 s

    assert h.snapshot(120)["healthy"] is False            # the old flat bound
    cfg = {"probe_intervals": {"A": 600}}
    assert h.snapshot(hub_health_window(cfg))["healthy"] is True


def test_a_genuinely_dead_hub_still_reads_unhealthy():
    """Widening the window must not make health unfalsifiable."""
    h = HealthState()
    h.record_write()
    h.last_write_ts = time.time() - 40000    # far beyond even a 2 h cadence
    cfg = {"probe_intervals": {"A": 7200}}
    assert h.snapshot(hub_health_window(cfg))["healthy"] is False

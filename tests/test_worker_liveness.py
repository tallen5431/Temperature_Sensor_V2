"""If the alert monitor thread dies, nothing used to notice.

This is the worst failure this product has, and it was the one with no detector.
Every other signal keeps looking correct while it is happening:

  * readings keep arriving — they are written on the request thread, not the
    monitor, so `rows_written` climbs and `last_write_age_sec` stays small;
  * the dashboard keeps drawing live cards and a moving chart;
  * `/api/health` reported `healthy: true`;
  * `setpoint_healthy` stayed at 1, so a Grafana alert wired to it stayed quiet;
  * the Diagnostics page said "Healthy".

And no alarm is ever raised again. The counters in `HealthState` cannot help:
they only record failures something LIVE observed, and the thing that would have
observed this one is the thing that stopped.

Only the alert monitor is `required`. The auto-provisioner and the upstream
forwarder are features — a hub with those stopped is degraded, not blind — so
they are reported but do not condemn the appliance.
"""
from core.applog import HealthState
from core.metrics import render_prometheus


class FakeThread:
    def __init__(self, alive=True):
        self._alive = alive

    def is_alive(self):
        return self._alive

    def die(self):
        self._alive = False


def _health(**workers):
    """A hub that is writing happily, with the given workers registered."""
    h = HealthState()
    for name, (thread, required) in workers.items():
        h.register_worker(name, thread, required=required)
    h.record_write()
    return h


def test_a_dead_alert_monitor_makes_the_hub_unhealthy():
    mon = FakeThread()
    h = _health(alert_monitor=(mon, True))
    assert h.snapshot()["healthy"] is True

    mon.die()
    snap = h.snapshot()
    assert snap["healthy"] is False, \
        "readings still arriving is not health when nothing is checking them"
    assert snap["workers_down"] == ["alert_monitor"]


def test_writes_still_flowing_cannot_mask_it():
    """The exact shape of the old blind spot: the write path is a different
    thread, so every write-based signal stays green."""
    mon = FakeThread()
    h = _health(alert_monitor=(mon, True))
    mon.die()
    for _ in range(50):
        h.record_write()
    snap = h.snapshot()
    assert snap["rows_written"] == 51 and snap["last_write_age_sec"] < 5
    assert snap["healthy"] is False


def test_an_optional_worker_stopping_does_not_condemn_the_hub():
    prov = FakeThread()
    fwd = FakeThread()
    h = _health(alert_monitor=(FakeThread(), True),
                auto_provisioner=(prov, False), upstream_forwarder=(fwd, False))
    prov.die()
    fwd.die()
    snap = h.snapshot()
    assert snap["healthy"] is True, "a stopped feature is degraded, not blind"
    assert snap["workers_down"] == []
    assert snap["workers"] == {"alert_monitor": True, "auto_provisioner": False,
                               "upstream_forwarder": False}, \
        "but it must still be visible — 'which one' is the first support question"


def test_a_worker_that_raises_on_is_alive_counts_as_down():
    """A health probe must never raise, and 'I could not tell' is not 'fine'."""
    class Broken:
        def is_alive(self):
            raise RuntimeError("handle went away")

    h = _health(alert_monitor=(Broken(), True))
    snap = h.snapshot()
    assert snap["workers"] == {"alert_monitor": False}
    assert snap["healthy"] is False


def test_a_hub_with_no_registered_workers_is_unchanged():
    """Every existing caller — tests, /metrics' stand-in db — registers none."""
    h = HealthState()
    h.record_write()
    snap = h.snapshot()
    assert snap["healthy"] is True
    assert snap["workers"] == {} and snap["workers_down"] == []


def test_re_registering_replaces_rather_than_duplicates():
    h = HealthState()
    first, second = FakeThread(alive=False), FakeThread(alive=True)
    h.register_worker("alert_monitor", first, required=True)
    h.register_worker("alert_monitor", second, required=True)
    assert h.snapshot()["workers"] == {"alert_monitor": True}


# --- the scrape ------------------------------------------------------------

def test_prometheus_drops_setpoint_healthy_when_the_monitor_dies():
    mon = FakeThread()
    h = _health(alert_monitor=(mon, True))
    mon.die()
    text = render_prometheus(h.snapshot(), {}, 1, "2.6.2")
    assert "setpoint_healthy 0" in text, \
        "a Grafana alert on setpoint_healthy would have stayed quiet"


def test_prometheus_names_which_worker_stopped():
    """setpoint_healthy says something is wrong; this says what, and the answer
    changes what to do about it."""
    mon, prov = FakeThread(), FakeThread()
    h = _health(alert_monitor=(mon, True), auto_provisioner=(prov, False))
    prov.die()
    text = render_prometheus(h.snapshot(), {}, 1, "2.6.2")
    assert 'setpoint_worker_up{worker="alert_monitor"} 1' in text
    assert 'setpoint_worker_up{worker="auto_provisioner"} 0' in text
    assert "setpoint_healthy 1" in text, "an optional worker must not flip healthy"


def test_the_worker_gauge_is_absent_when_nothing_is_registered():
    """No empty HELP/TYPE block on a scrape from a hub that registers none."""
    h = HealthState()
    h.record_write()
    assert "setpoint_worker_up" not in render_prometheus(h.snapshot(), {}, 0, "2.6.2")


# --- and the page a person actually reads ----------------------------------

def test_diagnostics_spells_out_what_a_dead_monitor_means():
    """"1 of 3 running" is a fact nobody can act on. The page has to say that no
    alarm will be raised, because every other thing on it looks fine."""
    from components.diagnostics_view import _health_card

    card = _health_card({"healthy": False, "workers": {"alert_monitor": False,
                                                       "auto_provisioner": True},
                         "workers_down": ["alert_monitor"]})
    text = str(card)
    assert "Alerting has stopped" in text
    assert "no alarm will be raised" in text
    assert "Restart the hub" in text


def test_diagnostics_says_nothing_extra_when_the_workers_are_fine():
    from components.diagnostics_view import _health_card

    text = str(_health_card({"healthy": True,
                             "workers": {"alert_monitor": True},
                             "workers_down": []}))
    assert "Alerting has stopped" not in text
    assert "1 of 1 running" in text

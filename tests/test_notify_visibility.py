"""An undelivered alert must not be indistinguishable from a delivered one.

Alerting is the product's promise, so a notification that never reaches anyone
is its worst failure -- and the worst version of that is a SILENT one. The
dashboard still shows the breach and the event log still records it, so an
operator has every reason to believe they were told.

Two distinct loss paths, counted separately because they mean different things:
a channel failure (SMTP down, webhook 500, bad credentials) and back-pressure
(the dispatch queue filling because sends are slower than events arrive).

The subtle one is the channel failure: ``Notifier.dispatch`` reports a dead
channel by RETURNING ``ok=False``, not by raising -- send_email/send_webhook
catch their own exceptions -- so a bare ``try/except`` around it sees a clean
run and counts nothing.
"""
import queue

import pytest

from alert_monitor import AlertMonitor
from core.applog import HEALTH


class _DeadChannels:
    """What a dead SMTP server actually looks like: no exception, ok=False."""

    def dispatch(self, ev):
        return [("email", False, "Connection refused"),
                ("webhook", False, "HTTP 500")]


class _WorkingChannel:
    def dispatch(self, ev):
        return [("email", True, "sent")]


class _RaisingChannel:
    def dispatch(self, ev):
        raise RuntimeError("unexpected channel explosion")


class _AliveThread:
    def is_alive(self):
        return True


@pytest.fixture()
def counters():
    """Deltas, not absolutes -- HEALTH is a process-wide singleton."""
    def _snap():
        s = HEALTH.snapshot()
        return s["notify_failures"], s["notify_dropped"]
    return _snap


def _monitor(notifier):
    return AlertMonitor(db=None, cfg={}, notifier=notifier)


def test_failed_channels_are_counted_though_dispatch_never_raises(counters):
    f0, _ = counters()
    _monitor(_DeadChannels())._send({"probe_id": "Setpoint-TEST", "kind": "high"})
    f1, _ = counters()
    assert f1 - f0 == 2          # one per dead channel


def test_a_successful_send_counts_nothing(counters):
    f0, d0 = counters()
    _monitor(_WorkingChannel())._send({"probe_id": "Setpoint-TEST", "kind": "high"})
    assert counters() == (f0, d0)


def test_an_exploding_channel_is_counted_and_does_not_propagate(counters):
    """The dispatch worker must survive; a dead channel cannot kill alerting."""
    f0, _ = counters()
    _monitor(_RaisingChannel())._send({"probe_id": "Setpoint-TEST", "kind": "high"})
    assert counters()[0] - f0 == 1


def test_queue_full_counts_a_drop_separately_from_a_failure(counters):
    f0, d0 = counters()
    m = _monitor(_WorkingChannel())
    m._notify_q = queue.Queue(maxsize=1)
    m._notify_q.put({})                      # fill it
    m._notify_thread = _AliveThread()        # force the async path
    m._dispatch({"probe_id": "Setpoint-TEST", "kind": "high"})
    f1, d1 = counters()
    assert d1 - d0 == 1
    assert f1 == f0                          # a drop is not a channel failure


def test_failure_timestamp_is_recorded():
    _monitor(_DeadChannels())._send({"probe_id": "Setpoint-TEST", "kind": "high"})
    assert HEALTH.snapshot()["last_notify_failure_age_sec"] is not None


def test_health_snapshot_exposes_the_counters():
    snap = HEALTH.snapshot()
    assert {"notify_failures", "notify_dropped",
            "last_notify_failure_age_sec"} <= set(snap)

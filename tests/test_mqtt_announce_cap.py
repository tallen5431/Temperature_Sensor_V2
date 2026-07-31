"""The Home Assistant discovery announce set must be bounded.

A probe id arrives as an X-Probe-ID header on the open-by-default ingest API and
sanitizes to 32 chars of ``[A-Za-z0-9_-]``, so its cardinality is effectively
unbounded -- the same exposure ``probe_discovery._MAX_PROBES`` exists to bound.
Here the consequence is worse than memory: each novel id publishes a discovery
entity with ``retain=True``, and a retained message outlives the hub, a broker
restart, and the flood itself, so an id flood permanently litters the user's
Home Assistant with phantom entities they have to hand-clear.
"""
import pytest

from core.mqtt_publish import MqttPublisher, _MAX_ANNOUNCED


class _CountingClient:
    """Records publishes, split by whether they are retained (discovery)."""

    def __init__(self):
        self.retained = []
        self.states = []

    def publish(self, topic, payload, retain=False):
        (self.retained if retain else self.states).append(topic)


@pytest.fixture()
def pub():
    p = MqttPublisher()
    client = _CountingClient()
    p._client = client
    p._enabled = True
    p._discovery_enabled = True
    return p, client


def test_normal_fleet_announces_once_per_probe_and_metric(pub):
    """The cap must not disturb ordinary use."""
    p, client = pub
    for i in range(4):
        for _ in range(10):          # repeated readings, one announce each
            p.publish_reading(f"Setpoint-{i}", 20.0, humidity=50.0, vpd=1.2)
    assert len(client.retained) == 12    # 4 probes x 3 metrics
    assert len(client.states) == 40      # every reading still published


def test_id_flood_cannot_publish_unbounded_retained_messages(pub):
    p, client = pub
    for i in range(_MAX_ANNOUNCED + 500):
        p.publish_reading(f"Spoofed-{i:06d}", 21.0)
    assert len(client.retained) == _MAX_ANNOUNCED
    assert len(p._announced) == _MAX_ANNOUNCED


def test_readings_keep_flowing_past_the_cap(pub):
    """Capping discovery must never cost a reading -- data is the product."""
    p, client = pub
    total = _MAX_ANNOUNCED + 500
    for i in range(total):
        p.publish_reading(f"Spoofed-{i:06d}", 21.0)
    assert len(client.states) == total


def test_cap_warning_is_logged_once_not_per_reading(pub, caplog):
    p, _ = pub
    with caplog.at_level("WARNING"):
        for i in range(_MAX_ANNOUNCED + 50):
            p.publish_reading(f"Spoofed-{i:06d}", 21.0)
    assert sum("capped" in r.message for r in caplog.records) == 1


def test_an_already_announced_probe_is_not_re_announced_past_the_cap(pub):
    """Eviction would turn a bounded set into an unbounded retained stream."""
    p, client = pub
    p.publish_reading("Setpoint-REAL", 20.0)
    assert len(client.retained) == 1
    for i in range(_MAX_ANNOUNCED + 100):
        p.publish_reading(f"Spoofed-{i:06d}", 21.0)
    before = len(client.retained)
    for _ in range(20):
        p.publish_reading("Setpoint-REAL", 20.5)
    assert len(client.retained) == before      # no re-announce churn


def test_empty_probe_id_is_never_announced(pub):
    p, client = pub
    p.publish_reading("", 20.0)
    assert client.retained == []
    assert client.states == []

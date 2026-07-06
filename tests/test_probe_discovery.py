import pytest

zeroconf = pytest.importorskip("zeroconf")
from zeroconf import ServiceStateChange  # noqa: E402

from probe_discovery import ProbeDiscovery, ProbeInfo, SERVICE_TYPE  # noqa: E402


@pytest.fixture
def discovery():
    try:
        d = ProbeDiscovery()
    except OSError:
        pytest.skip("Zeroconf could not bind a socket in this environment")
    yield d
    try:
        d.stop()
    except Exception:
        pass


def test_removed_uses_exact_match_not_prefix(discovery):
    # Two probes where one name is a prefix of the other's. Removing the longer
    # one must NOT delete the shorter one (the old startswith bug did).
    discovery._probes["hostA"] = ProbeInfo(
        name="ThermaProbe-12", host="hostA", ip="1", port=80,
        service_name="ThermaProbe-12." + SERVICE_TYPE, source="mdns")
    discovery._probes["hostB"] = ProbeInfo(
        name="ThermaProbe-1", host="hostB", ip="2", port=80,
        service_name="ThermaProbe-1." + SERVICE_TYPE, source="mdns")

    discovery._handle(None, SERVICE_TYPE, "ThermaProbe-12." + SERVICE_TYPE, ServiceStateChange.Removed)

    assert "hostA" not in discovery._probes
    assert "hostB" in discovery._probes  # survivor


def test_register_seen_adds_posting_only_probe(discovery):
    discovery.register_seen("ThermaProbe-9A3F2C", ip="192.168.1.50")
    probes = discovery.list_probes()
    assert "ThermaProbe-9A3F2C" in probes
    assert probes["ThermaProbe-9A3F2C"].ip == "192.168.1.50"


def test_register_seen_updates_existing_mdns_probe(discovery):
    discovery._probes["hostA"] = ProbeInfo(
        name="ThermaProbe-9A3F2C", host="hostA", ip="", port=80,
        properties={"id": "ThermaProbe-9A3F2C"}, service_name="x", source="mdns")
    discovery.register_seen("ThermaProbe-9A3F2C", ip="10.0.0.9")
    # Should update the existing entry, not create a duplicate keyed by id.
    assert "ThermaProbe-9A3F2C" not in discovery._probes  # no duplicate key
    assert discovery._probes["hostA"].ip == "10.0.0.9"

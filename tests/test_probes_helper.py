"""``core.probes`` — the one rule for reading a probe record.

The registry holds ``ProbeInfo`` dataclasses *and* plain dicts (ingest-seeded
entries, older persisted state, test fakes), so five surfaces used to each carry
their own attribute-or-key dance. These tests pin the shared rule against both
shapes, because the last time a copy of it drifted, ``setpoint_probes_total``
silently equalled ``setpoint_probes_online`` on every scrape.
"""
import pytest

from core.probes import (
    discovered_probe_ids,
    discovered_probes,
    normalize_probe,
    probe_address,
    probe_id,
    probe_label,
    probe_last_seen,
    probe_port,
    probe_properties,
)
from probe_discovery import ProbeInfo


def _info(**over):
    base = dict(name="Setpoint-9A3F", host="probe.local.", ip="10.0.0.7", port=80,
                properties={"id": "Setpoint-9A3F"}, last_seen=1000.0)
    base.update(over)
    return ProbeInfo(**base)


class _Finder:
    def __init__(self, probes):
        self._p = probes

    def list_probes(self):
        return self._p


# --- the id ------------------------------------------------------------------

def test_id_comes_from_properties_on_both_shapes():
    assert probe_id(_info()) == "Setpoint-9A3F"
    assert probe_id({"properties": {"id": "Setpoint-DICT"}}) == "Setpoint-DICT"


def test_id_falls_back_to_the_flat_keys_a_dict_entry_may_carry():
    assert probe_id({"probe_id": "P1"}) == "P1"
    assert probe_id({"id": "P2"}) == "P2"


def test_id_never_falls_back_to_the_display_name():
    """A probe whose real id is unknown must not be provisioned or configured
    under its label — the provisioner and the Devices editor both key per-probe
    settings on this, and a name is not stable."""
    assert probe_id(_info(properties={})) == ""
    assert probe_id({"name": "Kitchen fridge"}) == ""


def test_label_prefers_the_name_then_degrades_to_the_id():
    assert probe_label(_info(name="Walk-in")) == "Walk-in"
    assert probe_label({"properties": {"name": "Freezer"}}) == "Freezer"
    assert probe_label({"properties": {"id": "Setpoint-B2C1"}}) == "Setpoint-B2C1"
    assert probe_label({}) == ""


# --- the other fields --------------------------------------------------------

def test_last_seen_is_a_float_or_none_never_a_string():
    assert probe_last_seen(_info(last_seen=12.5)) == 12.5
    assert probe_last_seen({"last_seen": 7}) == 7.0
    assert probe_last_seen({"last_seen": "recently"}) is None
    assert probe_last_seen({}) is None


def test_address_prefers_the_ip_and_falls_back_to_the_mdns_host():
    assert probe_address(_info()) == "10.0.0.7"
    assert probe_address(_info(ip="")) == "probe.local."
    assert probe_address({}) == ""


@pytest.mark.parametrize("value,expected", [
    (8080, 8080), ("8080", 8080), (None, 80), ("", 80), ("nope", 80),
])
def test_port_survives_anything_a_hand_edited_entry_can_hold(value, expected):
    assert probe_port({"port": value}) == expected


def test_normalize_covers_every_field_at_once():
    assert normalize_probe(_info()) == {
        "probe_id": "Setpoint-9A3F", "name": "Setpoint-9A3F",
        "host": "probe.local.", "ip": "10.0.0.7", "port": 80,
        "last_seen": 1000.0, "properties": {"id": "Setpoint-9A3F"},
    }


@pytest.mark.parametrize("value", ["not-a-dict", None, 42, []])
def test_malformed_properties_degrade_instead_of_raising(value):
    """A probe record can come from persisted state or a test fake; a properties
    value that is not a dict must not crash a dashboard callback."""
    assert probe_properties({"properties": value}) == {}
    assert probe_id({"properties": value, "probe_id": "P1"}) == "P1"


# --- reading the whole registry ----------------------------------------------

def test_discovery_failures_degrade_to_an_empty_list():
    class _Broken:
        def list_probes(self):
            raise RuntimeError("no multicast interface")

    assert discovered_probes(_Broken()) == []
    assert discovered_probes(None) == []
    assert discovered_probe_ids(None) == set()


def test_ids_count_a_probe_that_never_advertised_one():
    """setpoint_probes_total exists to be compared against the reporting count,
    so an unidentified probe still has to be counted or the difference the
    metric is watched for is understated."""
    ids = discovered_probe_ids(_Finder({
        "a": _info(properties={"id": "Setpoint-9A3F"}),
        "b": _info(name="Setpoint-NONAME", properties={}),
    }))
    assert ids == {"Setpoint-9A3F", "Setpoint-NONAME"}

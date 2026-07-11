"""Tests for probe discovery de-duplication (probe_discovery.dedupe_probes_by_ip).

A single physical probe can briefly appear under two identities — the mDNS
record advertised at boot (before the DS18B20 ROM is read) and the id it later
POSTs to /api/ingest.  Both share one LAN IP, so the listing must collapse them
to a single, freshest entry; otherwise the Devices page shows one probe twice.
"""
from probe_discovery import ProbeInfo, dedupe_probes_by_ip


def _probe(name, ip, last_seen, probe_id=None):
    return ProbeInfo(
        name=name,
        host=name,
        ip=ip,
        port=80,
        properties={"id": probe_id} if probe_id else {},
        last_seen=last_seen,
    )


def test_same_ip_collapses_to_freshest():
    # The exact field scenario: one mDNS card (stale) + one ingest card (fresh).
    probes = {
        "TempSensor-8C58": _probe("TempSensor-8C58", "192.168.1.219", 1000.0),
        "TempProbe-0002":  _probe("TempProbe-0002",  "192.168.1.219", 3000.0),
    }
    out = dedupe_probes_by_ip(probes)
    assert len(out) == 1
    survivor = next(iter(out.values()))
    assert survivor.name == "TempProbe-0002"   # the most recently-seen wins


def test_freshest_wins_regardless_of_order():
    # Same IP but the fresh entry is listed first — order must not matter.
    probes = {
        "TempProbe-0002":  _probe("TempProbe-0002",  "10.0.0.5", 5000.0),
        "TempSensor-8C58": _probe("TempSensor-8C58", "10.0.0.5", 1000.0),
    }
    out = dedupe_probes_by_ip(probes)
    assert len(out) == 1
    assert next(iter(out.values())).name == "TempProbe-0002"


def test_distinct_ips_are_preserved():
    probes = {
        "a": _probe("a", "192.168.1.10", 1000.0),
        "b": _probe("b", "192.168.1.11", 1000.0),
    }
    out = dedupe_probes_by_ip(probes)
    assert len(out) == 2


def test_unknown_ip_entries_pass_through():
    # Entries with no resolved IP must never be merged together.
    probes = {
        "a": _probe("a", "", 1000.0),
        "b": _probe("b", "", 2000.0),
        "c": _probe("c", "192.168.1.50", 1500.0),
    }
    out = dedupe_probes_by_ip(probes)
    assert len(out) == 3


def test_surviving_entry_keeps_real_key():
    # The provisioner addresses probes by their dict key, so it must survive.
    probes = {
        "stale-key": _probe("TempSensor-8C58", "192.168.1.219", 1000.0),
        "fresh-key": _probe("TempProbe-0002",  "192.168.1.219", 3000.0),
    }
    out = dedupe_probes_by_ip(probes)
    assert list(out.keys()) == ["fresh-key"]


def test_handles_dict_style_probes():
    # Discovery may hold dict-shaped entries (minimal ingest records); support both.
    probes = {
        "TempSensor-8C58": {"name": "TempSensor-8C58", "ip": "192.168.1.219", "last_seen": 1000.0},
        "TempProbe-0002":  {"name": "TempProbe-0002",  "ip": "192.168.1.219", "last_seen": 3000.0},
    }
    out = dedupe_probes_by_ip(probes)
    assert len(out) == 1
    assert next(iter(out.values()))["name"] == "TempProbe-0002"


def test_empty_input():
    assert dedupe_probes_by_ip({}) == {}

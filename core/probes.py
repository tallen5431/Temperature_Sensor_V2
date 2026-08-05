"""One definition of how to read a probe record from the discovery registry.

:class:`probe_discovery.ProbeDiscovery` hands out :class:`ProbeInfo` dataclasses,
but the same map also holds plain dicts — entries seeded from ingest, older
persisted state, and every test fake. So each consumer has to cope with both
shapes, and each one used to do it by hand: ``app.py``'s ``/metrics``, the API's
``/api/probes``, the Diagnostics snapshot, the Devices grid and the
auto-provisioner all carried their own attribute-or-key dance.

Five copies of one rule drift, and this one did. ``/metrics`` reached for
``probe_id`` — a field ``ProbeInfo`` does not have, because the id lives in
``.properties["id"]`` — so its "discovered" set was permanently empty,
``setpoint_probes_total`` always equalled ``setpoint_probes_online``, and the one
Grafana alert those two gauges exist to support (``total - online > 0``, i.e. "a
probe I know about has stopped reporting") was silently disarmed. The test that
was meant to cover it re-implemented the extraction in the test file, so it
passed against its own copy while the real one was broken.

Everything here is pure and free of Dash/Flask/DB imports, so it can be tested
directly and used from any layer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _get(probe: Any, key: str, default=None):
    """Read ``key`` from a probe record that may be a dict or an object."""
    if isinstance(probe, dict):
        return probe.get(key, default)
    return getattr(probe, key, default)


def probe_properties(probe: Any) -> Dict[str, Any]:
    """The mDNS TXT properties dict, or ``{}`` when absent/malformed."""
    props = _get(probe, "properties") or {}
    return props if isinstance(props, dict) else {}


def probe_id(probe: Any) -> str:
    """The probe's stable id, or ``""`` when it has none.

    ``properties["id"]`` first — that is where the firmware puts the DS18B20 ROM
    id and the only value that survives a rename — then the flat ``probe_id`` /
    ``id`` keys a dict-shaped entry may carry. Deliberately does NOT fall back to
    the display name: callers that manage a probe (provisioning, per-probe
    settings) must not act on a probe whose real id is unknown. Callers that only
    need to count or label one use ``probe_id(p) or probe_label(p)``.
    """
    props = probe_properties(probe)
    for value in (props.get("id"), _get(probe, "probe_id"), _get(probe, "id")):
        if value:
            return str(value)
    return ""


def probe_label(probe: Any) -> str:
    """A human-facing name for the probe, or ``""`` when nothing is known."""
    props = probe_properties(probe)
    for value in (_get(probe, "name"), props.get("name"), props.get("id"),
                  _get(probe, "id")):
        if value:
            return str(value)
    return ""


def probe_last_seen(probe: Any) -> Optional[float]:
    """Epoch of the last sighting, or ``None`` when unknown/unparseable."""
    value = _get(probe, "last_seen")
    return float(value) if isinstance(value, (int, float)) else None


def probe_address(probe: Any) -> str:
    """The best address to reach the probe on: its IP, else its mDNS hostname."""
    return str(_get(probe, "ip") or _get(probe, "host") or "")


def probe_port(probe: Any, default: int = 80) -> int:
    try:
        return int(_get(probe, "port") or default)
    except (TypeError, ValueError):
        return default


def normalize_probe(probe: Any) -> Dict[str, Any]:
    """One probe record as a plain dict with every field resolved.

    Keys: ``probe_id`` (may be ``""``), ``name``, ``host``, ``ip``, ``port``,
    ``last_seen``, ``properties``.
    """
    return {
        "probe_id": probe_id(probe),
        "name": probe_label(probe),
        "host": _get(probe, "host"),
        "ip": _get(probe, "ip"),
        "port": probe_port(probe),
        "last_seen": probe_last_seen(probe),
        "properties": probe_properties(probe),
    }


def discovered_probes(discovery: Any) -> List[Dict[str, Any]]:
    """Every mDNS-discovered probe, normalised. Never raises.

    Discovery is optional (it degrades to an inert object when no multicast
    interface exists), so a caller asking "what probes are there?" gets an empty
    list rather than an exception it would have to guard at every call site.
    """
    if discovery is None:
        return []
    try:
        values = (discovery.list_probes() or {}).values()
    except Exception:  # noqa: BLE001 - discovery is best-effort everywhere
        return []
    return [normalize_probe(p) for p in values]


def discovered_probe_ids(discovery: Any) -> set:
    """Ids of every discovered probe, falling back to the display name.

    Used where a probe must be *counted* even if it never advertised an id —
    ``setpoint_probes_total`` exists to be compared against the reporting count,
    so dropping an unidentified probe here would understate the difference the
    metric is watched for.
    """
    return {p["probe_id"] or p["name"] for p in discovered_probes(discovery)
            if p["probe_id"] or p["name"]}

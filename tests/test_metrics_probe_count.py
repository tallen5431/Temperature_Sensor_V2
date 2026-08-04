"""`setpoint_probes_total` must count mDNS-discovered probes, not just reporters.

The two gauges exist to express one thing between them: "a probe I know about
has stopped reporting", i.e. ``probes_total - probes_online > 0``. That is the
obvious Grafana alert for a silent freezer sensor.

app.py read the discovered id with ``getattr(p, "probe_id", None)``, but the
registry stores ``ProbeInfo`` dataclasses, which have no ``probe_id`` field --
the id lives in ``.properties["id"]``. So the expression returned None for every
probe, the discovered set was always empty, and ``probes_total`` was identical to
``probes_online`` on every scrape, permanently disarming that alert. Nothing
caught it because test_metrics.py calls ``render_prometheus`` directly with a
literal count and never exercises the extraction.

These tests pin the extraction itself, against the real ProbeInfo class — and
against the REAL function. They used to re-implement it here, which is how a copy
in the test file could keep passing while the copy in app.py was broken; the rule
now lives once, in ``core.probes``, and both the route and these tests call it.
"""
from core.probes import discovered_probe_ids
from probe_discovery import ProbeInfo


class _Finder:
    def __init__(self, probes):
        self._p = probes

    def list_probes(self):
        return self._p


def _extract(probes):
    """The id extraction as app.py's /metrics route performs it."""
    return discovered_probe_ids(_Finder(probes))


def _probe(name, pid=None):
    return ProbeInfo(name=name, host=f"{name}.local", ip="10.0.0.1", port=80,
                     properties=({"id": pid} if pid else {}))


def test_probeinfo_really_has_no_probe_id_attribute():
    """Pins the premise: if this ever changes, the extraction can be simplified."""
    assert not hasattr(_probe("Setpoint-9A3F", "Setpoint-9A3F"), "probe_id")


def test_id_is_read_from_properties():
    assert _extract({"a": _probe("nm", "Setpoint-9A3F")}) == {"Setpoint-9A3F"}


def test_falls_back_to_name_when_properties_carry_no_id():
    assert _extract({"a": _probe("Setpoint-B2C1")}) == {"Setpoint-B2C1"}


def test_dict_shaped_entries_still_work():
    assert _extract({"a": {"properties": {"id": "Setpoint-DICT"}}}) == {"Setpoint-DICT"}
    assert _extract({"a": {"name": "Setpoint-NAME"}}) == {"Setpoint-NAME"}


def test_empty_and_missing_are_skipped():
    assert _extract({}) == set()
    assert _extract({"a": {"properties": {}}}) == set()


def test_total_can_exceed_online_so_the_silent_probe_alert_can_fire():
    """The whole point: a discovered-but-not-reporting probe must show up."""
    discovered = _extract({
        "a": _probe("nm1", "Setpoint-9A3F"),
        "b": _probe("nm2", "Setpoint-B2C1"),
    })
    reporting = {"Setpoint-9A3F"}          # only one is actually ingesting
    total, online = len(discovered | reporting), len(reporting)
    assert total == 2 and online == 1
    assert total - online == 1


def test_a_reporting_probe_absent_from_mdns_is_still_counted():
    """The union must not lose a probe that ingests without an mDNS record."""
    discovered = _extract({"a": _probe("nm", "Setpoint-9A3F")})
    reporting = {"Setpoint-9A3F", "Setpoint-ONLY-INGEST"}
    assert len(discovered | reporting) == 2

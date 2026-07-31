"""Per-probe scalar maps must be coerced, not silently ignored.

``alert_thresholds`` already coerces its inner values because an uncoerced one
would raise TypeError and kill alerting. Its siblings -- ``probe_intervals``,
``probe_resolutions`` and ``calibration_offsets`` -- have the opposite problem:
every consumer defends itself (``desired_probe_config`` and
``_calibration_offset`` both swallow a bad value and fall back), so nothing
crashes and the misconfiguration is invisible.

That is worse than a crash, because the Devices card renders the RAW config
value. Hand-edit an interval to "30s" and the card reads "Interval: 30s s"
while the probe keeps running the global interval. Coercing at load makes the
stored config, the value in effect, and the value displayed agree.
"""
import pytest

from core.config_schema import normalize_config
from provisioning import desired_probe_config


def _norm(**cfg):
    return normalize_config(dict(cfg))


def test_unparseable_interval_is_dropped_not_left_to_mislead():
    out, warns = _norm(probe_intervals={"A": "30s"})
    assert "A" not in out["probe_intervals"]
    assert any("probe_intervals['A']" in w for w in warns)


def test_a_dropped_override_falls_back_to_the_global_interval():
    """The card can no longer show a per-probe value the probe isn't running."""
    out, _ = _norm(interval_sec=5, probe_intervals={"A": "30s"})
    assert desired_probe_config(out, "A")["interval_ms"] == 5000


def test_quoted_numbers_are_accepted_and_applied():
    out, _ = _norm(interval_sec=5, probe_intervals={"B": "1800"})
    assert out["probe_intervals"]["B"] == 1800
    assert desired_probe_config(out, "B")["interval_ms"] == 1800000


def test_quoted_number_does_not_warn():
    """Only a value change warrants a warning, not a tightened type."""
    _, warns = _norm(probe_intervals={"B": "1800"})
    assert not any("probe_intervals['B']" in w for w in warns)


def test_below_minimum_interval_is_clamped_and_warned():
    out, warns = _norm(probe_intervals={"C": 0.1})
    assert out["probe_intervals"]["C"] == 0.5
    assert any("adjusted" in w and "probe_intervals['C']" in w for w in warns)


def test_resolution_is_coerced_to_int_and_bad_values_dropped():
    out, _ = _norm(probe_resolutions={"A": "12", "B": "high"})
    assert out["probe_resolutions"] == {"A": 12}
    assert desired_probe_config(out, "A")["resolution_bits"] == 12


def test_calibration_offset_keeps_negatives():
    """A calibration offset is a delta -- negative is the common case."""
    out, _ = _norm(calibration_offsets={"A": "-0.5", "B": "half a degree", "C": 0.25})
    assert out["calibration_offsets"] == {"A": -0.5, "C": 0.25}


def test_none_entries_are_removed():
    out, _ = _norm(probe_intervals={"A": None})
    assert out["probe_intervals"] == {}


@pytest.mark.parametrize("key", ["probe_intervals", "probe_resolutions",
                                 "calibration_offsets"])
def test_a_non_dict_table_still_resets_cleanly(key):
    out, warns = _norm(**{key: "not a dict"})
    assert out[key] == {}
    assert any(key in w for w in warns)

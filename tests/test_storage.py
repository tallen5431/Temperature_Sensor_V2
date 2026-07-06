import csv

import pytest

from core.storage import (
    normalize_payload,
    append_row,
    apply_calibration,
    sanitize_probe_id,
    _escape_csv_field,
    COLUMNS,
    MIN_TEMP_C,
    MAX_TEMP_C,
)


def test_celsius_passthrough():
    ts, c, f = normalize_payload({"temperature_c": 25})
    assert c == 25.0
    assert f == pytest.approx(77.0)


def test_fahrenheit_derives_celsius():
    ts, c, f = normalize_payload({"temperature_f": 32})
    assert c == pytest.approx(0.0)
    assert f == 32.0


@pytest.mark.parametrize("key", ["temperature_c", "temp_c", "t_c", "c"])
def test_all_celsius_aliases(key):
    _, c, _ = normalize_payload({key: 10})
    assert c == 10.0


def test_zero_is_not_treated_as_missing():
    # 0 is falsy — the old `payload.get(k)` truthiness check would have skipped it.
    _, c, _ = normalize_payload({"temperature_c": 0})
    assert c == 0.0


def test_missing_temperature_raises():
    with pytest.raises(ValueError):
        normalize_payload({"humidity": 50})


def test_non_finite_rejected():
    with pytest.raises(ValueError):
        normalize_payload({"temperature_c": float("nan")})
    with pytest.raises(ValueError):
        normalize_payload({"temperature_c": float("inf")})


def test_out_of_range_rejected():
    with pytest.raises(ValueError):
        normalize_payload({"temperature_c": MAX_TEMP_C + 1})
    with pytest.raises(ValueError):
        normalize_payload({"temperature_c": MIN_TEMP_C - 1})
    # Sensor fault code 85.0 is inside range but -127 (disconnected) is not.
    with pytest.raises(ValueError):
        normalize_payload({"temperature_c": -127})


def test_append_row_always_four_columns(tmp_path):
    p = tmp_path / "log.csv"
    append_row(p, "2026-01-01T00:00:00", 21.0, 69.8, probe_id="ThermaProbe-9A3F2C")
    append_row(p, "2026-01-01T00:00:05", 22.0, 71.6, probe_id=None)  # no probe id
    with open(p, newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == COLUMNS
    # Every data row must have exactly 4 fields — no ragged rows.
    for r in rows[1:]:
        assert len(r) == 4
    assert rows[2][3] == ""  # missing probe_id becomes empty string, not absent


def test_formula_injection_escaped():
    assert _escape_csv_field("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert _escape_csv_field("+1") == "'+1"
    assert _escape_csv_field("normal") == "normal"


def test_append_row_escapes_probe_id(tmp_path):
    p = tmp_path / "log.csv"
    append_row(p, "2026-01-01T00:00:00", 21.0, 69.8, probe_id="=cmd()")
    with open(p, newline="") as f:
        rows = list(csv.reader(f))
    assert rows[1][3].startswith("'=")


def test_sanitize_probe_id():
    assert sanitize_probe_id("ThermaProbe-9A3F2C") == "ThermaProbe-9A3F2C"
    assert sanitize_probe_id("=evil()") == ""
    assert sanitize_probe_id("a" * 33) == ""
    assert sanitize_probe_id("") == ""


def test_apply_calibration():
    cal = {"ThermaProbe-1": {"offset_c": 1.5, "gain": 1.0}}
    assert apply_calibration(20.0, "ThermaProbe-1", cal) == pytest.approx(21.5)
    # No calibration entry → unchanged
    assert apply_calibration(20.0, "ThermaProbe-2", cal) == 20.0
    assert apply_calibration(20.0, "ThermaProbe-1", None) == 20.0

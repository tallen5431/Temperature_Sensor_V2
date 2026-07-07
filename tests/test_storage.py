import csv

import pytest

from core.storage import (
    normalize_payload,
    append_row,
    apply_calibration,
    sanitize_probe_id,
    extract_humidity,
    compute_vpd,
    _escape_csv_field,
    COLUMNS,
    MIN_TEMP_C,
    MAX_TEMP_C,
)

PID_COL = COLUMNS.index("probe_id")
HUM_COL = COLUMNS.index("humidity_pct")


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


def test_append_row_never_ragged(tmp_path):
    p = tmp_path / "log.csv"
    append_row(p, "2026-01-01T00:00:00", 21.0, 69.8, probe_id="ThermaProbe-9A3F2C")
    append_row(p, "2026-01-01T00:00:05", 22.0, 71.6, probe_id=None)  # no probe id / no humidity
    with open(p, newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == COLUMNS
    # Every data row must have exactly len(COLUMNS) fields — no ragged rows.
    for r in rows[1:]:
        assert len(r) == len(COLUMNS)
    assert rows[2][PID_COL] == ""   # missing probe_id -> empty string
    assert rows[2][HUM_COL] == ""   # missing humidity -> empty string


def test_append_row_writes_humidity_and_vpd(tmp_path):
    p = tmp_path / "log.csv"
    append_row(p, "2026-01-01T00:00:00", 25.0, 77.0, probe_id="P1", humidity_pct=60.0, vpd_kpa=1.27)
    with open(p, newline="") as f:
        rows = list(csv.reader(f))
    assert rows[1][HUM_COL] == "60.00"
    assert rows[1][COLUMNS.index("vpd_kpa")] == "1.270"


def test_formula_injection_escaped():
    assert _escape_csv_field("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert _escape_csv_field("+1") == "'+1"
    assert _escape_csv_field("normal") == "normal"


def test_append_row_escapes_probe_id(tmp_path):
    p = tmp_path / "log.csv"
    append_row(p, "2026-01-01T00:00:00", 21.0, 69.8, probe_id="=cmd()")
    with open(p, newline="") as f:
        rows = list(csv.reader(f))
    assert rows[1][PID_COL].startswith("'=")


def test_relative_probe_timestamp_is_replaced_with_server_time():
    # Firmware sends a relative marker ("uptime+123s") — the hub must stamp its
    # own ISO time instead of writing an unparseable timestamp.
    ts, _, _ = normalize_payload({"temperature_c": 20, "timestamp": "uptime+123s"})
    import datetime as _dt
    _dt.datetime.fromisoformat(ts)  # must parse — raises if it's the relative marker


def test_valid_iso_timestamp_is_preserved():
    ts, _, _ = normalize_payload({"temperature_c": 20, "timestamp": "2026-01-01T10:00:00"})
    assert ts == "2026-01-01T10:00:00"


def test_extract_humidity():
    assert extract_humidity({"humidity_pct": 55.2}) == 55.2
    assert extract_humidity({"rh": "48"}) == 48.0
    assert extract_humidity({"temperature_c": 20}) is None       # no humidity
    assert extract_humidity({"humidity": 150}) is None           # out of range
    assert extract_humidity({"humidity": "nope"}) is None        # unparseable


def test_compute_vpd():
    # At 25 C / 50% RH, air VPD ~ 1.58 kPa (Tetens).
    v = compute_vpd(25.0, 50.0)
    assert v == pytest.approx(1.58, abs=0.05)
    # 100% RH -> VPD 0 (saturated).
    assert compute_vpd(20.0, 100.0) == pytest.approx(0.0, abs=1e-9)
    # Leaf offset raises deficit vs air VPD.
    assert compute_vpd(25.0, 50.0, leaf_offset_c=2.0) < compute_vpd(25.0, 50.0)


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

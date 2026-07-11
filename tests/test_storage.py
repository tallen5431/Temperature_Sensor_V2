"""Tests for ingest normalisation and timezone handling (core.storage)."""
import datetime

import pytest

from core.storage import _to_local_naive, normalize_payload


def test_celsius_only_computes_fahrenheit():
    ts, c, f = normalize_payload({"temperature_c": 25.0})
    assert c == 25.0
    assert f == pytest.approx(77.0)


def test_fahrenheit_only_computes_celsius():
    ts, c, f = normalize_payload({"temperature_f": 32.0})
    assert c == pytest.approx(0.0)
    assert f == 32.0


def test_alias_keys_accepted():
    _, c, _ = normalize_payload({"t_c": 18.5})
    assert c == 18.5


def test_missing_temperature_raises():
    with pytest.raises(ValueError):
        normalize_payload({"probe_id": "x"})


def test_empty_string_temperature_is_ignored():
    # GET query params can arrive as empty strings; treat as "not provided".
    with pytest.raises(ValueError):
        normalize_payload({"temperature_c": "", "temperature_f": ""})


def test_naive_timestamp_passthrough():
    ts, _, _ = normalize_payload({"temperature_c": 1, "timestamp": "2026-06-04T12:00:00"})
    assert ts == "2026-06-04T12:00:00"


def test_utc_z_is_converted_to_local():
    # A UTC instant must be shifted to local wall-clock, not merely stripped.
    utc = datetime.datetime(2026, 6, 4, 12, 0, 0, tzinfo=datetime.timezone.utc)
    expected_local = utc.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    assert _to_local_naive("2026-06-04T12:00:00Z") == expected_local


def test_utc_offset_with_fractional_seconds_converted():
    # Regression: the old index-19 check skipped conversion when fractional
    # seconds pushed the offset past position 19, silently dropping the tz.
    got = _to_local_naive("2026-06-04T12:00:00.500+00:00")
    expected = (
        datetime.datetime(2026, 6, 4, 12, 0, 0, 500000, tzinfo=datetime.timezone.utc)
        .astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    )
    assert got == expected


def test_explicit_offset_converted_to_local():
    # +02:00 instant -> local
    got = _to_local_naive("2026-06-04T14:00:00+02:00")
    expected = (
        datetime.datetime(2026, 6, 4, 14, 0, 0,
                          tzinfo=datetime.timezone(datetime.timedelta(hours=2)))
        .astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    )
    assert got == expected

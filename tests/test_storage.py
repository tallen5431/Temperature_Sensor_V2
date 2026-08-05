"""Tests for ingest normalisation and timezone handling (core.storage)."""
import datetime

import pytest

from core.storage import _to_local_naive, compute_vpd, extract_battery, normalize_payload


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
    # The millisecond precision is now preserved (high-rate logging).
    got = _to_local_naive("2026-06-04T12:00:00.500+00:00")
    expected = (
        datetime.datetime(2026, 6, 4, 12, 0, 0, 500000, tzinfo=datetime.timezone.utc)
        .astimezone().replace(tzinfo=None).isoformat(timespec="milliseconds")
    )
    assert got == expected


def test_subsecond_timestamp_preserved():
    # High-rate logging (0.5 s while a freezer door is open) needs millisecond
    # precision so two readings inside the same second stay distinguishable.
    ts, _, _ = normalize_payload({"temperature_c": -22.5,
                                  "timestamp": "2026-07-21T00:42:04.500Z"})
    assert ts.endswith(".500")  # ms retained after the tz->local conversion


def test_wholesecond_timestamp_has_no_spurious_millis():
    # A probe that only sends whole seconds must not gain a ".000" suffix.
    ts, _, _ = normalize_payload({"temperature_c": 20.0,
                                  "timestamp": "2026-07-21T00:42:04Z"})
    assert "." not in ts


def test_explicit_offset_converted_to_local():
    # +02:00 instant -> local
    got = _to_local_naive("2026-06-04T14:00:00+02:00")
    expected = (
        datetime.datetime(2026, 6, 4, 14, 0, 0,
                          tzinfo=datetime.timezone(datetime.timedelta(hours=2)))
        .astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    )
    assert got == expected


def test_future_timestamp_is_clamped_to_now():
    # A probe with a bad clock stamps a reading ~47 min in the future; the hub
    # must clamp it to ~now so the chart never draws into the future and the
    # bogus point can't become the "latest" reading.
    future = (datetime.datetime.now() + datetime.timedelta(minutes=47)).isoformat(timespec="seconds")
    ts, _, _ = normalize_payload({"temperature_c": 23.0, "timestamp": future})
    parsed = datetime.datetime.fromisoformat(ts)
    assert parsed <= datetime.datetime.now() + datetime.timedelta(seconds=125)


def test_recent_and_past_timestamps_are_preserved():
    # Small skew and legitimately-old (buffered) readings pass through unchanged.
    for offset_min in (-120, -5, 0):
        stamp = (datetime.datetime.now() + datetime.timedelta(minutes=offset_min)).isoformat(timespec="seconds")
        ts, _, _ = normalize_payload({"temperature_c": 20.0, "timestamp": stamp})
        assert ts == stamp


@pytest.mark.parametrize("bad", ["NaN", "inf", "-inf", "1e999"])
def test_non_finite_temperature_rejected(bad):
    # PROTOCOL.md §6 rule 2: non-finite values must be rejected, not stored.
    with pytest.raises(ValueError):
        normalize_payload({"temperature_c": bad})


@pytest.mark.parametrize("bad", [-127, -60.1, 150.1, 999, -300])
def test_out_of_range_temperature_rejected(bad):
    # §6 rule 3: the -60..150 C band rejects the -127 disconnected fault code and
    # any other out-of-band value. (The 85.0 power-on code is in-band and is
    # suppressed at the firmware per §8, not by this hub-side range check.)
    with pytest.raises(ValueError):
        normalize_payload({"temperature_c": bad})


def test_out_of_range_fahrenheit_rejected_when_both_units_sent():
    # Regression: a payload sending BOTH units could slip a garbage Fahrenheit
    # value past the Celsius-only range gate and poison the temperature_f column.
    # The F band (-76..302 F == -60..150 C) is now checked too.
    with pytest.raises(ValueError):
        normalize_payload({"temperature_c": 25.0, "temperature_f": 9999.0})
    # A consistent both-units payload still passes unharmed.
    _, c, f = normalize_payload({"temperature_c": 25.0, "temperature_f": 77.0})
    assert c == 25.0 and f == 77.0


@pytest.mark.parametrize("ok", [-60.0, -18.0, 0.0, 22.5, 85.0, 150.0])
def test_in_band_temperature_accepted(ok):
    _, c, _ = normalize_payload({"temperature_c": ok})
    assert c == ok


def test_extract_battery_pct_passthrough():
    # A probe reporting a percentage directly is used as-is (0..100 inclusive).
    assert extract_battery({"battery_pct": 87}) == 87.0
    assert extract_battery({"battery_pct": 0}) == 0.0
    assert extract_battery({"battery_pct": 100}) == 100.0
    assert extract_battery({"battery_pct": "42.5"}) == 42.5


def test_extract_battery_pct_out_of_band_rejected():
    assert extract_battery({"battery_pct": 100.1}) is None
    assert extract_battery({"battery_pct": -1}) is None


def test_extract_battery_volts_mapped_linearly():
    # Single-cell LiPo mapping: 3.0 V -> 0 %, 4.2 V -> 100 %, midpoint -> 50 %.
    assert extract_battery({"battery_v": 3.0}) == pytest.approx(0.0)
    assert extract_battery({"battery_v": 4.2}) == pytest.approx(100.0)
    assert extract_battery({"battery_v": 3.6}) == pytest.approx(50.0)


def test_extract_battery_volts_clamped_inside_plausible_band():
    # A freshly charged cell can read slightly above 4.2 V and a deeply drained
    # one below 3.0 V; within the plausible cell band those clamp to 100/0.
    assert extract_battery({"battery_v": 4.35}) == 100.0
    assert extract_battery({"battery_v": 2.8}) == 0.0


@pytest.mark.parametrize("payload", [
    {},                            # no battery keys at all (mains-powered probe)
    {"battery_pct": None},
    {"battery_pct": ""},
    {"battery_pct": "junk"},
    {"battery_pct": "nan"},
    {"battery_v": "inf"},
    {"battery_v": "junk"},
    {"battery_v": 12.0},           # not a single-cell voltage -> junk, not "full"
    {"battery_v": 0.0},            # dead-short reading -> junk, not "empty"
])
def test_extract_battery_junk_returns_none(payload):
    assert extract_battery(payload) is None


def test_compute_vpd_typical_and_extreme():
    # A normal grow-room point: 25 C / 60 %RH with a 2 C leaf offset ~ 0.91 kPa.
    assert compute_vpd(25.0, 60.0, 2.0) == pytest.approx(0.91, abs=0.05)
    # A cooler leaf (larger offset) lowers VPD vs plain air VPD (no offset).
    assert 0.0 < compute_vpd(25.0, 60.0, 2.0) < compute_vpd(25.0, 60.0, 0.0)
    # VPD is clamped non-negative and never divides by zero at extreme cold.
    assert compute_vpd(-250.0, 50.0) >= 0.0
    assert compute_vpd(100.0, 100.0) >= 0.0


# --- a reading with no usable id ------------------------------------------

def test_a_reading_with_no_usable_id_is_filed_somewhere_visible():
    """PROTOCOL.md §6.4: such a reading "is still logged, without an id". It was
    — under probe_id "", which every UI surface skips (`if not
    str(pid).strip(): continue`) and which `delete_probe("")` refuses to touch.
    The hub answered ok:true, counted the row in the readings total and wrote it
    to the CSV export with a blank column, and showed it nowhere, with no way to
    remove it. An integrator who forgot X-Probe-ID watched the counter climb and
    no probe ever appear."""
    from core.storage import UNIDENTIFIED_PROBE_ID, storage_probe_id
    for junk in (None, "", "   ", "!!!", "///", "\x00"):
        assert storage_probe_id(junk) == UNIDENTIFIED_PROBE_ID
    assert UNIDENTIFIED_PROBE_ID.strip(), \
        "the fallback id must be non-blank or the UI skips it exactly as before"
    from core.storage import sanitize_probe_id
    assert sanitize_probe_id(UNIDENTIFIED_PROBE_ID) == UNIDENTIFIED_PROBE_ID, \
        "the fallback must survive sanitising, or a round trip loses it again"


def test_a_real_id_is_untouched_by_the_fallback():
    from core.storage import storage_probe_id
    for pid in ("Setpoint-9A3F2C", "Walk-in", "freezer_2"):
        assert storage_probe_id(pid) == pid


def test_the_two_id_helpers_answer_different_questions():
    """sanitize_probe_id says "what is this id, cleaned up?" — and must still be
    able to answer "nothing", because callers use that to decide whether the
    request supplied one at all. storage_probe_id says where the row goes."""
    from core.storage import sanitize_probe_id, storage_probe_id
    assert sanitize_probe_id("!!!") == ""
    assert storage_probe_id("!!!") != ""

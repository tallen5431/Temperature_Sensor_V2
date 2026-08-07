"""A probe has two cadences, and the app only ever showed one of them.

``interval_ms`` is how often the probe TRANSMITS. ``sample_ms`` is how often it
READS. They are separate because the radio costs battery and the sensor does not:
a probe on a 15-minute report can read every minute with the radio off, buffer
what it sees, and transmit early only when a reading crosses a limit. That is the
threshold watch, and it is the reason a freezer thawing between reports is caught
in a minute rather than fifteen.

Two things hid it completely:

  * the one field on screen was labelled "Read Interval" and set the REPORTING
    interval, so the two were indistinguishable and the label named the wrong one;
  * the sample cadence (``probe_sample_sec``) had no control at all — it could
    only be changed by editing config.json by hand.

And the defaults switch it off: a 60 s check against a 5 s reporting interval is
not shorter, so ``sample_ms`` comes back 0. A hub could therefore have limits set,
the feature built, and nothing whatsoever happening, with no screen saying so.

These pin the hub half. The firmware half lives in tests/firmware/.
"""
import io

import pytest

from components.devices_panel import cadence_note
from components.settings_panel import (sample_cadence_note, settings_badges,
                                       watch_coverage)
from provisioning import reporting_plan


# --- the plan itself --------------------------------------------------------

def test_a_long_report_with_a_short_check_watches():
    cfg = {"interval_sec": 900, "probe_sample_sec": 60,
           "alert_thresholds": {"default": {"min": -20.0, "max": -15.0}}}
    plan = reporting_plan(cfg, "P")
    assert plan == {"report_sec": 900.0, "sample_sec": 60.0,
                    "watching": True, "has_limit": True}


def test_the_shipped_defaults_do_not_watch():
    """The exact configuration a hub arrives in: a 5 s reporting interval, the
    60 s default check. 60 is not shorter than 5, so nothing is armed — which is
    correct, and was invisible."""
    cfg = {"interval_sec": 5, "alert_thresholds": {"default": {"max": 4.0}}}
    plan = reporting_plan(cfg, "P")
    assert plan["watching"] is False
    assert plan["sample_sec"] == plan["report_sec"] == 5.0, \
        "with no watch the probe really does read and report on one beat"


def test_limits_are_what_arm_it():
    cfg = {"interval_sec": 900, "probe_sample_sec": 60}
    assert reporting_plan(cfg, "P") == {"report_sec": 900.0, "sample_sec": 900.0,
                                        "watching": False, "has_limit": False}


def test_a_per_probe_reporting_interval_is_what_counts():
    """The override, not the global, decides whether the check fits underneath."""
    cfg = {"interval_sec": 5, "probe_sample_sec": 60,
           "probe_intervals": {"Freezer": 900},
           "alert_thresholds": {"default": {"max": 4.0}}}
    assert reporting_plan(cfg, "Freezer")["watching"] is True
    assert reporting_plan(cfg, "Counter")["watching"] is False


def test_the_plan_agrees_with_what_the_probe_is_sent():
    """It is derived from desired_probe_config rather than re-reading config, so
    a screen cannot describe a probe differently from how it is configured."""
    from provisioning import desired_probe_config
    cfg = {"interval_sec": 600, "probe_sample_sec": 7,
           "alert_thresholds": {"P": {"min": 1.0}}}
    want = desired_probe_config(cfg, "P")
    plan = reporting_plan(cfg, "P")
    assert plan["report_sec"] * 1000 == want["interval_ms"]
    assert plan["sample_sec"] * 1000 == want["sample_ms"]


# --- the sentence on the Devices modal --------------------------------------

def test_the_modal_says_both_cadences_when_the_watch_is_on():
    text, css = cadence_note(reporting_plan(
        {"interval_sec": 900, "probe_sample_sec": 7,
         "alert_thresholds": {"default": {"max": 4.0}}}, "P"), 7)
    assert "15 minutes" in text and "7 s" in text
    assert "as soon as it is seen" in text
    assert "success" in css


def test_the_modal_explains_the_case_that_looks_broken():
    """Limits set, check set, and nothing happening because the check is not
    shorter than the reporting interval. Silent before; it is the default."""
    text, css = cadence_note(reporting_plan(
        {"interval_sec": 5, "probe_sample_sec": 60,
         "alert_thresholds": {"default": {"max": 4.0}}}, "P"), 60)
    assert "on the same beat, every 5 s" in text
    assert "longer than the between-report check" in text
    assert "1 minute" in text and "Settings → Probes" in text
    assert "warning" in css


def test_the_modal_says_what_to_do_when_no_limit_is_set():
    text, css = cadence_note(reporting_plan({"interval_sec": 900}, "P"), 60)
    assert "Set a min or max limit" in text
    assert "muted" in css


# --- who the Settings control actually reaches ------------------------------

_FLEET = {"interval_sec": 5,
          "probe_names": {"A": "Freezer", "B": "Counter"},
          "probe_intervals": {"A": 900},
          "alert_thresholds": {"A": {"min": -20.0}, "B": {"max": 8.0}}}


def test_coverage_names_the_probes_a_cadence_reaches():
    watched, known = watch_coverage(_FLEET, 60)
    assert watched == ["A"], "B reports every 5 s, so a 60 s check cannot fit under it"
    assert known == ["A", "B"]


def test_a_cadence_that_reaches_nobody_says_so():
    text, css = sample_cadence_note(_FLEET, 3600)
    assert "Reaches no probe right now" in text
    assert "1 hour" in text
    assert css == "text-warning"


def test_a_cadence_that_reaches_somebody_names_them():
    text, css = sample_cadence_note(_FLEET, 60)
    assert "1 of 2 probes" in text and "Freezer" in text
    assert css == "text-success"


def test_an_empty_hub_is_not_scolded():
    text, css = sample_cadence_note({"interval_sec": 5}, 60)
    assert "No probes are configured yet" in text
    assert css == "text-muted"


def test_the_probes_badge_reports_what_is_in_effect_not_what_is_stored():
    """Same rule as "On · no channel" for alerts: the badge is only useful if a
    setting that reaches nothing cannot look like one that works."""
    reaching = settings_badges({**_FLEET, "probe_sample_sec": 60})["probes"]
    assert reaching == ("Automatic · checks every 1 minute", "success")

    inert = settings_badges({**_FLEET, "probe_sample_sec": 3600})["probes"]
    assert inert == ("Automatic", "success"), \
        "a cadence no probe can use must not be advertised as running"


def test_a_config_object_works_as_well_as_a_dict(tmp_path):
    """settings_badges gets the live Config on the page and plain dicts in tests."""
    from core.config import Config
    cfg = Config(tmp_path / "config.json")
    cfg.update({**_FLEET, "probe_sample_sec": 60})
    assert watch_coverage(cfg, 60)[0] == ["A"]
    assert settings_badges(cfg)["probes"][0].endswith("checks every 1 minute")


# --- the control is reachable and saved -------------------------------------

def test_the_settings_page_actually_carries_the_control():
    """It had no UI at all, which is the whole bug — so its absence is the
    regression to guard, not its wiring."""
    from components.settings_panel import SettingsPanel
    from tests.test_callback_graph import _walk
    ids = {getattr(c, "id", None) for c in _walk(SettingsPanel)}
    assert "probe-sample-sec" in ids
    assert "probe-sample-note" in ids


def test_saving_it_normalises_and_persists(tmp_path):
    from core.config_schema import normalize_config
    clean, _warns = normalize_config({"probe_sample_sec": 7})
    assert clean["probe_sample_sec"] == 7
    # The firmware floor is 5 s and provisioning clamps to it, so a smaller value
    # is silently ignored at the point of use -- the form's min matches.
    cfg = {"interval_sec": 900, "probe_sample_sec": 1,
           "alert_thresholds": {"default": {"max": 4.0}}}
    assert reporting_plan(cfg, "P")["sample_sec"] == 5.0


# --- the CSV the button downloads -------------------------------------------

def _seed(db, probe="Setpoint-000092"):
    for i in range(3):
        db.append(f"2026-08-07T09:0{i}:00", 4.0 + i, 39.2 + i, probe,
                  epoch=1_770_000_000 + i)


def test_the_download_button_csv_carries_the_friendly_name(tmp_path):
    """The spreadsheet export has always had a `probe` column; the plain one did
    not, so the file most people download identified a fridge only as
    Setpoint-000092."""
    from core.db import Database
    db = Database(tmp_path / "t.db")
    _seed(db)
    buf = io.StringIO()
    db.export_csv(buf, name_map={"Setpoint-000092": "Refrigerator"})
    lines = buf.getvalue().splitlines()
    assert lines[0].split(",") == ["timestamp", "timestamp_utc", "temperature_c",
                                   "temperature_f", "probe_id", "probe",
                                   "humidity_pct", "vpd_kpa"]
    assert lines[1].split(",")[5] == "Refrigerator"


def test_a_hub_that_names_nothing_gets_the_file_it_always_got(tmp_path):
    """Conditional exactly like `site` and the humidity pair — an all-empty column
    on every existing export would be a shape change for nothing."""
    from core.db import Database
    db = Database(tmp_path / "t.db")
    _seed(db)
    for name_map in ({}, None, {"Setpoint-000092": "   "}):
        buf = io.StringIO()
        db.export_csv(buf, name_map=name_map)
        assert buf.getvalue().splitlines()[0] == (
            "timestamp,timestamp_utc,temperature_c,temperature_f,probe_id,"
            "humidity_pct,vpd_kpa"), f"name_map={name_map!r}"


def test_an_unnamed_probe_falls_back_to_its_id(tmp_path):
    """Blank would read as missing data rather than as "never named"."""
    from core.db import Database
    db = Database(tmp_path / "t.db")
    _seed(db, "A")
    _seed(db, "B")
    buf = io.StringIO()
    db.export_csv(buf, name_map={"A": "Freezer"})
    rows = [ln.split(",") for ln in buf.getvalue().splitlines()[1:]]
    assert {r[4]: r[5] for r in rows} == {"A": "Freezer", "B": "B"}


def test_both_exports_agree_about_the_name(tmp_path):
    """Two files off the same page disagreeing about what a probe is called is
    the confusion that started this."""
    from core.db import Database
    db = Database(tmp_path / "t.db")
    _seed(db)
    names = {"Setpoint-000092": "Refrigerator"}
    plain, friendly = io.StringIO(), io.StringIO()
    db.export_csv(plain, name_map=names)
    db.export_friendly_csv(friendly, name_map=names)
    plain_h = plain.getvalue().splitlines()[0].split(",")
    friendly_h = friendly.getvalue().splitlines()[0].split(",")
    assert "probe" in plain_h and "probe" in friendly_h
    got = plain.getvalue().splitlines()[1].split(",")[plain_h.index("probe")]
    want = friendly.getvalue().splitlines()[1].split(",")[friendly_h.index("probe")]
    assert got == want == "Refrigerator"


@pytest.mark.parametrize("route", ["", "?format=excel"])
def test_the_download_route_passes_the_names_through(tmp_path, route):
    """app.py already read cfg["probe_names"] for the spreadsheet export and did
    not hand them to the plain one — the names were there the whole time."""
    import re
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "app.py").read_text("utf-8")
    block = src[src.index("def download_csv("):src.index("def _safe_unlink(")]
    for call in re.finditer(r"db\.export_(?:csv|friendly_csv|xlsx)\(", block):
        tail = block[call.end():call.end() + 120]
        assert "name_map=names" in tail, f"{call.group(0)} does not pass the names"

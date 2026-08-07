"""Each probe gets its own between-report check cadence.

One number for the fleet forces the slowest acceptable cadence onto everything. A
walk-in cooler on mains can afford to look every 10 s; a battery probe in a remote
freezer, on a 15-minute report, should not — every extra wake is run time it does
not get back. So ``probe_samples`` overrides ``probe_sample_sec`` per probe, in
the same shape as ``probe_intervals`` and ``probe_resolutions``: a table keyed by
probe id, absent meaning inherit.

The rule the override does NOT change: the check still only applies to a probe
that has a limit set, and only when it is shorter than that probe's reporting
interval. Both are firmware conditions (``watchArmed()``), so a hub that sent a
cadence violating them would be configuring a probe to ignore it.
"""
import pytest

from components.settings_panel import sample_cadence_note, watch_coverage
from core.config_schema import normalize_config
from provisioning import desired_probe_config, reporting_plan

BASE = {"interval_sec": 900, "probe_sample_sec": 60,
        "alert_thresholds": {"default": {"min": 1.0, "max": 5.0}}}


# --- what reaches the probe -------------------------------------------------

def test_a_probe_can_check_more_often_than_the_fleet():
    cfg = {**BASE, "probe_samples": {"Walkin": 10}}
    assert desired_probe_config(cfg, "Walkin")["sample_ms"] == 10_000
    assert desired_probe_config(cfg, "Battery")["sample_ms"] == 60_000, \
        "a probe without an override still inherits"


def test_a_probe_can_check_less_often_than_the_fleet():
    """The battery case, which is the reason this is per-probe at all."""
    cfg = {**BASE, "probe_sample_sec": 10, "probe_samples": {"Battery": 300}}
    assert desired_probe_config(cfg, "Battery")["sample_ms"] == 300_000
    assert desired_probe_config(cfg, "Walkin")["sample_ms"] == 10_000


def test_an_override_still_has_to_fit_under_the_reporting_interval():
    """``watchArmed()`` requires sample < interval. Sending a cadence the probe
    would ignore is worse than sending none: the hub would show a watch the
    firmware is not running."""
    cfg = {**BASE, "probe_intervals": {"Fast": 30}, "probe_samples": {"Fast": 60}}
    assert desired_probe_config(cfg, "Fast")["sample_ms"] == 0
    assert reporting_plan(cfg, "Fast")["watching"] is False


def test_an_override_still_needs_a_limit():
    cfg = {"interval_sec": 900, "probe_sample_sec": 60,
           "probe_samples": {"Unwatched": 10}}
    assert desired_probe_config(cfg, "Unwatched")["sample_ms"] == 0


def test_an_override_is_clamped_to_the_firmware_floor():
    """WATCH_SAMPLE_MIN_MS is 5 s; below it the probe ignores the value, so a
    stored 2 would be a setting that reads as applied and is not."""
    cfg = {**BASE, "probe_samples": {"Eager": 1}}
    assert desired_probe_config(cfg, "Eager")["sample_ms"] == 5_000


@pytest.mark.parametrize("bad", ["ten", None, float("inf"), {}, [], float("nan")])
def test_a_bad_override_falls_back_instead_of_breaking_ingest(bad):
    """desired_probe_config runs on the LIVE ingest path — one bad value here
    would 500 every reading from every probe."""
    cfg = {**BASE, "probe_samples": {"P": bad}}
    assert desired_probe_config(cfg, "P")["sample_ms"] == 60_000, \
        "an unreadable override inherits; it must not disarm the watch or crash"


def test_the_plan_reports_the_override():
    cfg = {**BASE, "probe_samples": {"Walkin": 10}}
    assert reporting_plan(cfg, "Walkin") == {"report_sec": 900.0, "sample_sec": 10.0,
                                             "watching": True, "has_limit": True}


# --- config hygiene ---------------------------------------------------------

def test_the_table_is_normalised_like_the_other_per_probe_maps():
    clean, warns = normalize_config({"probe_samples": {"A": "30", "B": "nope",
                                                       "C": 1, "D": None}})
    assert clean["probe_samples"] == {"A": 30.0, "C": 5}, \
        "strings coerce, garbage is dropped, sub-floor is clamped, null removed"
    assert any("probe_samples['B']" in w for w in warns)
    assert any("probe_samples['C']" in w for w in warns), "a clamp must be reported"
    assert not any("probe_samples['A']" in w for w in warns), \
        "a type merely tightening is not worth a warning"


def test_a_non_object_table_is_reset_rather_than_crashing():
    clean, warns = normalize_config({"probe_samples": [1, 2, 3]})
    assert clean["probe_samples"] == {}
    assert any("probe_samples" in w for w in warns)


def test_removing_a_probe_takes_its_cadence_with_it():
    """An orphan entry silently re-applies if a probe with that id ever returns."""
    import pathlib
    import re
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "components" / "devices_panel.py").read_text("utf-8")
    block = re.search(r"for key in \((.*?)\):", src, re.S).group(1)
    for key in ("probe_names", "probe_intervals", "alert_thresholds",
                "calibration_offsets", "probe_resolutions", "probe_samples"):
        assert f"'{key}'" in block, f"remove-device does not clear {key}"


# --- what the pages say -----------------------------------------------------

_FLEET = {"interval_sec": 900, "probe_sample_sec": 60,
          "probe_names": {"A": "Walk-in", "B": "Chest freezer"},
          "alert_thresholds": {"A": {"max": 5.0}, "B": {"min": -22.0}},
          "probe_samples": {"A": 10}}


def test_the_settings_count_excludes_probes_on_their_own_cadence():
    """Otherwise typing a number no inheriting probe can use still reads as
    "reaches 2 probes", because a pinned probe was never affected by it."""
    watched, known = watch_coverage(_FLEET, 60)
    assert watched == ["B"] and known == ["A", "B"]


def test_settings_says_who_is_on_their_own_cadence():
    text, css = sample_cadence_note(_FLEET, 60)
    assert "1 of 2 probes: Chest freezer" in text
    assert "1 probe (Walk-in) uses their own cadence instead." in text
    assert css == "text-success"


def test_a_default_that_reaches_nobody_is_not_alarming_when_everyone_is_pinned():
    """Warning-yellow for "this does nothing" is right only when it means nobody
    is being checked. If every probe carries its own cadence, nothing is wrong."""
    pinned = {**_FLEET, "probe_samples": {"A": 10, "B": 20}}
    _text, css = sample_cadence_note(pinned, 3600)
    assert css == "text-muted"

    _text, css = sample_cadence_note({**_FLEET, "probe_samples": {}}, 3600)
    assert css == "text-warning", "nobody checked and nobody pinned IS the warning"


def test_the_modal_note_follows_the_field_not_the_saved_default():
    """The field is the override, so the sentence has to answer for what is typed
    -- otherwise a probe being given 10 s still reads as being on the fleet's 60."""
    from components.devices_panel import cadence_note
    plan = reporting_plan({**BASE, "probe_samples": {"P": 10}}, "P")
    text, css = cadence_note(plan, 10)
    assert "every 10 s in between" in text and "success" in css


# --- the control exists and is wired ----------------------------------------

def test_the_modal_carries_the_field():
    from components.devices_panel import DevicesLayout
    from tests.test_callback_graph import _walk
    ids = {getattr(c, "id", None) for c in _walk(DevicesLayout)}
    assert "edit-probe-sample-input" in ids


def test_the_save_path_stores_an_override_and_a_blank_removes_it(tmp_path):
    """Blank must DELETE rather than write the current global: a stored copy stops
    following a later fleet-wide change, which is the exact bug the reporting
    interval's "only when it differs" rule exists to avoid."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "components" / "devices_panel.py").read_text("utf-8")
    block = src[src.index("# --- Save the per-probe between-report check ---"):]
    block = block[:block.index("# --- Push the new settings")]
    assert "probe_samples.pop(stored_probe_id, None)" in block
    assert "probe_samples[stored_probe_id] = new_sample" in block
    assert "max(5.0, float(sample_value))" in block


def test_the_on_save_push_carries_the_watch(tmp_path):
    """It did not, so a check-cadence change was the one edit the immediate push
    could not deliver — it waited for the probe's next check-in."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "components" / "devices_panel.py").read_text("utf-8")
    call = src[src.index("ok = provision_probe("):]
    call = call[:call.index(")\n")]
    assert "watch=(" in call and "sample_ms" in call


def test_the_pushed_watch_equals_the_pulled_one(tmp_path):
    """Push and pull must configure a probe identically; both come from
    desired_probe_config, so this pins that they are read from one place."""
    from core.config import Config
    cfg = Config(tmp_path / "config.json")
    cfg.update({**BASE, "probe_samples": {"P": 10}})
    want = desired_probe_config(cfg, "P")
    pushed = (want.get("alert_min_c"), want.get("alert_max_c"), want.get("sample_ms", 0))
    assert pushed == (1.0, 5.0, 10_000)


def test_the_badge_counts_probes_on_their_own_cadence_too():
    """watch_coverage answers "who does THIS number reach", which is right for the
    Settings field and wrong for the badge: a hub where every probe carries its
    own cadence has zero coverage on the default and is checking all of them. The
    badge read "Automatic", as though nothing were running."""
    from components.settings_panel import settings_badges, watching_probes

    pinned = {**_FLEET, "probe_samples": {"A": 10, "B": 10}}
    assert watching_probes(pinned) == {"A": 10.0, "B": 10.0}
    assert settings_badges(pinned)["probes"] == ("Automatic · checks every 10 s",
                                                 "success")


def test_a_mixed_fleet_names_no_single_cadence():
    """Two probes on different cadences have no one number; printing either would
    be worse than printing none."""
    from components.settings_panel import settings_badges

    mixed = {**_FLEET, "probe_samples": {"A": 10, "B": 120}}
    assert settings_badges(mixed)["probes"] == ("Automatic · checks between reports",
                                                "success")


def test_the_badge_stays_quiet_when_nothing_is_checked():
    quiet = {**_FLEET, "probe_samples": {}, "probe_sample_sec": 3600}
    from components.settings_panel import settings_badges, watching_probes
    assert watching_probes(quiet) == {}
    assert settings_badges(quiet)["probes"] == ("Automatic", "success")

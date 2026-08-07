"""An excursion that begins and ends between two monitor cycles raised nothing.

``evaluate`` judges ONE reading per probe per cycle — the latest. A breach that
starts and clears in between is written to the database, drawn on the chart, and
never alerted, logged, or shown as an event. For a product whose whole promise is
"you will be told when your freezer fails", that is the worst shape a bug can
take: the evidence is right there and nobody was told.

It is not a corner case. It is exactly what a hub outage produces. A probe with
the threshold watch armed buffers every sample to flash while it cannot reach the
hub, then flushes the lot on reconnect — so a freezer that failed and recovered
during the outage arrives entirely as history. The watch exists so an excursion
between REPORTS is not missed; storing it and never looking gave that back at the
hub end.

The rule that keeps this from double-reporting: a run still open at the newest
reading belongs to ``evaluate`` (which owns the cooldown and deadband state for
it). Only runs that closed before the newest reading are reported here.
"""
import datetime
import pathlib
import tempfile

import pytest

from alert_monitor import AlertMonitor
from core.alerts import find_missed_excursions, format_event
from core.config import Config
from core.db import Database

THR = {"min": -22.0, "max": -15.0}


# --- the pure detector ------------------------------------------------------

def _rows(temps, step=60, start=1_700_000_000):
    return [(start + i * step, t) for i, t in enumerate(temps)]


def test_a_closed_excursion_is_one_event_not_one_per_reading():
    """13 minutes at a 7 s cadence is 110 readings and one problem."""
    runs = find_missed_excursions(_rows([-19.0] * 3 + [-8.0] * 11 + [-19.0] * 3), THR)
    assert len(runs) == 1
    run = runs[0]
    assert run["kind"] == "missed" and run["condition"] == "high"
    assert run["samples"] == 11
    assert run["end_epoch"] - run["start_epoch"] == 10 * 60


def test_an_open_run_is_left_to_the_live_evaluator():
    """The single most important property here. A breach still in force at the
    newest reading is what evaluate() is looking at, and it owns the cooldown and
    hysteresis state for it — both reporting it would send two alerts for one
    incident, from two different state machines."""
    assert find_missed_excursions(_rows([-19.0] * 3 + [-8.0] * 5), THR) == []


def test_the_worst_reading_is_the_one_reported():
    """Not the first or the last: the number that says how bad it got."""
    runs = find_missed_excursions(_rows([-19.0, -16.0, -4.5, -16.0, -19.0]), THR)
    assert runs[0]["temperature_c"] == -4.5


def test_a_low_excursion_is_found_too():
    runs = find_missed_excursions(_rows([-19.0, -30.0, -30.0, -19.0]), THR)
    assert runs[0]["condition"] == "low" and runs[0]["limit"] == -22.0


def test_two_separate_excursions_are_two_events():
    runs = find_missed_excursions(
        _rows([-19.0, -8.0, -8.0, -19.0, -19.0, -8.0, -19.0]), THR)
    assert [r["samples"] for r in runs] == [2, 1]


def test_crossing_straight_from_one_limit_to_the_other_splits():
    runs = find_missed_excursions(_rows([-19.0, -30.0, -4.0, -19.0]), THR)
    assert [r["condition"] for r in runs] == ["low", "high"]


def test_a_probe_that_never_leaves_range_reports_nothing():
    assert find_missed_excursions(_rows([-19.0] * 10), THR) == []


def test_no_thresholds_means_nothing_to_miss():
    assert find_missed_excursions(_rows([-8.0, -30.0, -19.0]), {}) == []


@pytest.mark.parametrize("rows", [[], [(1, None)], [(1, "warm")], None])
def test_unreadable_input_is_survived(rows):
    """This runs on the alert monitor thread — the one thread whose death is
    invisible. It must not raise on a bad row."""
    assert find_missed_excursions(rows or [], THR) == []


def test_the_deadband_applies_on_the_way_out():
    """Same rule as the live path: entering a breach uses the raw limit, leaving
    it must clear by the deadband — otherwise a probe hovering on its limit is
    reported as a dozen separate excursions."""
    hovering = _rows([-19.0, -14.9, -15.2, -14.9, -15.2, -19.0])
    assert len(find_missed_excursions(hovering, THR, hysteresis=0.5)) == 1
    assert len(find_missed_excursions(hovering, THR, hysteresis=0.0)) == 2


# --- the message ------------------------------------------------------------

def test_the_message_is_past_tense_and_says_when():
    """Written like a live alert it would send someone to check a freezer that is
    currently fine, and hide the fact that the readings arrived late."""
    run = find_missed_excursions(_rows([-19.0] + [-8.0] * 11 + [-19.0]), THR,
                                 probe_id="F")[0]
    subject, body = format_event(run, {"F": "Chest freezer"})
    assert "Chest freezer" in subject
    assert "went out of range" in subject and "10 min" in subject
    assert "has since returned to normal" in body
    assert "arrived late" in body and "could not reach the hub" in body


def test_the_dashboard_has_a_colour_for_it():
    """Without an entry it falls through to grey 'secondary', which on a page
    where high is red and offline is amber reads as an informational note."""
    from components.dashboard_view import _EVENT_COLORS
    assert _EVENT_COLORS["missed"] == "warning"


# --- the monitor --------------------------------------------------------------

def _hub(thresholds=None):
    d = pathlib.Path(tempfile.mkdtemp())
    db, cfg = Database(d / "t.db"), Config(d / "config.json")
    cfg.update({"alert_thresholds": thresholds if thresholds is not None
                else {"Freezer": dict(THR)},
                "notifications": {"enabled": False}})
    return db, cfg, AlertMonitor(db, cfg, notifier=None)


def _add(db, minutes_ago, temp, probe="Freezer", now=None):
    t = (now or datetime.datetime.now()) - datetime.timedelta(minutes=minutes_ago)
    db.append(t.isoformat(timespec="milliseconds"), temp, temp * 9 / 5 + 32, probe)


def _missed(monitor):
    return [e for e in monitor.check_once() if e.get("kind") == "missed"]


def test_the_outage_case_end_to_end():
    db, _cfg, mon = _hub()
    _add(db, 30, -19.0)
    assert _missed(mon) == [], "first sight must seed the watermark, not scan"

    # The hub was away for 20 minutes; minutes 15..2 of that were an excursion,
    # and the freezer had recovered by the time the readings arrived.
    for m in range(20, 0, -1):
        _add(db, m, -8.0 if 2 <= m <= 15 else -19.0)

    events = _missed(mon)
    assert len(events) == 1
    assert events[0]["condition"] == "high"
    assert events[0]["temperature_c"] == -8.0
    assert [e["kind"] for e in db.list_events(limit=10)] == ["missed"], \
        "it has to reach the durable log, or the dashboard still shows nothing"


def test_it_does_not_repeat_on_the_next_cycle():
    db, _cfg, mon = _hub()
    _add(db, 30, -19.0)
    mon.check_once()
    for m in range(20, 0, -1):
        _add(db, m, -8.0 if 2 <= m <= 15 else -19.0)
    assert len(_missed(mon)) == 1
    assert _missed(mon) == []
    assert _missed(mon) == []


def test_a_restart_does_not_re_announce_history():
    """The watermark lives in memory, so a fresh monitor over the same database
    sees the whole retention window as 'new'. Seeding on first sight is what
    stops every restart from mailing out every excursion still on disk."""
    db, cfg, mon = _hub()
    _add(db, 30, -19.0)
    mon.check_once()
    for m in range(20, 0, -1):
        _add(db, m, -8.0 if 2 <= m <= 15 else -19.0)
    assert len(_missed(mon)) == 1

    restarted = AlertMonitor(db, cfg, notifier=None)
    assert _missed(restarted) == []


def test_the_live_path_and_the_scan_never_both_claim_one_incident():
    """A breach still in force when the cycle runs is the latest reading, so
    evaluate() alerts on it. The scan must stay silent, or one freezer failure
    sends two different alerts."""
    db, _cfg, mon = _hub()
    _add(db, 30, -19.0)
    mon.check_once()
    for m in range(10, 0, -1):
        _add(db, m, -8.0 if m <= 6 else -19.0)     # still hot at the newest reading
    events = mon.check_once()
    kinds = [e["kind"] for e in events]
    assert "high" in kinds, "the live path must still fire"
    assert "missed" not in kinds, "and the scan must not double it"


def test_a_probe_with_no_limits_is_not_scanned():
    db, _cfg, mon = _hub(thresholds={"Freezer": dict(THR)})
    _add(db, 30, 20.0, probe="Office")
    mon.check_once()
    for m in range(20, 0, -1):
        _add(db, m, 90.0 if 2 <= m <= 15 else 20.0, probe="Office")
    assert _missed(mon) == []


def test_a_demo_probe_is_never_reported():
    db, _cfg, mon = _hub(thresholds={"default": dict(THR)})
    _add(db, 30, -19.0, probe="DEMO-1")
    mon.check_once()
    for m in range(20, 0, -1):
        _add(db, m, -8.0 if 2 <= m <= 15 else -19.0, probe="DEMO-1")
    assert _missed(mon) == []


def test_a_long_backfill_is_capped_and_says_so(caplog):
    """A hub off for a week must not wake up and send a hundred e-mails — and
    must not quietly drop the rest either, which would read as 'nothing else
    happened'."""
    db, _cfg, mon = _hub()
    _add(db, 400, -19.0)
    mon.check_once()
    m = 399
    while m > 1:                       # ten separate excursions
        for _ in range(3):
            _add(db, m, -8.0); m -= 1
        for _ in range(3):
            _add(db, m, -19.0); m -= 1
    with caplog.at_level("WARNING"):
        events = _missed(mon)
    assert len(events) == AlertMonitor.MISSED_MAX_PER_CYCLE
    assert any("missed excursions in one backfill" in r.message for r in caplog.records)


def test_a_notification_is_dispatched_when_alerts_are_on():
    """Recording it is not enough — the point is being told."""
    db, cfg, mon = _hub()
    cfg.update({"notifications": {"enabled": True}})
    sent = []

    class _Notifier:
        def dispatch(self, event):
            sent.append(event)
            return [("email", True, "ok")]

    mon.notifier = _Notifier()
    mon._dispatch = lambda ev: sent.append(ev)      # bypass the worker thread
    _add(db, 30, -19.0)
    mon.check_once()
    for m in range(20, 0, -1):
        _add(db, m, -8.0 if 2 <= m <= 15 else -19.0)
    mon.check_once()
    assert any(e.get("kind") == "missed" for e in sent)
    assert any("went out of range" in (e.get("subject") or "") for e in sent)


# --- how it reads on the page -----------------------------------------------

def _events_text(db, cfg):
    import re
    from components.dashboard_view import build_events

    def text(n):
        if isinstance(n, (str, int, float)):
            return str(n)
        if isinstance(n, (list, tuple)):
            return " ".join(text(c) for c in n)
        ch = getattr(n, "children", None)
        return text(ch) if ch is not None else ""
    return re.sub(r"\s+", " ", text(build_events(db, cfg, "celsius"))).strip()


def test_recent_events_dates_it_when_it_happened_not_when_it_was_found():
    """Stamped at discovery, an excursion during a three-hour outage shows as
    "just now" — false, and the one detail that makes the row actionable. Every
    other kind is judged live, so for those "now" is correct."""
    db, cfg, mon = _hub()
    cfg.update({"probe_names": {"Freezer": "Chest freezer"}})
    _add(db, 200, -19.0)
    mon.check_once()
    for m in range(199, 0, -1):
        _add(db, m, -8.0 if 175 <= m <= 190 else -19.0)
    mon.check_once()

    row = _events_text(db, cfg)
    assert "3h ago" in row, row
    assert "just now" not in row


def test_the_badge_says_what_happened():
    """"MISSED" beside HIGH / LOW / OFFLINE reads as "missed a reading"."""
    db, cfg, mon = _hub()
    _add(db, 30, -19.0)
    mon.check_once()
    for m in range(20, 0, -1):
        _add(db, m, -8.0 if 2 <= m <= 15 else -19.0)
    mon.check_once()
    assert "WAS OUT OF RANGE" in _events_text(db, cfg)


# --- arrival order, not timestamp order -------------------------------------

def test_a_backlog_flushed_after_a_restart_is_still_caught():
    """The case a timestamp watermark cannot see, and the main one this exists for.

    A backlog is old by timestamp and new by arrival. Keyed on "newest reading
    epoch", the flush that follows a hub restart looks like nothing new — and a
    hub restart is precisely what ends the outage that filled the buffer, so the
    single most important scenario was the one that silently did nothing.
    Keying on readings.id asks "what has landed since I last looked" instead.
    """
    db, cfg, _mon = _hub()
    _add(db, 30, -19.0)

    restarted = AlertMonitor(db, cfg, notifier=None)
    assert _missed(restarted) == [], "history already on disk is not re-announced"

    # ...and now the probe reconnects and drains 20 minutes of buffered samples,
    # every one of them stamped BEFORE the readings the watermark was seeded on.
    for m in range(20, 0, -1):
        _add(db, m, -8.0 if 2 <= m <= 15 else -19.0)
    events = _missed(restarted)
    assert len(events) == 1, "the flush arrived after the seed and must be scanned"
    assert events[0]["temperature_c"] == -8.0


def test_readings_older_than_the_watermark_still_count_as_new():
    """The property underneath it, at the database seam."""
    db, _cfg, _mon = _hub()
    _add(db, 5, -19.0)
    mark = db.max_reading_id()
    _add(db, 600, -8.0)          # arrives later, stamped ten minutes EARLIER
    fresh = db.readings_since_id(mark)
    assert [r[3] for r in fresh] == [-8.0], \
        "arrival order, not timestamp order — a backlog is old by stamp and new by arrival"


def test_the_sweep_covers_every_probe_in_one_pass():
    """One query per cycle, not one per probe: a fleet of thirty probes must not
    cost thirty round-trips to answer 'has anything landed'."""
    db, _cfg, mon = _hub(thresholds={"default": dict(THR)})
    for pid in ("A", "B", "C"):
        _add(db, 30, -19.0, probe=pid)
    mon.check_once()
    for pid in ("A", "B", "C"):
        for m in range(20, 0, -1):
            _add(db, m, -8.0 if 2 <= m <= 15 else -19.0, probe=pid)
    events = _missed(mon)
    assert sorted(e["probe_id"] for e in events) == ["A", "B", "C"]


def test_the_bulk_endpoint_no_longer_logs_its_own_backfill_events():
    """Both reporting it meant one incident produced a `missed` event AND one
    `high` per 100-row chunk — 62 rows for a twelve-hour outage.

    Checked against the AST, not the text: the endpoint still calls
    ``record_event`` for alert events FORWARDED by a downstream hub, which is a
    different feature entirely, and the comment left where the removed block used
    to be names the very identifiers this is looking for.
    """
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "api" / "routes.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "ingest_csv")
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert "worst" not in names, \
        "the bulk drain must leave excursion reporting to AlertMonitor._check_missed"
    assert "threshold_breach" not in names, "and stop computing it per row"


def test_a_probe_seen_for_the_first_time_with_a_backlog_is_scanned():
    """The exact shape that failed on a live hub, and the reason the watermark is
    table-level rather than per probe.

    Seeded per probe on FIRST SIGHT, a probe whose very first appearance IS the
    backlog gets its watermark set and its readings skipped — and that is the
    normal case, because a freshly started hub has never seen any probe before,
    and the flush arrives moments later. One watermark over the whole table,
    seeded once at the first sweep, has no first-sight hole to fall through.
    """
    db, _cfg, mon = _hub(thresholds={"default": dict(THR)})
    assert _missed(mon) == [], "empty hub: seed and report nothing"

    for m in range(20, 0, -1):        # this probe has never been seen before
        _add(db, m, -8.0 if 2 <= m <= 15 else -19.0, probe="BrandNew")
    events = _missed(mon)
    assert len(events) == 1, "a first-ever appearance that is a backlog must be scanned"
    assert events[0]["probe_id"] == "BrandNew"

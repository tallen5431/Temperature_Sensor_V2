"""State the alert monitor has to carry between cycles, and what it cost not to.

Three maps, three different ways of forgetting:

  * the backfill sweep kept NO state, so it restarted every chunk at
    ``prev_condition='ok'``. An excursion open at the end of chunk N reappeared
    as brand new in chunk N+1 and was mailed out as ``missed`` when it
    recovered -- an incident the live path had already alerted, now described as
    something "the hub was not watching". The existing invariant test only ever
    covered a single cycle, so it passed throughout.
  * the connectivity map was rebuilt from whichever probes reported in the last
    24 h, so a probe silent LONGER than that fell out of it and its
    ``committed='offline'`` was forgotten. On its return it was re-seeded as
    online with no transition: no back-online event, no notification, no row in
    the log. The exact case the feature exists for -- a long outage -- was the
    one it could not report the end of.
  * the daily summary sent SMTP inline on the monitor thread, and only wrote the
    last-sent date on success, so a dead mail host was retried every cycle from
    the configured hour until midnight, each attempt able to stall threshold
    evaluation for the connect timeout plus an unbounded DNS resolve.
"""
import datetime
import pathlib
import tempfile

import pytest

import alert_monitor
from alert_monitor import AlertMonitor
from core.alerts import evaluate_offline, find_missed_excursions
from core.config import Config
from core.db import Database

THR = {"min": -30.0, "max": -12.0}


def _rows(temps, start=1_700_000_000, step=60):
    return [(start + i * step, t) for i, t in enumerate(temps)]


# --- the sweep's own state -------------------------------------------------

def test_a_run_open_at_the_end_of_a_batch_is_remembered():
    state = {}
    find_missed_excursions(_rows([-19.0, -8.0, -8.0]), THR, state=state)
    assert state["condition"] == "high"


def test_a_batch_that_ends_in_range_records_ok():
    state = {}
    find_missed_excursions(_rows([-8.0, -8.0, -19.0]), THR, state=state)
    assert state["condition"] == "ok"


def test_an_excursion_carried_in_from_the_previous_batch_is_not_reported():
    # Batch 1 ends mid-excursion: nothing to report, evaluate() owns it —
    # live_open says the live engine really is holding this probe's breach.
    state = {}
    assert find_missed_excursions(_rows([-19.0, -8.0, -8.0]), THR, state=state) == []
    # Batch 2 continues it and recovers. That is the SAME incident.
    assert find_missed_excursions(_rows([-8.0, -8.0, -19.0]), THR, state=state,
                                  live_open=True) == []


def test_a_carried_run_the_live_path_never_saw_is_still_reported():
    """The other half of the rule, and the one that loses data if it is missed.

    A probe flushing a buffered outage sends readings that are OLD, so the
    monitor's freshness filter keeps them out of evaluate() entirely. Suppress
    on the carry alone and an excursion long enough to span two sweeps is
    dropped here having never been reported anywhere — which is the exact case
    the whole missed-excursion feature exists for.
    """
    state = {}
    assert find_missed_excursions(_rows([-19.0, -8.0, -8.0]), THR, state=state) == []
    runs = find_missed_excursions(_rows([-8.0, -8.0, -19.0]), THR, state=state,
                                  live_open=False)
    assert len(runs) == 1, runs
    assert runs[0]["condition"] == "high"


def test_a_genuinely_new_excursion_after_a_carried_one_is_still_reported():
    # The suppression must be surgical: only the carried run is dropped.
    state = {}
    find_missed_excursions(_rows([-19.0, -8.0]), THR, state=state)          # open
    runs = find_missed_excursions(
        _rows([-8.0, -19.0, -19.0, -8.0, -8.0, -19.0, -19.0]), THR, state=state,
        live_open=True)
    assert len(runs) == 1, runs
    assert runs[0]["condition"] == "high"
    assert "carried" not in runs[0]                     # internal flag never escapes


def test_the_deadband_survives_the_batch_boundary():
    # -12.4 is back inside the -12.0 maximum but has not cleared it by the 0.5
    # deadband, so it is still the same breach and must not close the run.
    state = {}
    find_missed_excursions(_rows([-19.0, -8.0]), THR, hysteresis=0.5, state=state)
    assert find_missed_excursions(_rows([-12.4, -8.0]), THR, hysteresis=0.5,
                                  state=state, live_open=True) == []
    assert state["condition"] == "high"


def test_without_state_the_single_batch_behaviour_is_unchanged():
    runs = find_missed_excursions(_rows([-19.0] * 3 + [-8.0] * 11 + [-19.0] * 3), THR)
    assert len(runs) == 1 and runs[0]["condition"] == "high"


# --- the same thing, through the monitor -----------------------------------

def _hub(thresholds=None):
    d = pathlib.Path(tempfile.mkdtemp())
    db, cfg = Database(d / "t.db"), Config(d / "config.json")
    cfg.update({"alert_thresholds": thresholds if thresholds is not None
                else {"Freezer": dict(THR)},
                "notifications": {"enabled": False}})
    return db, cfg, AlertMonitor(db, cfg, notifier=None)


def _add(db, minutes_ago, temp, probe="Freezer"):
    t = datetime.datetime.now() - datetime.timedelta(minutes=minutes_ago)
    db.append(t.isoformat(timespec="milliseconds"), temp, temp * 9 / 5 + 32, probe)


def test_an_excursion_that_recovers_in_a_later_batch_is_not_reported_twice():
    """The case the single-cycle invariant test never reached.

    The breach opens in one sweep and RECOVERS INSIDE THE NEXT, with readings
    after it — so the run closes before that batch's last row and looks, to a
    stateless detector, exactly like an excursion nobody watched. The live path
    alerted it on arrival and emits the recovery; the sweep must stay silent.
    Readings stay inside alert_freshness_sec (600 s) so the live path really
    does see them.
    """
    db, _cfg, mon = _hub()
    _add(db, 9, -19.0)
    mon.check_once()                                    # seed the watermark

    # Cycle 1: the freezer fails and is still hot at the newest reading.
    for m in (8, 7):
        _add(db, m, -8.0)
    kinds = [e["kind"] for e in mon.check_once()]
    assert "high" in kinds and "missed" not in kinds

    # Cycle 2: one more hot reading, then it recovers and keeps reporting.
    _add(db, 6, -8.0)
    for m in (5, 4):
        _add(db, m, -19.0)
    kinds = [e["kind"] for e in mon.check_once()]
    assert "recovery" in kinds, "the live path must still report the all-clear"
    assert "missed" not in kinds, "and the sweep must not double it"
    assert "missed" not in [e["kind"] for e in db.list_events(limit=20)]


def test_a_backfilled_excursion_spanning_two_sweeps_is_still_reported():
    """The monitor-level version of the same rule.

    Readings old enough to be a flushed outage never reach evaluate(), so the
    sweep is the only thing that can report them — even when the excursion
    straddles two of its batches.
    """
    db, _cfg, mon = _hub()
    _add(db, 600, -19.0)
    mon.check_once()                                    # seed the watermark

    # Sweep 1: the excursion opens, still open at the batch's last row.
    for m in (540, 530, 520):
        _add(db, m, -8.0)
    assert [e["kind"] for e in mon.check_once()] == [], "nothing closed yet"

    # Sweep 2: it continues and recovers, all of it far outside the 600 s
    # freshness window, so evaluate() never saw any of it.
    for m in (510, 500):
        _add(db, m, -8.0)
    for m in (490, 480):
        _add(db, m, -19.0)
    events = mon.check_once()
    kinds = [e["kind"] for e in events]
    assert "missed" in kinds, "a buffered outage was dropped by both paths"
    missed = [e for e in events if e["kind"] == "missed"]
    assert len(missed) == 1, missed
    assert missed[0]["temperature_c"] == -8.0


def test_a_deleted_probe_drops_out_of_every_state_map():
    db, _cfg, mon = _hub()
    _add(db, 5, -8.0)
    mon.check_once()                                    # seeds the watermark only
    _add(db, 4, -8.0)
    mon.check_once()                                    # now the sweep runs
    mon._offline_states["Freezer"] = {"raw": "online", "committed": "online",
                                      "online_since": 0, "flaps": 0}
    assert mon._states and mon._missed_states
    db.delete_probe("Freezer")
    mon._last_prune = 0.0
    mon.maybe_prune_probes()
    for m in (mon._states, mon._rate_states, mon._offline_states, mon._missed_states):
        assert "Freezer" not in m


# --- the all-clear after a long silence ------------------------------------

def test_a_probe_silent_past_the_old_day_bound_still_reports_back_online():
    now = 1_800_000_000.0
    day = 86400.0
    states: dict = {}
    # Seen, then silent for three days — well past the 86 400 s the monitor used
    # to bound its tracking set at.
    _events, states = evaluate_offline({"P1": now - 10}, states, now=now,
                                       offline_after_sec=300)
    events, states = evaluate_offline({"P1": now - 10}, states, now=now + 3 * day,
                                      offline_after_sec=300)
    assert [e["kind"] for e in events] == ["offline"]
    # It returns. The all-clear is the whole point of having reported it offline.
    back = now + 3 * day + 60
    events, states = evaluate_offline({"P1": back}, states, now=back,
                                      offline_after_sec=300)
    assert [e["kind"] for e in events] == ["online"]


def test_the_offline_window_matches_what_every_other_surface_uses():
    from core.status import REPORTING_LOOKBACK_SEC
    assert alert_monitor.OFFLINE_MONITOR_WINDOW_SEC == REPORTING_LOOKBACK_SEC


# --- the daily summary is not sent on the monitor thread -------------------

class _FakeSummaryDB:
    def stats_per_probe(self, _s):
        return {"P1": {"count": 3, "min": 1.0, "max": 2.0, "avg": 1.5}}

    def latest_per_probe(self, window_seconds=None, site=None):
        import pandas as pd
        return pd.DataFrame([{"probe_id": "P1", "temperature_c": 1.5}])

    def probe_ids(self):
        return ["P1"]


@pytest.fixture
def summary(tmp_path, monkeypatch):
    cfg = Config(tmp_path / "c.json")
    cfg.update({"notifications": {
        "enabled": True,
        "daily_summary": {"enabled": True, "hour": 8},
        "email": {"enabled": True, "smtp_host": "smtp.local", "to": "a@b"},
    }})
    calls = []
    result = {"ok": False, "info": "connection timed out"}
    monkeypatch.setattr(alert_monitor, "send_email",
                        lambda email, subject, body:
                        (calls.append(subject), (result["ok"], result["info"]))[1])
    mon = AlertMonitor(_FakeSummaryDB(), cfg, notifier=None, period_sec=1)
    return cfg, mon, calls, result


def test_a_failing_summary_is_attempted_once_per_cycle_not_queued_forever(summary):
    # With a live worker the send is handed off; the in-flight guard is what
    # stops ~1900 enqueues a day filling the 500-slot queue and dropping real
    # alerts. Simulate a worker that is alive but has not drained anything yet.
    cfg, mon, calls, _result = summary

    class _Wedged:
        def is_alive(self):
            return True
    mon._notify_thread = _Wedged()
    at_9 = datetime.datetime(2026, 7, 21, 9, 0)
    assert mon.maybe_daily_summary(now=at_9) is True
    for _ in range(50):
        assert mon.maybe_daily_summary(now=at_9) is False
    assert mon._notify_q.qsize() == 1, "one outstanding attempt, not fifty"
    assert calls == [], "and nothing was sent on the caller's thread"


def test_the_queued_summary_is_sent_by_the_worker_and_marks_the_date(summary):
    cfg, mon, calls, result = summary
    result["ok"] = True

    class _Wedged:
        def is_alive(self):
            return True
    mon._notify_thread = _Wedged()
    assert mon.maybe_daily_summary(now=datetime.datetime(2026, 7, 21, 9, 0)) is True
    assert cfg.get("daily_summary_last_sent") is None    # not yet — the worker owns it
    mon._send(mon._notify_q.get_nowait())                # the worker's job
    assert calls and "2026-07-21" in calls[0]
    assert cfg.get("daily_summary_last_sent") == "2026-07-21"
    assert mon._summary_inflight is None                 # cleared, ready for tomorrow


def test_a_failed_summary_is_counted_not_just_logged(summary):
    from core.applog import HEALTH
    cfg, mon, _calls, _result = summary
    before = HEALTH.snapshot().get("notify_failures", 0)
    assert mon.maybe_daily_summary(now=datetime.datetime(2026, 7, 21, 9, 0)) is False
    assert HEALTH.snapshot().get("notify_failures", 0) == before + 1
    assert cfg.get("daily_summary_last_sent") is None    # still retried tomorrow

"""Retention must never be the thing that empties the store.

``purge_older_than`` deletes on ``epoch < now - days``, so it trusts the wall
clock. A clock reading far in the PAST is harmless -- the cutoff goes negative
and matches nothing. A clock reading far in the FUTURE is not: the cutoff lands
beyond every real reading and the next hourly sweep deletes the entire history,
with no undo. ``delete_future_readings`` already guards the mirror case; these
tests pin the guard on this side.
"""
import datetime
import time

import pytest

from core.db import Database


@pytest.fixture()
def db(tmp_path):
    d = Database(tmp_path / "readings.db")
    now = time.time()
    # 100 readings spread over the last ~10 days.
    for i in range(100):
        epoch = now - i * 8640
        ts = datetime.datetime.fromtimestamp(epoch).isoformat(timespec="milliseconds")
        d.append(ts, 20.0 + i * 0.01, 68.0, "Setpoint-TEST", epoch=epoch)
    return d


def test_normal_retention_still_trims_the_tail(db):
    """The guard must not break the feature it protects."""
    assert db.count() == 100
    removed = db.purge_older_than(5)
    assert removed > 0
    assert 0 < db.count() < 100


def test_clock_jumped_forward_does_not_wipe_history(db, monkeypatch):
    before = db.count()
    ten_years = 10 * 365 * 86400
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + ten_years)
    assert db.purge_older_than(30) == 0
    assert db.count() == before


def test_clock_far_in_the_past_is_harmless(db, monkeypatch):
    """A hub booting to 1970 before NTP syncs must not delete anything either."""
    before = db.count()
    monkeypatch.setattr(time, "time", lambda: 0.0)
    assert db.purge_older_than(30) == 0
    assert db.count() == before


def test_guard_self_resolves_once_fresh_data_arrives(db, monkeypatch):
    """A hub offline longer than the retention window is declined, not stuck.

    The guard declines while every row is expired, but once probes report again
    the newest epoch is current, the cutoff falls back behind it, and the stale
    rows purge normally on the next sweep.
    """
    real = time.time
    a_year = 365 * 86400
    monkeypatch.setattr(time, "time", lambda: real() + a_year)
    assert db.purge_older_than(30) == 0          # everything expired -> declined
    assert db.count() == 100

    # A probe reports again, stamped at the (shifted) current time.
    fresh = time.time()
    db.append(datetime.datetime.fromtimestamp(fresh).isoformat(timespec="milliseconds"),
              21.0, 69.8, "Setpoint-TEST", epoch=fresh)
    removed = db.purge_older_than(30)
    assert removed == 100                        # the genuinely stale rows go
    assert db.count() == 1                       # the fresh reading survives


def test_empty_database_is_a_no_op(tmp_path):
    """MAX(epoch) is NULL on an empty table -- must not raise or misbehave."""
    assert Database(tmp_path / "empty.db").purge_older_than(30) == 0

"""Tests for the SQLite reading store (core.db)."""
import datetime
import io
import time

import pytest

from core.db import Database, iso_to_epoch, migrate_csv_if_present


def _iso(dt: datetime.datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


@pytest.fixture()
def db(tmp_path):
    return Database(tmp_path / "test.db")


def test_empty_database(db):
    assert db.count() == 0
    assert db.latest() is None
    stats = db.window_stats()
    assert stats["count"] == 0 and stats["min"] is None
    assert db.window_df().empty


def test_append_and_latest(db):
    now = datetime.datetime.now()
    db.append(_iso(now - datetime.timedelta(seconds=10)), 20.0, 68.0, "probeA")
    db.append(_iso(now), 22.5, 72.5, "probeA")
    assert db.count() == 2
    latest = db.latest()
    assert latest["temperature_c"] == 22.5
    assert latest["probe_id"] == "probeA"


def test_window_filtering(db):
    now = datetime.datetime.now()
    db.append(_iso(now - datetime.timedelta(hours=48)), 10.0, 50.0, "p")  # old
    db.append(_iso(now - datetime.timedelta(minutes=30)), 20.0, 68.0, "p")  # recent
    db.append(_iso(now), 21.0, 69.8, "p")  # recent

    all_rows = db.window_df()
    assert len(all_rows) == 3

    last_hour = db.window_df(window_seconds=3600)
    assert len(last_hour) == 2  # the 48h-old row is excluded


def test_window_stats_accurate(db):
    now = datetime.datetime.now()
    db.append(_iso(now - datetime.timedelta(minutes=3)), 10.0, 50.0, "p")
    db.append(_iso(now - datetime.timedelta(minutes=2)), 30.0, 86.0, "p")
    db.append(_iso(now - datetime.timedelta(minutes=1)), 20.0, 68.0, "p")
    stats = db.window_stats(window_seconds=3600)
    assert stats["count"] == 3
    assert stats["min"] == 10.0
    assert stats["max"] == 30.0
    assert stats["avg"] == pytest.approx(20.0)
    # min/max timestamps point at the correct rows
    assert stats["min_ts"].endswith(_iso(now - datetime.timedelta(minutes=3))[-8:])


def test_downsampling_caps_points_but_not_stats(db):
    now = datetime.datetime.now()
    base = now - datetime.timedelta(hours=1)
    for i in range(1000):
        db.append(_iso(base + datetime.timedelta(seconds=i)), float(i % 50), 0.0, "p")
    df = db.window_df(window_seconds=7200, max_points=100)
    assert len(df) <= 100  # plot is downsampled
    stats = db.window_stats(window_seconds=7200)
    assert stats["count"] == 1000  # stats use the full set
    assert stats["max"] == 49.0


def test_latest_per_probe(db):
    now = datetime.datetime.now()
    db.append(_iso(now - datetime.timedelta(seconds=20)), 19.0, 0.0, "A")
    db.append(_iso(now - datetime.timedelta(seconds=10)), 25.0, 0.0, "A")
    db.append(_iso(now - datetime.timedelta(seconds=5)), 30.0, 0.0, "B")
    latest = db.latest_per_probe()
    by_probe = {r["probe_id"]: r["temperature_c"] for _, r in latest.iterrows()}
    assert by_probe == {"A": 25.0, "B": 30.0}


def test_export_csv_roundtrip(db):
    now = datetime.datetime.now()
    db.append(_iso(now), 22.123, 71.821, "probeX")
    buf = io.StringIO()
    n = db.export_csv(buf)
    assert n == 1
    content = buf.getvalue()
    assert "timestamp,timestamp_utc,temperature_c,temperature_f,probe_id" in content
    assert "probeX" in content
    assert "22.123" in content
    # every data row carries an unambiguous UTC timestamp ending in Z
    assert content.splitlines()[1].split(",")[1].endswith("Z")


def test_export_csv_filters(db):
    now = datetime.datetime.now()
    old = now - datetime.timedelta(days=3)
    db.append(_iso(old), 10.0, 50.0, "A")     # 3 days ago
    db.append(_iso(now), 20.0, 68.0, "A")     # today
    db.append(_iso(now), 4.0, 39.2, "B")      # today, other probe

    def rows(**kw):
        buf = io.StringIO()
        n = db.export_csv(buf, **kw)
        return n

    assert rows() == 3
    assert rows(probe_id="A") == 2
    assert rows(probe_id="B") == 1
    # absolute date range: only today's readings
    start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    assert rows(start_epoch=start) == 2
    # combine probe + range
    assert rows(probe_id="A", start_epoch=start) == 1
    # end_epoch excludes today
    assert rows(end_epoch=start - 1) == 1  # only the 3-days-ago row


def test_iso_to_epoch_roundtrip():
    now = datetime.datetime.now().replace(microsecond=0)
    epoch = iso_to_epoch(now.isoformat())
    assert abs(epoch - now.timestamp()) < 1.5
    # trailing Z tolerated
    assert iso_to_epoch(now.isoformat() + "Z") == epoch
    # garbage falls back to ~now instead of raising
    assert abs(iso_to_epoch("not-a-date") - time.time()) < 2


def test_last_reading_epoch_per_probe(db):
    now = datetime.datetime.now()
    db.append(_iso(now - datetime.timedelta(seconds=30)), 10.0, 0.0, "A")
    db.append(_iso(now), 11.0, 0.0, "A")              # newer for A
    db.append(_iso(now - datetime.timedelta(seconds=5)), 20.0, 0.0, "B")
    last = db.last_reading_epoch_per_probe()
    assert set(last.keys()) == {"A", "B"}
    assert last["A"] >= last["B"]  # A's newest is more recent than B's


def test_stats_per_probe(db):
    now = datetime.datetime.now()
    # Freezer probe A: cold range; room probe B: warm range.
    for t in (-20.0, -18.0, -16.0):
        db.append(_iso(now), t, 0.0, "A")
    for t in (20.0, 22.0, 24.0):
        db.append(_iso(now), t, 0.0, "B")
    stats = db.stats_per_probe()
    assert set(stats.keys()) == {"A", "B"}
    assert stats["A"]["min"] == -20.0 and stats["A"]["max"] == -16.0
    assert stats["A"]["count"] == 3
    assert abs(stats["A"]["avg"] - (-18.0)) < 1e-6
    assert stats["B"]["min"] == 20.0 and stats["B"]["max"] == 24.0
    assert abs(stats["B"]["avg"] - 22.0) < 1e-6


def test_stats_per_probe_empty(db):
    assert db.stats_per_probe() == {}


def test_window_stats_probe_filter(db):
    now = datetime.datetime.now()
    for t in (-20.0, -18.0, -16.0):
        db.append(_iso(now), t, 0.0, "A")
    for t in (20.0, 22.0, 24.0):
        db.append(_iso(now), t, 0.0, "B")
    alls = db.window_stats()
    assert alls["min"] == -20.0 and alls["max"] == 24.0 and alls["count"] == 6
    a = db.window_stats(probe_id="A")
    assert a["min"] == -20.0 and a["max"] == -16.0 and a["count"] == 3
    assert abs(a["avg"] - (-18.0)) < 1e-6
    assert db.window_stats(probe_id="nope")["count"] == 0


def test_delete_probe(db):
    now = datetime.datetime.now()
    for i in range(4):
        db.append(_iso(now), 20.0 + i, 0.0, "keep")
    for i in range(3):
        db.append(_iso(now), 5.0 + i, 0.0, "gone")
    assert db.count() == 7
    removed = db.delete_probe("gone")
    assert removed == 3
    assert db.count() == 4
    assert set(db.stats_per_probe().keys()) == {"keep"}
    # Deleting again removes nothing; a blank id is a guarded no-op.
    assert db.delete_probe("gone") == 0
    assert db.delete_probe("") == 0
    assert db.count() == 4


def test_bulk_insert(db):
    now = datetime.datetime.now()
    rows = [(_iso(now - datetime.timedelta(seconds=i)), float(i), float(i) * 2, "p")
            for i in range(100)]
    n = db.bulk_insert(rows)
    assert n == 100
    assert db.count() == 100
    assert db.bulk_insert([]) == 0  # empty is a no-op


def test_purge_older_than(db):
    now = datetime.datetime.now()
    db.append(_iso(now - datetime.timedelta(days=40)), 10.0, 50.0, "p")  # old
    db.append(_iso(now - datetime.timedelta(days=5)), 20.0, 68.0, "p")   # recent
    db.append(_iso(now), 21.0, 69.8, "p")                                # recent
    removed = db.purge_older_than(30)
    assert removed == 1
    assert db.count() == 2
    # 0 days = keep forever (no-op)
    assert db.purge_older_than(0) == 0
    assert db.count() == 2


def test_backup_snapshot(db, tmp_path):
    now = datetime.datetime.now()
    for i in range(5):
        db.append(_iso(now - datetime.timedelta(seconds=i)), float(i), 0.0, "p")
    dest = tmp_path / "backup.db"
    db.backup(dest)
    assert dest.exists()
    # The snapshot is a valid, queryable database with the same row count.
    snap = Database(dest)
    assert snap.count() == 5


def test_migrate_csv(tmp_path):
    csv_path = tmp_path / "legacy.csv"
    csv_path.write_text(
        "timestamp,temperature_c,temperature_f,probe_id\n"
        "2026-01-01T10:00:00,20.0,68.0,p1\n"
        "2026-01-01T10:00:05,21.0,69.8,p1\n"
        "bad,row,here,x\n",  # unparseable temp -> skipped
        encoding="utf-8",
    )
    db = Database(tmp_path / "m.db")
    imported = migrate_csv_if_present(db, csv_path)
    assert imported == 2
    assert db.count() == 2
    # second call is a no-op because the db is no longer empty
    assert migrate_csv_if_present(db, csv_path) == 0

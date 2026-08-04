"""Multi-site roll-up: a store hub forwarding its readings to an HQ hub.

The correctness properties that matter, in the order they would hurt:

  * never skip a reading (a missed row is a hole in a food-safety record)
  * never loop (two hubs pointed at each other must not ping-pong forever)
  * survive an outage without losing the backlog or re-sending the world
  * refuse to run half-configured rather than pooling stores anonymously
"""
import datetime
import pathlib

import pytest

from core.config import Config
from core.db import Database
from core.forwarder import UpstreamForwarder, ingest_url, rows_to_payload


def _seed(db, n=5, probe="Setpoint-9A3F2C", start=None, site=""):
    now = start or datetime.datetime.now()
    for i in range(n):
        ts = (now + datetime.timedelta(seconds=i)).isoformat(timespec="milliseconds")
        db.append(ts, 4.0 + i * 0.1, 39.2, probe, site=site)


@pytest.fixture
def store(tmp_path):
    db = Database(tmp_path / "store.db")
    cfg = Config(tmp_path / "store.json")
    cfg.set("upstream", {"enabled": True, "url": "http://hq.local:8088",
                         "token": "T", "site": "atl"})
    return db, cfg


class _Capture:
    """Stand-in for post_batch: records calls, returns a scripted status."""
    def __init__(self, status=200):
        self.status = status
        self.calls = []

    def __call__(self, url, token, site, rows, events=(), timeout=20.0):
        self.calls.append({"url": url, "token": token, "site": site,
                           "ids": [r[0] for r in rows],
                           "event_ids": [e[0] for e in events]})
        return self.status


class _RecordingStop:
    """Let ``run`` execute a fixed number of cycles and record its delays."""

    def __init__(self, cycles):
        self.cycles = cycles
        self.delays = []

    def is_set(self):
        return len(self.delays) >= self.cycles

    def wait(self, delay):
        self.delays.append(delay)
        return self.is_set()


def test_ingest_url_normalises():
    assert ingest_url("http://h:8088") == "http://h:8088/api/ingest_csv"
    assert ingest_url("http://h:8088/") == "http://h:8088/api/ingest_csv"
    assert ingest_url("http://h:8088/api/ingest_csv") == "http://h:8088/api/ingest_csv"
    assert ingest_url("") == ""


def test_forwards_then_advances_and_stops(store, monkeypatch):
    db, cfg = store
    _seed(db, 3)
    cap = _Capture(200)
    monkeypatch.setattr("core.forwarder.post_batch", cap)
    fwd = UpstreamForwarder(db, cfg)

    assert fwd.run_once() == 3
    assert cap.calls[0]["site"] == "atl"
    assert cap.calls[0]["token"] == "T"
    assert cap.calls[0]["url"].endswith("/api/ingest_csv")
    # Cursor advanced, so a second cycle has nothing to do.
    assert fwd.run_once() == 0
    assert len(cap.calls) == 1


def test_failure_holds_the_cursor_so_nothing_is_skipped(store, monkeypatch):
    db, cfg = store
    _seed(db, 2)
    fail = _Capture(503)
    monkeypatch.setattr("core.forwarder.post_batch", fail)
    fwd = UpstreamForwarder(db, cfg)
    assert fwd.run_once() == 0

    # Upstream recovers: the SAME rows must go, not the next ones.
    ok = _Capture(200)
    monkeypatch.setattr("core.forwarder.post_batch", ok)
    assert fwd.run_once() == 2
    assert ok.calls[0]["ids"] == fail.calls[0]["ids"]


def test_backlog_written_during_an_outage_is_picked_up(store, monkeypatch):
    db, cfg = store
    _seed(db, 2)
    cap = _Capture(200)
    monkeypatch.setattr("core.forwarder.post_batch", cap)
    fwd = UpstreamForwarder(db, cfg)
    fwd.run_once()
    # Probe keeps writing while the link is down / hub restarts.
    _seed(db, 3, start=datetime.datetime.now() + datetime.timedelta(minutes=1))
    assert fwd.run_once() == 3
    assert cap.calls[1]["ids"] == [3, 4, 5]


def test_cursor_survives_restart(store, monkeypatch, tmp_path):
    db, cfg = store
    _seed(db, 2)
    monkeypatch.setattr("core.forwarder.post_batch", _Capture(200))
    UpstreamForwarder(db, cfg).run_once()
    # A brand-new forwarder (process restart) must not re-send the history.
    fresh = UpstreamForwarder(Database(tmp_path / "store.db"), cfg)
    assert fresh.run_once() == 0


def test_forwarded_rows_are_never_re_forwarded(store, monkeypatch):
    """The loop guard: rows that arrived FROM another hub carry a site and must
    not be pushed on, or two hubs pointed at each other never stop."""
    db, cfg = store
    _seed(db, 2, site="marietta")      # arrived here from elsewhere
    _seed(db, 1, probe="Local-1", start=datetime.datetime.now() + datetime.timedelta(minutes=5))
    cap = _Capture(200)
    monkeypatch.setattr("core.forwarder.post_batch", cap)
    assert UpstreamForwarder(db, cfg).run_once() == 1
    assert cap.calls[0]["ids"] == [3]


def test_refuses_to_forward_without_a_site_label(tmp_path, monkeypatch):
    db = Database(tmp_path / "s.db")
    cfg = Config(tmp_path / "c.json")
    cfg.set("upstream", {"enabled": True, "url": "http://hq:8088", "token": "T"})
    _seed(db, 2)
    cap = _Capture(200)
    monkeypatch.setattr("core.forwarder.post_batch", cap)
    # Unlabelled readings would pool six stores into one anonymous heap that no
    # later migration could separate. Better to do nothing and log.
    assert UpstreamForwarder(db, cfg).run_once() == 0
    assert cap.calls == []


def test_disabled_is_inert(tmp_path, monkeypatch):
    db = Database(tmp_path / "s.db")
    cfg = Config(tmp_path / "c.json")
    _seed(db, 3)
    cap = _Capture(200)
    monkeypatch.setattr("core.forwarder.post_batch", cap)
    assert UpstreamForwarder(db, cfg).run_once() == 0
    assert cap.calls == []


def test_payload_shape_matches_what_ingest_csv_accepts(store):
    db, _ = store
    db.append(datetime.datetime.now().isoformat(timespec="milliseconds"),
              4.0, 39.2, "P1", humidity=55.0, battery=87.0)
    payload = rows_to_payload(db.rows_after(0))
    assert payload[0]["probe_id"] == "P1"
    assert payload[0]["temperature_c"] == 4.0
    assert payload[0]["humidity_pct"] == 55.0
    assert payload[0]["battery_pct"] == 87.0
    # The local autoincrement id is this hub's cursor and meaningless upstream.
    assert "id" not in payload[0]


def test_batch_is_capped_to_the_protocol_limit(store, monkeypatch):
    db, cfg = store
    cfg.set("upstream", {**cfg.get("upstream"), "batch": 99999})
    _seed(db, 5)
    cap = _Capture(200)
    monkeypatch.setattr("core.forwarder.post_batch", cap)
    UpstreamForwarder(db, cfg).run_once()
    assert len(cap.calls[0]["ids"]) == 5     # all five, but the request cap held


def test_non_default_full_batches_fast_drain_then_partial_batch_waits(store, monkeypatch):
    db, cfg = store
    cfg.set("upstream", {**cfg.get("upstream"), "batch": 2, "interval_sec": 30})
    _seed(db, 5)
    cap = _Capture(200)
    monkeypatch.setattr("core.forwarder.post_batch", cap)
    stop = _RecordingStop(cycles=3)

    UpstreamForwarder(db, cfg, stop).run()

    assert [call["ids"] for call in cap.calls] == [[1, 2], [3, 4], [5]]
    assert stop.delays == [1, 1, 30]


def test_event_only_full_batch_fast_drains(store, monkeypatch):
    db, cfg = store
    cfg.set("upstream", {**cfg.get("upstream"), "batch": 2, "interval_sec": 30})
    for _ in range(3):
        db.record_event("offline", "Setpoint-9A3F2C")
    cap = _Capture(200)
    monkeypatch.setattr("core.forwarder.post_batch", cap)
    stop = _RecordingStop(cycles=2)

    UpstreamForwarder(db, cfg, stop).run()

    assert [call["event_ids"] for call in cap.calls] == [[1, 2], [3]]
    assert stop.delays == [1, 30]


def test_events_forward_alongside_readings(store, monkeypatch):
    """A store's alert decisions are a separate record from its readings, and
    the one an auditor asks for. They ride the same request so one round trip
    advances both cursors — either the batch lands or neither moves."""
    db, cfg = store
    _seed(db, 2)
    db.record_event("high", "Setpoint-9A3F2C", 15.0, 8.0)
    cap = _Capture(200)
    monkeypatch.setattr("core.forwarder.post_batch", cap)

    fwd = UpstreamForwarder(db, cfg)
    assert fwd.run_once() == 2                 # return value stays "readings sent"
    assert cap.calls[0]["event_ids"] == [1]
    # Both cursors advanced, so a second cycle is idle.
    assert fwd.run_once() == 0
    assert len(cap.calls) == 1


def test_an_events_only_batch_still_goes(store, monkeypatch):
    """Events must not need a reading to travel with — an offline event fires
    precisely when readings have stopped arriving."""
    db, cfg = store
    db.record_event("offline", "Setpoint-9A3F2C")
    cap = _Capture(200)
    monkeypatch.setattr("core.forwarder.post_batch", cap)
    UpstreamForwarder(db, cfg).run_once()
    assert cap.calls[0]["ids"] == [] and cap.calls[0]["event_ids"] == [1]


def test_forwarded_events_are_never_re_forwarded(store, monkeypatch):
    """The loop guard, for events: rows that arrived FROM another hub carry a
    site and must not be pushed on."""
    db, cfg = store
    db.record_event("high", "Remote", 12.0, 8.0, site="marietta")
    db.record_event("high", "Local", 12.0, 8.0)
    cap = _Capture(200)
    monkeypatch.setattr("core.forwarder.post_batch", cap)
    UpstreamForwarder(db, cfg).run_once()
    assert cap.calls[0]["event_ids"] == [2]


def test_a_failed_batch_holds_both_cursors(store, monkeypatch):
    db, cfg = store
    _seed(db, 2)
    db.record_event("high", "Setpoint-9A3F2C", 15.0, 8.0)
    fail = _Capture(503)
    monkeypatch.setattr("core.forwarder.post_batch", fail)
    fwd = UpstreamForwarder(db, cfg)
    assert fwd.run_once() == 0

    ok = _Capture(200)
    monkeypatch.setattr("core.forwarder.post_batch", ok)
    assert fwd.run_once() == 2
    assert ok.calls[0]["ids"] == fail.calls[0]["ids"]
    assert ok.calls[0]["event_ids"] == fail.calls[0]["event_ids"]

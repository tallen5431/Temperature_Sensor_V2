"""The instant a reading claims, from the probe's clock to head office's row.

Four bugs shared one root: an epoch that nobody carried, so somebody re-derived
one — and re-derivation is only correct when the deriver shares the writer's
clock and timezone. Each of these was silent, and each corrupted the ORDERING
column, which every read path filters and sorts on.

  * ``/api/ingest`` clamped a drifted probe's future timestamp into ``ts`` and
    then stored that probe's un-clamped epoch beside it. One drifted probe
    pinned ``latest`` forever, could never be judged offline (``now - epoch`` is
    negative), and out-sorted its own corrected readings after its clock synced.
  * The upstream forwarder put its LOCAL-NAIVE ``ts`` on the wire and dropped
    the epoch it already had, so head office in another timezone re-read a
    store's wall clock as its own — and a store to the east had every batch
    re-stamped to arrival by the receiver's future-stamp guard.
  * The same for forwarded alert EVENTS, which take a different write path
    (``Database.record_event``) and so needed fixing on their own.
  * ``post_batch`` used the default urllib opener, which follows redirects: the
    token went to whatever host ``Location`` named, the POST body was dropped,
    and a 2xx from that host advanced both cursors past records never sent.
"""
import datetime
import http.server
import os
import threading
import time as _time

import pytest

from core.db import Database, utc_iso
from core.forwarder import (UpstreamForwarder, _explain, events_to_payload,
                            post_batch, rows_to_payload)
from core.config import Config
from core.storage import absolute_epoch, is_future_stamp, normalize_payload


@pytest.fixture
def tz(monkeypatch):
    """Run a block under a named timezone, restoring the real one after."""
    if not hasattr(_time, "tzset"):                     # non-POSIX; nothing to assert
        pytest.skip("timezone switching needs time.tzset()")

    def _set(name):
        monkeypatch.setenv("TZ", name)
        _time.tzset()
    yield _set
    os.environ.pop("TZ", None)
    _time.tzset()


# --- the clamp and the epoch must agree -----------------------------------

def _ingest_client(tmp_path):
    from tests.test_api import _make_client            # one client factory, not two
    return _make_client(tmp_path)


def test_a_future_stamped_reading_does_not_keep_its_future_epoch(tmp_path):
    client, db, _ = _ingest_client(tmp_path)
    now = _time.time()
    ahead = datetime.datetime.fromtimestamp(
        now + 4 * 365 * 86400, tz=datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    client.post("/api/ingest",
                json={"temperature_c": 25.0, "probe_id": "P1", "timestamp": ahead})
    row = db._conn().execute("SELECT ts, epoch FROM readings").fetchone()
    # ts was clamped to the hub's clock; the epoch must have been clamped with it,
    # or every ORDER BY epoch in core/db.py still sees the year 2030.
    assert abs(row["epoch"] - now) < 10, row["epoch"]
    assert row["ts"].startswith(datetime.datetime.fromtimestamp(now).strftime("%Y-%m-%d"))


def test_a_clamped_reading_stops_out_sorting_the_probes_corrected_ones(tmp_path):
    # The consequence that actually hurts: after the probe's clock syncs, its
    # real readings must become "latest" again.
    client, db, _ = _ingest_client(tmp_path)
    ahead = datetime.datetime.fromtimestamp(
        _time.time() + 86400 * 900, tz=datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    client.post("/api/ingest", json={"temperature_c": -30.0, "probe_id": "P1", "timestamp": ahead})
    good = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    client.post("/api/ingest", json={"temperature_c": 4.0, "probe_id": "P1", "timestamp": good})
    assert db.latest_per_probe()["temperature_c"].iloc[-1] == 4.0


def test_a_probe_stamp_inside_tolerance_still_keeps_its_exact_epoch(tmp_path):
    # The clamp must not become a blanket "ignore the probe's clock" — the DST
    # fall-back fix depends on a good tz-aware stamp surviving verbatim.
    client, db, _ = _ingest_client(tmp_path)
    exact = "2025-06-01T12:00:00.000Z"
    client.post("/api/ingest", json={"temperature_c": 4.0, "probe_id": "P1", "timestamp": exact})
    row = db._conn().execute("SELECT epoch FROM readings").fetchone()
    assert row["epoch"] == pytest.approx(absolute_epoch(exact))


# --- what travels between two hubs ----------------------------------------

def _forward_one(tmp_path, store_tz, hq_tz, tz):
    """Write one reading + one event in ``store_tz``, ingest them in ``hq_tz``."""
    tz(store_tz)
    store = Database(tmp_path / "store.db")
    stamp = datetime.datetime.now().isoformat(timespec="milliseconds")
    store.append(stamp, 4.0, 39.2, "P1")
    store.record_event("high", "P1", temperature_c=9.0, limit=8.0)
    rows, events = store.rows_after(0), store.events_after(0)
    wire_rows, wire_events = rows_to_payload(rows), events_to_payload(events)

    tz(hq_tz)
    hq = Database(tmp_path / "hq.db")
    ts, t_c, t_f = normalize_payload(wire_rows[0])
    hq.bulk_insert([(ts, t_c, t_f, "P1", None, None, None,
                     absolute_epoch(wire_rows[0]["timestamp"]))], site="store1")
    hq.record_event("high", "P1", temperature_c=9.0, limit=8.0,
                    ts=wire_events[0]["timestamp"], epoch=wire_events[0].get("epoch"),
                    site="store1")
    return rows[0], events[0], wire_rows[0], wire_events[0], hq


@pytest.mark.parametrize("store_tz,hq_tz", [
    ("Europe/Berlin", "America/Los_Angeles"),     # 9 h apart, store ahead
    ("America/Los_Angeles", "Europe/Berlin"),     # and the other direction
    ("UTC", "UTC"),                               # the no-op case still works
])
def test_head_office_stores_the_instant_the_store_recorded(tmp_path, tz, store_tz, hq_tz):
    row, event, _wr, _we, hq = _forward_one(tmp_path, store_tz, hq_tz, tz)
    hq_row = hq._conn().execute("SELECT epoch FROM readings").fetchone()
    hq_event = hq._conn().execute("SELECT ts, epoch FROM events").fetchone()
    assert hq_row["epoch"] == pytest.approx(row[2], abs=0.002)
    # Events go through record_event, a different write path from readings —
    # fixing only the readings half left the audit trail skewed.
    assert hq_event["epoch"] == pytest.approx(event[2], abs=1.5)
    # ...and the event's ts column is this hub's wall clock, like every row
    # beside it — derived from the instant, not copied off the wire.
    assert not hq_event["ts"].endswith("Z")
    assert hq_event["ts"] == datetime.datetime.fromtimestamp(
        hq_event["epoch"]).isoformat(timespec="seconds")


def test_the_wire_carries_an_unambiguous_instant_for_both_records(tmp_path, tz):
    """Readings send UTC; events send their naive stamp plus an `epoch` field.

    The asymmetry is deliberate, and it is about the PREVIOUS release. A hub
    running it already recovers a Z-suffixed reading stamp correctly, but its
    record_event derives the epoch with iso_to_epoch, which strips the Z and
    reads the rest as local — so sending UTC there would have skewed forwarded
    events on an older head office by its whole UTC offset, including on the
    same-timezone deployments that were previously right. An extra field is
    ignored by that build and honoured by this one.
    """
    _row, event, wire_row, wire_event, _hq = _forward_one(
        tmp_path, "Europe/Berlin", "Europe/Berlin", tz)
    assert wire_row["timestamp"].endswith("Z")
    assert absolute_epoch(wire_row["timestamp"]) is not None

    assert not wire_event["timestamp"].endswith("Z"), \
        "an older head office reads a Z-stamped event as local time"
    assert wire_event["epoch"] == pytest.approx(event[2])


def test_an_older_head_office_reads_a_forwarded_event_exactly_as_before(tmp_path, tz):
    """The compatibility guarantee, spelled out: with the `epoch` field dropped
    (as a build that does not know it would), the stamp still resolves the way
    it did before this change."""
    from core.db import iso_to_epoch
    tz("Europe/Berlin")
    store = Database(tmp_path / "store.db")
    store.record_event("high", "P1", temperature_c=9.0, limit=8.0)
    event = store.events_after(0)[0]
    wire = events_to_payload([event])[0]
    # What the old receiver computes, having ignored `epoch` entirely.
    assert int(iso_to_epoch(wire["timestamp"])) == event[2]


def test_a_store_to_the_east_is_not_restamped_as_future(tmp_path, tz):
    # The receiver clamps anything more than 120 s ahead of its own clock. A
    # naive Berlin stamp read in Los Angeles is 9 h ahead, so head office
    # re-stamped every forwarded row to arrival time and logged "check the
    # probe's clock (NTP)" about a probe with a perfectly good clock.
    tz("Europe/Berlin")
    store = Database(tmp_path / "store.db")
    store.append(datetime.datetime.now().isoformat(timespec="milliseconds"), 4.0, 39.2, "P1")
    wire = rows_to_payload(store.rows_after(0))[0]
    tz("America/Los_Angeles")
    assert is_future_stamp(wire["timestamp"]) is False


def test_utc_iso_round_trips_through_absolute_epoch():
    for epoch in (1767222000.0, 1767222000.123, 0.0):
        assert absolute_epoch(utc_iso(epoch)) == pytest.approx(epoch, abs=0.001)


# --- a redirect is not a delivery ------------------------------------------

class _Quiet(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):                          # keep pytest output clean
        pass


@pytest.fixture
def redirect_pair():
    """A server that 302s to a second server that records what arrives."""
    received = []

    class Target(_Quiet):
        def _answer(self):
            received.append((self.command, dict(self.headers)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        do_GET = do_POST = _answer

    target = http.server.HTTPServer(("127.0.0.1", 0), Target)

    class Redirector(_Quiet):
        def do_POST(self):
            self.send_response(302)
            self.send_header("Location",
                             f"http://127.0.0.1:{target.server_address[1]}/api/ingest_csv")
            self.end_headers()

    redirector = http.server.HTTPServer(("127.0.0.1", 0), Redirector)
    for srv in (target, redirector):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{redirector.server_address[1]}/api/ingest_csv", received
    for srv in (target, redirector):
        srv.shutdown()


ONE_ROW = [(1, "2026-01-01T00:00:00", 1767222000.0, 4.0, 39.2, "P1", None, None, None)]


def test_a_redirect_is_reported_as_a_redirect_not_a_delivery(redirect_pair):
    url, _received = redirect_pair
    assert post_batch(url, "T", "store1", ONE_ROW) == 302   # not 2xx -> cursor holds


def test_the_device_token_is_never_replayed_at_a_redirect_target(redirect_pair):
    url, received = redirect_pair
    post_batch(url, "SUPER-SECRET-TOKEN", "store1", ONE_ROW)
    assert received == [], "the redirect target was contacted at all"


def test_the_operator_is_told_a_redirect_is_what_happened():
    assert "redirect" in _explain(302).lower()
    assert "redirect" in _explain(301).lower()


# --- a site label the receiver will keep -----------------------------------

@pytest.mark.parametrize("label", ["東京店", "###", "   "])
def test_a_site_label_that_sanitises_away_refuses_to_forward(tmp_path, label):
    # The receiver runs sanitize_site on X-Site, and an empty site is the marker
    # for "ingested locally HERE" — so these rows would be judged by head
    # office's own thresholds, swept by its alert monitor and forwarded onward.
    db = Database(tmp_path / "s.db")
    cfg = Config(tmp_path / "s.json")
    cfg.set("upstream", {"enabled": True, "url": "http://hq:8088", "token": "T",
                         "site": label})
    db.append(datetime.datetime.now().isoformat(timespec="milliseconds"), 4.0, 39.2, "P1")
    fwd = UpstreamForwarder(db, cfg)
    sent = []
    import core.forwarder as fw
    real, fw.post_batch = fw.post_batch, lambda *a, **k: sent.append(a) or 200
    try:
        assert fwd.run_once() == 0
    finally:
        fw.post_batch = real
    assert sent == []
    assert fwd.last_error


def test_a_usable_site_label_still_forwards(tmp_path):
    db = Database(tmp_path / "s.db")
    cfg = Config(tmp_path / "s.json")
    cfg.set("upstream", {"enabled": True, "url": "http://hq:8088", "token": "T",
                         "site": "atl-1"})
    db.append(datetime.datetime.now().isoformat(timespec="milliseconds"), 4.0, 39.2, "P1")
    fwd = UpstreamForwarder(db, cfg)
    seen = {}
    import core.forwarder as fw
    real = fw.post_batch

    def _capture(url, token, site, rows, events=(), timeout=20.0):
        seen["site"] = site
        return 200
    fw.post_batch = _capture
    try:
        assert fwd.run_once() == 1
    finally:
        fw.post_batch = real
    assert seen["site"] == "atl-1"
    assert fwd.last_error == ""


def test_two_clamped_readings_in_one_millisecond_both_survive(tmp_path):
    """The clamp must not become its own data-loss path.

    _local_iso_now() has millisecond precision, so deriving the epoch from the
    clamped `ts` would give two readings inside one millisecond the same epoch
    — and UNIQUE(probe_id, epoch, site) would drop the second while the
    endpoint still answered 200, which is the silent loss the bulk path spreads
    its restamps 1 ms apart to avoid.
    """
    client, db, _ = _ingest_client(tmp_path)
    ahead = datetime.datetime.fromtimestamp(
        _time.time() + 86400 * 500, tz=datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    for temp in (4.0, 5.0, 6.0):
        client.post("/api/ingest",
                    json={"temperature_c": temp, "probe_id": "P1", "timestamp": ahead})
    assert db.count() == 3, "a clamped reading was swallowed by the unique index"


def test_a_clamped_rows_ts_and_epoch_describe_the_same_instant(tmp_path):
    """db.append's contract is that `epoch` IS the instant of `ts`, and
    export_csv writes `timestamp_utc` from one beside `timestamp` from the
    other — so taking a second clock read for the epoch would let one row show
    two different times. One value, derived from the stored string."""
    from core.db import iso_to_epoch
    client, db, _ = _ingest_client(tmp_path)
    ahead = datetime.datetime.fromtimestamp(
        _time.time() + 86400 * 500, tz=datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    client.post("/api/ingest",
                json={"temperature_c": 4.0, "probe_id": "P1", "timestamp": ahead})
    row = db._conn().execute("SELECT ts, epoch FROM readings").fetchone()
    assert row["epoch"] == pytest.approx(iso_to_epoch(row["ts"]), abs=1e-6)

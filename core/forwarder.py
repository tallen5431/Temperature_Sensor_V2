"""Forward this hub's readings and alert log to another hub (multi-site roll-up).

A chain with six stores wants head office to see all six. The local-first
architecture is the product's whole point, so the answer is *not* a cloud: each
store keeps its own hub and its own database, and optionally **pushes a copy** of
its readings to an aggregating hub that head office runs.

The shape falls out of what already exists — a store hub forwarding to an HQ hub
is the same relationship a probe already has with a hub:

===========================  ==========================================
probe  ->  hub               store hub  ->  HQ hub
===========================  ==========================================
POST /api/ingest_csv         the same endpoint, plus an `events` array
X-Token auth                 the same auth
buffers to flash when down   the backlog simply stays unsent
UNIQUE(probe_id,epoch,site)  the same index makes re-sends idempotent
===========================  ==========================================

TWO RECORDS travel, not one. Readings are what the sensor measured; events are
what this store's own alert engine DECIDED about them, against this store's own
thresholds. Head office re-evaluating the same readings against its own limits
gives a different answer, and it is the store's answer that belongs in the
store's audit trail. They share one request — one round trip, and either the
batch lands or neither cursor moves — but keep separate cursors so neither
stream can block the other.

That last row is what makes this safe. Because the receiving hub inserts with
``INSERT OR IGNORE`` against ``UNIQUE(probe_id, epoch, site)``, a batch re-sent after a
dropped response cannot duplicate rows. The forwarder therefore never has to be
clever about exactly-once delivery: it only has to be sure it never *skips*, and
at-least-once is free.

**Push, never pull.** Stores need no inbound reachability at all — no tunnel, no
port forward, no VPN, nothing to secure per site. It also keeps working across a
store's outage: the high-water mark simply stops advancing and catches up later.

Design notes:

* The cursor is the ``readings.id`` autoincrement, not a timestamp. A probe
  draining a backlog writes *old* readings *now*; an epoch cursor would skip them
  because they are older than the mark. Insertion order is the only order that
  cannot lose a row.
* Only locally-ingested rows are forwarded (``site = ''``). Rows that arrived
  here *from* another hub are excluded, so two hubs pointed at each other cannot
  ping-pong the same readings forever.
* The high-water mark lives in the ``meta`` table, so a restart neither re-sends
  the whole history nor silently skips what was written while it was down.

See ``docs/MULTI_SITE.md`` for the operator's view and a two-hub test recipe.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from core.db import utc_iso
from core.protocol import MAX_BATCH_ROWS, MAX_INGEST_BYTES
from core.storage import sanitize_site

log = logging.getLogger("hub.forwarder")


def _explain(status: int) -> str:
    """Turn an HTTP status into something a store manager can act on.

    The Settings page shows this verbatim. "upstream POST -> 401" is a log line;
    "head office rejected the token" is a thing someone can go fix.
    """
    if not status:
        return ("Could not reach head office — check the address, and that the "
                "head-office hub is running and its firewall allows the port.")
    if status == 401:
        return "Head office rejected the token — check it matches head office's device token."
    if status == 404:
        return "Head office answered, but not with a Setpoint hub — check the address."
    if status == 413:
        return "Batch too large for head office — lower the rows-per-send."
    if 300 <= status < 400:
        return ("Something on the network answered with a redirect instead of head "
                "office — check the address (use the one it redirects to, usually "
                "the https:// form), and whether a captive portal or proxy sits in "
                "between.")
    if 500 <= status < 600:
        return f"Head office returned an error ({status}) — it may be starting up or overloaded."
    return f"Head office refused the readings (HTTP {status})."


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse to chase ``Location`` on an upstream POST.

    Forwarding targets one fixed, operator-configured endpoint, so a 3xx is
    never head office answering. Following it costs two things, and both are
    silent:

    * ``HTTPRedirectHandler`` copies every header except the content ones onto
      the new request with no same-origin test, so ``X-Token`` — head office's
      device token — is replayed at whatever host ``Location`` names, on any
      scheme or port. ``upstream.url`` is frequently plain ``http://``, so
      anything on the path can inject that redirect.
    * For 301/302/303 it rebuilds the request as a bodiless GET. The batch is
      dropped, and if the redirect target answers 2xx (a captive portal, an SPA
      catch-all, a proxy interstitial) :meth:`_run_once_locked` reads that as
      delivery and advances BOTH cursors past readings and events that were
      never sent — a permanent hole in the record, which is the one outcome
      this module's docstring stakes itself on avoiding.

    Returning ``None`` makes ``OpenerDirector`` fall through to
    ``HTTPDefaultErrorHandler``, which raises ``HTTPError`` — so ``post_batch``
    reports the real 3xx, the cursor holds and the backoff engages.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)

_HWM_KEY = "forwarder.last_id"
_EVENTS_KEY = "forwarder.last_event_id"

DEFAULT_INTERVAL_SEC = 30
DEFAULT_BATCH = 500          # PROTOCOL caps /ingest_csv at 1000 rows/request
MAX_BATCH = MAX_BATCH_ROWS
# The row limit is not the binding one — the receiver also refuses a body over
# MAX_INGEST_BYTES. Leave headroom under it for the request line and headers
# rather than aiming at the exact ceiling. See fit_batch.
MAX_FORWARD_BODY_BYTES = MAX_INGEST_BYTES - 1024
_BACKOFF_START = 5
_BACKOFF_MAX = 300


@dataclass(frozen=True)
class _CycleResult:
    """Outcome needed by the thread wrapper without rereading cycle config."""

    readings_sent: int = 0
    full_batch: bool = False
    # Did a request actually complete with a 2xx? Distinct from readings_sent,
    # which is 0 both when nothing was queued (no request made, nothing proved)
    # and when an events-only batch landed. Settings' Save needs the difference:
    # it reported "connected to head office" off a cycle that short-circuited
    # before any HTTP at all, so an unreachable address or a wrong token looked
    # like a working one.
    posted: bool = False


def _cfg_block(cfg) -> dict:
    try:
        block = cfg.get("upstream") or {}
    except Exception:  # noqa: BLE001
        return {}
    return block if isinstance(block, dict) else {}


def batch_size(block: dict) -> int:
    """Rows (and events) per upstream request, clamped to the protocol's 1..1000.

    One definition, so the limit the cycle reads with and the limit it judges
    "was this batch full?" against cannot drift — that pair disagreeing is what
    made a configured batch below the default drain a backlog at one batch per
    interval (see :class:`_CycleResult` and ``run``).
    """
    try:
        return max(1, min(int(block.get("batch") or DEFAULT_BATCH), MAX_BATCH))
    except (TypeError, ValueError):
        return DEFAULT_BATCH


def rows_to_payload(rows) -> list:
    """Shape ``db.rows_after()`` tuples into the JSON body ``/ingest_csv`` takes.

    Column order matches the SELECT in ``Database.rows_after``. ``id`` is dropped
    — it is this hub's cursor, meaningless to the receiver, whose own autoincrement
    numbers its copy independently. ``vpd`` is dropped too, and deliberately: the
    receiving hub recomputes it from temperature + humidity at ingest, using ITS
    own ``vpd_leaf_offset_c``, so sending ours would be overwritten anyway.

    The timestamp on the wire is the row's ``epoch`` rendered as UTC, NOT the
    stored ``ts``. ``ts`` is local-naive — one hub, one timezone — and carries no
    marker saying which one, so head office in a different zone re-read it as its
    own wall clock and shifted every forwarded reading by the offset between
    them (see :func:`core.storage.absolute_epoch`, which exists for exactly this
    and which the receiver already honours for a ``Z``-suffixed stamp). A store
    to the east also tripped the receiver's future-stamp guard and had its whole
    batch re-stamped to arrival time. The epoch is the instant the store hub
    already established; sending it unambiguously is all that was missing.
    """
    out = []
    for r in rows:
        _id, ts, epoch, t_c, t_f, pid, hum, _vpd, bat = r
        row = {"timestamp": _wire_stamp(ts, epoch), "temperature_c": t_c,
               "temperature_f": t_f, "probe_id": pid}
        if hum is not None:
            row["humidity_pct"] = hum
        if bat is not None:
            row["battery_pct"] = bat
        out.append(row)
    return out


def events_to_payload(rows) -> list:
    """Shape ``db.events_after()`` tuples into the ``events`` array ``/ingest_csv``
    accepts. Column order matches the SELECT in ``Database.events_after``; the
    local id is dropped for the same reason readings drop theirs.

    Events carry the true instant as a SEPARATE ``epoch`` field and leave
    ``timestamp`` as the store's local-naive string, where readings send UTC.
    The asymmetry is deliberate and it is about the previous release: a hub
    running it already recovers a ``Z``-suffixed reading stamp correctly
    (``ingest_csv`` has called ``absolute_epoch`` on readings for some time),
    but its ``record_event`` derives the epoch with ``iso_to_epoch``, which
    strips the ``Z`` and reads the result as LOCAL. Sending UTC here would have
    skewed forwarded events on an older head office by its whole UTC offset —
    including on the same-timezone deployments that were previously correct.
    An extra field is ignored by that build and honoured by this one, so the
    fix costs nothing during a rollout.
    """
    out = []
    for _id, ts, epoch, kind, pid, t_c, limit_c in rows:
        ev = {"timestamp": ts, "kind": kind, "probe_id": pid}
        if epoch is not None:
            ev["epoch"] = epoch
        if t_c is not None:
            ev["temperature_c"] = t_c
        if limit_c is not None:
            ev["limit_c"] = limit_c
        out.append(ev)
    return out


def _wire_stamp(ts, epoch) -> str:
    """The unambiguous instant for one forwarded record.

    Falls back to the stored local-naive string only if the row somehow has no
    usable epoch — an ambiguous stamp still beats no stamp, and the receiver
    treats a naive one exactly as it always did.
    """
    try:
        return utc_iso(epoch)
    except (TypeError, ValueError, OSError, OverflowError):
        return ts


def batch_body(rows, events=()) -> bytes:
    """Exactly the JSON bytes one upstream request carries.

    Shared by :func:`post_batch` and :func:`fit_batch` so the size that is
    measured is the size that is sent.
    """
    payload = {"readings": rows_to_payload(rows)}
    if events:
        payload["events"] = events_to_payload(events)
    return json.dumps(payload).encode("utf-8")


def fit_batch(rows, events, max_bytes: int = MAX_FORWARD_BODY_BYTES):
    """Trim a batch to PREFIXES whose encoded request fits ``max_bytes``.

    The receiver rejects any body over ``MAX_INGEST_BYTES`` with a 413, and a row
    limit alone cannot honour a byte limit: 500 readings (the default) encode to
    ~62 KB of the 63.5 KB budget with a bare temperature, and to ~92 KB once a
    grow probe adds humidity and battery — so the shipped default already 413s
    forever for the probes that report most. At the configured maximum of 1000 it
    413s for every deployment. Nothing retries its way out of that: the same
    bytes are rebuilt every cycle, so forwarding simply stops.

    Trimming from the END only is what keeps this safe. Both cursors advance to
    the last id actually accepted, so dropping from anywhere but the tail would
    step the cursor past records that were never sent — a permanent hole in a
    food-safety record, which is the one outcome worth more than throughput.

    Readings shrink first: they are the bulk, and events are the record an
    auditor asks for. Binary search rather than popping one at a time — the
    obvious loop re-encodes the whole payload per pop, which measured 480 encodes
    and 0.5 s of CPU per cycle at a 1000-row batch, burned on the forwarder
    thread every interval forever.

    Returns ``(rows, events)``; ``([], [])`` only when a single record exceeds the
    budget on its own, which the caller reports rather than skipping.
    """
    def fits(r, e):
        return len(batch_body(r, e)) <= max_bytes

    rows, events = list(rows), list(events)
    if fits(rows, events):
        return rows, events

    def largest_prefix(seq, build):
        lo, hi = 0, len(seq)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if fits(*build(mid)):
                lo = mid
            else:
                hi = mid - 1
        return lo

    keep = largest_prefix(rows, lambda n: (rows[:n], events))
    if keep:
        return rows[:keep], events
    # Not even one reading fits alongside the events — shrink the events instead.
    keep_ev = largest_prefix(events, lambda n: ([], events[:n]))
    return [], events[:keep_ev]


def post_batch(url: str, token: str, site: str, rows, events=(), timeout: float = 20.0) -> int:
    """POST one batch upstream. Returns the HTTP status, or 0 on transport error.

    Readings and events ride the same request: one round trip, and either both
    land or neither does, so the two cursors can advance together.
    """
    body = batch_body(rows, events)
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Token", token)
    if site:
        req.add_header("X-Site", site)
    try:
        # _OPENER, not urlopen: the default opener follows redirects, which leaks
        # the token and eats the batch. See _NoRedirect.
        with _OPENER.open(req, timeout=timeout) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as e:
        return int(e.code)
    except Exception:  # noqa: BLE001 - transport failure; caller backs off
        return 0


def ingest_url(base: str) -> str:
    base = (base or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/api/ingest_csv"):
        return base
    return base + "/api/ingest_csv"


class UpstreamForwarder(threading.Thread):
    """Background pump: local readings -> an aggregating hub."""

    def __init__(self, db, cfg, stop_event: threading.Event | None = None):
        super().__init__(name="upstream-forwarder", daemon=True)
        self.db = db
        self.cfg = cfg
        self.stop_event = stop_event or threading.Event()
        self._backoff = 0
        # Settings can ask for a cycle on demand (so "Save" reports a real
        # result instead of a hopeful one) while the pump thread is mid-cycle.
        # Two concurrent cycles would read the same high-water mark and post the
        # same batch twice — harmless upstream thanks to INSERT OR IGNORE, but
        # it doubles the traffic and muddles the status, so serialise them.
        self._cycle_lock = threading.Lock()
        self.last_error = ""       # human-readable, for the Settings status line
        self.last_sent_epoch = 0.0

    # -- one cycle, exposed so tests can drive it without a thread ------------
    def run_once(self) -> int:
        """Forward at most one batch. Returns rows accepted upstream (0 if idle)."""
        with self._cycle_lock:
            return self._run_once_locked().readings_sent

    def run_once_detailed(self) -> _CycleResult:
        """One cycle, with whether a request actually completed — see
        :class:`_CycleResult`.``posted``. ``run_once`` stays as the row count
        every existing caller wants."""
        with self._cycle_lock:
            return self._run_once_locked()

    def _run_once_locked(self) -> _CycleResult:
        block = _cfg_block(self.cfg)
        if not block.get("enabled"):
            return _CycleResult()
        url = ingest_url(block.get("url"))
        if not url:
            self.last_error = "No head-office address set."
            log.warning("upstream.enabled is set but upstream.url is empty; nothing to do")
            return _CycleResult()
        # Sanitise to the charset the RECEIVER will apply (it calls sanitize_site
        # on the X-Site header). A label with no ASCII alphanumerics — "東京店",
        # "###" — survives this check as truthy but arrives at head office as the
        # empty string, which is the marker for "ingested locally HERE": those
        # rows are then judged by HQ's own thresholds, swept by HQ's own alert
        # monitor, and forwarded onward by HQ's own local_only cursor. Refusing
        # here also keeps a non-latin-1 label from failing as a fake network
        # outage when urllib encodes the header.
        raw_site = str(block.get("site") or "").strip()
        site = sanitize_site(raw_site)
        if not site:
            # Without a site label HQ cannot tell this store's readings from any
            # other's. Refuse rather than silently pooling six stores into one
            # anonymous heap that no later migration can separate.
            self.last_error = (
                "No site name set." if not raw_site else
                "Site name has no letters, digits, '-' or '_' — head office cannot "
                "tell this store's readings apart. Rename it.")
            log.warning("upstream.enabled is set but upstream.site (%r) is empty or "
                        "sanitises away; refusing to forward", raw_site)
            return _CycleResult()
        batch = batch_size(block)

        last = self._cursor(_HWM_KEY)
        last_ev = self._cursor(_EVENTS_KEY)
        rows = self.db.rows_after(last, limit=batch)
        events = self.db.events_after(last_ev, limit=batch)
        if not rows and not events:
            self._backoff = 0
            self.last_error = ""
            return _CycleResult()

        # The row limit alone cannot honour the receiver's byte limit — see
        # fit_batch. Trim to prefixes that will actually be accepted, before
        # spending a round trip on bytes that can only come back 413.
        wanted_rows, wanted_events = len(rows), len(events)
        rows, events = fit_batch(rows, events)
        if not rows and not events:
            # A single record larger than a whole request. Unreachable through
            # the sanitised ingest path (probe ids cap at 32 chars), so this
            # means a hand-edited row. Stall loudly rather than skipping it: a
            # gap in the record is worse than a stopped forwarder, and `pending`
            # climbing beside this message in Diagnostics is the diagnosis.
            self._backoff = _BACKOFF_MAX
            self.last_error = ("A single reading or event is too large to forward. "
                               "Forwarding is stopped until it is removed.")
            log.error("upstream: the record after reading id=%d / event id=%d exceeds "
                      "the %d-byte request budget on its own; forwarding is stalled",
                      last, last_ev, MAX_FORWARD_BODY_BYTES)
            return _CycleResult()
        if len(rows) < wanted_rows or len(events) < wanted_events:
            log.debug("upstream: batch trimmed to fit %d bytes — %d/%d readings, "
                      "%d/%d events", MAX_FORWARD_BODY_BYTES, len(rows), wanted_rows,
                      len(events), wanted_events)

        status = post_batch(url, str(block.get("token") or ""), site, rows, events)
        if 200 <= status < 300:
            # Both cursors advance together, because one request carried both.
            if rows:
                self.db.meta_set(_HWM_KEY, str(rows[-1][0]))
            if events:
                self.db.meta_set(_EVENTS_KEY, str(events[-1][0]))
            self._backoff = 0
            self.last_error = ""
            self.last_sent_epoch = time.time()
            log.info("forwarded %d readings, %d events to %s as site=%s",
                     len(rows), len(events), url, site)
            # Each cursor has its own limit. Either collection filling that
            # limit means its cursor may have more work immediately available —
            # judged on what was READ, not what survived fit_batch, or a batch
            # trimmed for size would look partial and sleep a whole interval
            # while the rows it just dropped were still waiting.
            return _CycleResult(len(rows),
                                wanted_rows >= batch or wanted_events >= batch
                                or len(rows) < wanted_rows
                                or len(events) < wanted_events,
                                posted=True)

        # 4xx means the request itself is wrong (bad token, malformed body).
        # Retrying identical bytes will not fix it, so keep the cursor and let the
        # warning stand rather than hammering an upstream that is telling us no.
        self._backoff = min(_BACKOFF_MAX, (self._backoff or _BACKOFF_START) * 2)
        self.last_error = _explain(status)
        log.warning("upstream POST %s -> %s; %d readings held, retrying in %ds",
                    url, status or "no response", len(rows), self._backoff)
        return _CycleResult()

    def _cursor(self, key: str) -> int:
        try:
            return int(self.db.meta_get(key, "0") or 0)
        except (TypeError, ValueError):
            return 0

    def pending(self) -> int:
        """Local readings not yet accepted upstream — the backlog, for the UI."""
        try:
            return max(0, self.db.count_local_after(self._cursor(_HWM_KEY)))
        except Exception:  # noqa: BLE001 - a status readout must never raise
            return 0

    def run(self) -> None:  # pragma: no cover - thread wrapper
        log.info("upstream forwarder started")
        while not self.stop_event.is_set():
            try:
                with self._cycle_lock:
                    result = self._run_once_locked()
            except Exception:  # noqa: BLE001 - a pump must not die on one bad cycle
                log.exception("forwarder cycle failed")
                result = _CycleResult()
                self._backoff = min(_BACKOFF_MAX, (self._backoff or _BACKOFF_START) * 2)
            block = _cfg_block(self.cfg)
            try:
                interval = int(block.get("interval_sec") or DEFAULT_INTERVAL_SEC)
            except (TypeError, ValueError):
                interval = DEFAULT_INTERVAL_SEC
            # A full batch means there is more waiting — drain promptly instead of
            # sleeping a full interval per batch, or a big backlog takes hours.
            # "Full" is decided by the cycle itself (see _CycleResult), for two
            # reasons the caller cannot see. It compares against the CONFIGURED
            # batch, not DEFAULT_BATCH — with upstream.batch below 500 a full
            # batch could never reach the constant, so the fast-drain never
            # engaged and a hub back from an outage caught up at one batch per
            # interval. And it counts EITHER cursor: readings and events have
            # separate limits, and an events-only backlog is not a corner case —
            # offline events fire precisely when readings have stopped arriving.
            delay = self._backoff or (1 if result.full_batch else max(5, interval))
            self.stop_event.wait(delay)

    def stop(self) -> None:
        self.stop_event.set()


class _ForwarderHandle:
    """Process-wide handle so Settings can drive the pump without a restart.

    The thread is started unconditionally at boot and no-ops while
    ``upstream.enabled`` is false (one dict lookup every 30 s). That is what lets
    someone switch forwarding on in Settings and have it work, instead of saving
    a setting that quietly does nothing until the hub is restarted — which is
    exactly the kind of thing that gets diagnosed as "the feature is broken".
    """

    def __init__(self):
        self._fwd = None

    def start(self, db, cfg) -> None:
        if self._fwd is not None:
            return
        self._fwd = UpstreamForwarder(db, cfg)
        self._fwd.start()

    def stop(self) -> None:
        if self._fwd is not None:
            self._fwd.stop()
            self._fwd = None

    def is_alive(self) -> bool:
        """Is the pump thread running? Mirrors ``threading.Thread`` so the health
        worker registry can watch this handle like any other background thread —
        it is the thread's public face everywhere else, so it should be here too
        rather than making the registry special-case one caller."""
        return self._fwd is not None and self._fwd.is_alive()

    def sync_now(self) -> tuple:
        """Force one cycle. Returns ``(rows_sent, error_text)`` for the UI."""
        return self.sync_now_detailed()[:2]

    def sync_now_detailed(self) -> tuple:
        """Force one cycle. Returns ``(rows_sent, error_text, contacted)``.

        ``contacted`` is what tells "head office answered" apart from "there was
        nothing to send, so nobody was asked" — the two cases the two-value form
        collapses into ``(0, "")``.
        """
        if self._fwd is None:
            return 0, "Forwarding is not running on this hub.", False
        try:
            result = self._fwd.run_once_detailed()
        except Exception as e:  # noqa: BLE001 - surfaced to the operator, not raised
            return 0, str(e), False
        return result.readings_sent, self._fwd.last_error, result.posted

    def status(self) -> dict:
        """Backlog, last success and last error — the three things both callers
        want together. Diagnostics renders all of it; Settings uses ``pending``.

        Safe on a hub where the pump never started: every value is its
        nothing-has-happened default rather than an absence to guard against.
        """
        if self._fwd is None:
            return {"pending": 0, "last_sent_epoch": 0.0, "last_error": ""}
        return {"pending": self._fwd.pending(),
                "last_sent_epoch": self._fwd.last_sent_epoch,
                "last_error": self._fwd.last_error}


FORWARDER = _ForwarderHandle()

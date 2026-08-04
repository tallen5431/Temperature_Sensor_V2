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

from core.protocol import MAX_BATCH_ROWS, MAX_INGEST_BYTES

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
    if 500 <= status < 600:
        return f"Head office returned an error ({status}) — it may be starting up or overloaded."
    return f"Head office refused the readings (HTTP {status})."

_HWM_KEY = "forwarder.last_id"
_EVENTS_KEY = "forwarder.last_event_id"

DEFAULT_INTERVAL_SEC = 30
DEFAULT_BATCH = 500          # PROTOCOL caps /ingest_csv at 1000 rows/request
MAX_BATCH = MAX_BATCH_ROWS
# Stay comfortably below the receiver's hard ceiling.  Besides allowing for a
# proxy to re-encode JSON, this makes the strict "fits below" contract explicit.
MAX_FORWARD_BODY_BYTES = MAX_INGEST_BYTES - 1024
_BACKOFF_START = 5
_BACKOFF_MAX = 300


def _cfg_block(cfg) -> dict:
    try:
        block = cfg.get("upstream") or {}
    except Exception:  # noqa: BLE001
        return {}
    return block if isinstance(block, dict) else {}


def rows_to_payload(rows) -> list:
    """Shape ``db.rows_after()`` tuples into the JSON body ``/ingest_csv`` takes.

    Column order matches the SELECT in ``Database.rows_after``. ``id`` is dropped
    — it is this hub's cursor, meaningless to the receiver, whose own autoincrement
    numbers its copy independently.
    """
    out = []
    for r in rows:
        _id, ts, _epoch, t_c, t_f, pid, hum, vpd, bat = r
        row = {"timestamp": ts, "temperature_c": t_c,
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
    local id is dropped for the same reason readings drop theirs."""
    out = []
    for _id, ts, _epoch, kind, pid, t_c, limit_c in rows:
        ev = {"timestamp": ts, "kind": kind, "probe_id": pid}
        if t_c is not None:
            ev["temperature_c"] = t_c
        if limit_c is not None:
            ev["limit_c"] = limit_c
        out.append(ev)
    return out


def _batch_body(rows, events=()) -> bytes:
    """Return exactly the JSON bytes used for an upstream request."""
    payload = {"readings": rows_to_payload(rows)}
    if events:
        payload["events"] = events_to_payload(events)
    return json.dumps(payload).encode("utf-8")


def _fit_batch(rows, events, max_bytes=MAX_FORWARD_BODY_BYTES):
    """Select cursor-safe prefixes whose encoded request fits ``max_bytes``.

    Removing only from the ends is important: advancing a cursor through a
    non-prefix would permanently skip the omitted records.
    """
    rows, events = list(rows), list(events)
    while rows or events:
        if len(_batch_body(rows, events)) <= max_bytes:
            return rows, events
        # Preserve a useful mix when both queues are populated, while converging
        # quickly for large batches.
        if len(rows) >= len(events) and rows:
            rows.pop()
        elif events:
            events.pop()
    return rows, events


def post_batch(url: str, token: str, site: str, rows, events=(), timeout: float = 20.0) -> int:
    """POST one batch upstream. Returns the HTTP status, or 0 on transport error.

    Readings and events ride the same request: one round trip, and either both
    land or neither does, so the two cursors can advance together.
    """
    body = _batch_body(rows, events)
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Token", token)
    if site:
        req.add_header("X-Site", site)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
            return self._run_once_locked()

    def _run_once_locked(self) -> int:
        block = _cfg_block(self.cfg)
        if not block.get("enabled"):
            return 0
        url = ingest_url(block.get("url"))
        if not url:
            self.last_error = "No head-office address set."
            log.warning("upstream.enabled is set but upstream.url is empty; nothing to do")
            return 0
        site = str(block.get("site") or "").strip()
        if not site:
            # Without a site label HQ cannot tell this store's readings from any
            # other's. Refuse rather than silently pooling six stores into one
            # anonymous heap that no later migration can separate.
            self.last_error = "No site name set."
            log.warning("upstream.enabled is set but upstream.site is empty; refusing to forward")
            return 0
        batch = max(1, min(int(block.get("batch") or DEFAULT_BATCH), MAX_BATCH))

        last = self._cursor(_HWM_KEY)
        last_ev = self._cursor(_EVENTS_KEY)
        rows = self.db.rows_after(last, limit=batch)
        events = self.db.events_after(last_ev, limit=batch)
        if not rows and not events:
            self._backoff = 0
            self.last_error = ""
            return 0

        rows, events = _fit_batch(rows, events)
        if not rows and not events:
            self._backoff = _BACKOFF_MAX
            self.last_error = ("The next reading or event is too large to forward; "
                               "shorten its probe ID or event fields, or remove/quarantine the record.")
            log.error("upstream record after reading id=%d/event id=%d exceeds %d bytes",
                      last, last_ev, MAX_FORWARD_BODY_BYTES)
            return 0

        token = str(block.get("token") or "")
        status = post_batch(url, token, site, rows, events)
        # A receiver/proxy may enforce a smaller limit than this version knows.
        # Reduce cursor-safe prefixes immediately rather than retrying identical
        # bytes on every cycle.
        while status == 413 and len(rows) + len(events) > 1:
            target_count = max(1, (len(rows) + len(events)) // 2)
            while len(rows) + len(events) > target_count:
                if len(rows) >= len(events) and rows:
                    rows.pop()
                elif events:
                    events.pop()
            status = post_batch(url, token, site, rows, events)
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
            return len(rows)

        # 4xx means the request itself is wrong (bad token, malformed body).
        # Retrying identical bytes will not fix it, so keep the cursor and let the
        # warning stand rather than hammering an upstream that is telling us no.
        self._backoff = min(_BACKOFF_MAX, (self._backoff or _BACKOFF_START) * 2)
        self.last_error = (_explain(status) if status != 413 else
                           "The next reading or event is too large for head office; "
                           "remove or quarantine that record before retrying.")
        log.warning("upstream POST %s -> %s; %d readings held, retrying in %ds",
                    url, status or "no response", len(rows), self._backoff)
        return 0

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
                sent = self.run_once()
            except Exception:  # noqa: BLE001 - a pump must not die on one bad cycle
                log.exception("forwarder cycle failed")
                sent = 0
                self._backoff = min(_BACKOFF_MAX, (self._backoff or _BACKOFF_START) * 2)
            block = _cfg_block(self.cfg)
            interval = int(block.get("interval_sec") or DEFAULT_INTERVAL_SEC)
            # A full batch means there is more waiting — drain promptly instead of
            # sleeping a full interval per batch, or a big backlog takes hours.
            delay = self._backoff or (1 if sent >= DEFAULT_BATCH else max(5, interval))
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

    def sync_now(self) -> tuple:
        """Force one cycle. Returns ``(rows_sent, error_text)`` for the UI."""
        if self._fwd is None:
            return 0, "Forwarding is not running on this hub."
        try:
            sent = self._fwd.run_once()
        except Exception as e:  # noqa: BLE001 - surfaced to the operator, not raised
            return 0, str(e)
        return sent, self._fwd.last_error

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

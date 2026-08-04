"""Forward this hub's readings to another hub (multi-site roll-up).

A chain with six stores wants head office to see all six. The local-first
architecture is the product's whole point, so the answer is *not* a cloud: each
store keeps its own hub and its own database, and optionally **pushes a copy** of
its readings to an aggregating hub that head office runs.

The shape falls out of what already exists — a store hub forwarding to an HQ hub
is the same relationship a probe already has with a hub:

===========================  ==========================================
probe  ->  hub               store hub  ->  HQ hub
===========================  ==========================================
POST /api/ingest_csv         the same endpoint, unchanged
X-Token auth                 the same auth
buffers to flash when down   the backlog simply stays unsent
UNIQUE(probe_id, epoch)      the same index makes re-sends idempotent
===========================  ==========================================

That last row is what makes this safe. Because the receiving hub inserts with
``INSERT OR IGNORE`` against ``UNIQUE(probe_id, epoch)``, a batch re-sent after a
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

DEFAULT_INTERVAL_SEC = 30
DEFAULT_BATCH = 500          # PROTOCOL caps /ingest_csv at 1000 rows/request
MAX_BATCH = 1000
_BACKOFF_START = 5
_BACKOFF_MAX = 300


def _cfg_block(cfg) -> dict:
    try:
        block = cfg.get("upstream") or {}
    except Exception:  # noqa: BLE001
        return {}
    return block if isinstance(block, dict) else {}


def batch_size(block: dict) -> int:
    """Rows per upstream request, clamped to the protocol's 1..1000.

    Shared by the cycle that reads the batch and the pump that decides how long
    to sleep afterwards — those two disagreeing is what made a configured batch
    below the default drain a backlog at one batch per interval (see ``run``).
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
    """
    out = []
    for r in rows:
        _id, ts, _epoch, t_c, t_f, pid, hum, _vpd, bat = r
        row = {"timestamp": ts, "temperature_c": t_c,
               "temperature_f": t_f, "probe_id": pid}
        if hum is not None:
            row["humidity_pct"] = hum
        if bat is not None:
            row["battery_pct"] = bat
        out.append(row)
    return out


def post_batch(url: str, token: str, site: str, rows, timeout: float = 20.0) -> int:
    """POST one batch upstream. Returns the HTTP status, or 0 on transport error."""
    body = json.dumps({"readings": rows_to_payload(rows)}).encode("utf-8")
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
        batch = batch_size(block)

        try:
            last = int(self.db.meta_get(_HWM_KEY, "0") or 0)
        except (TypeError, ValueError):
            last = 0
        rows = self.db.rows_after(last, limit=batch)
        if not rows:
            self._backoff = 0
            self.last_error = ""
            return 0

        status = post_batch(url, str(block.get("token") or ""), site, rows)
        if 200 <= status < 300:
            self.db.meta_set(_HWM_KEY, str(rows[-1][0]))
            self._backoff = 0
            self.last_error = ""
            self.last_sent_epoch = time.time()
            log.info("forwarded %d readings to %s as site=%s", len(rows), url, site)
            return len(rows)

        # 4xx means the request itself is wrong (bad token, malformed body).
        # Retrying identical bytes will not fix it, so keep the cursor and let the
        # warning stand rather than hammering an upstream that is telling us no.
        self._backoff = min(_BACKOFF_MAX, (self._backoff or _BACKOFF_START) * 2)
        self.last_error = _explain(status)
        log.warning("upstream POST %s -> %s; %d readings held, retrying in %ds",
                    url, status or "no response", len(rows), self._backoff)
        return 0

    def pending(self) -> int:
        """Local readings not yet accepted upstream — the backlog, for the UI."""
        try:
            last = int(self.db.meta_get(_HWM_KEY, "0") or 0)
            return max(0, self.db.count_local_after(last))
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
            try:
                interval = int(block.get("interval_sec") or DEFAULT_INTERVAL_SEC)
            except (TypeError, ValueError):
                interval = DEFAULT_INTERVAL_SEC
            # A full batch means there is more waiting — drain promptly instead of
            # sleeping a full interval per batch, or a big backlog takes hours.
            # Compared against the CONFIGURED batch, not DEFAULT_BATCH: with
            # upstream.batch set to anything below 500 a full batch could never
            # reach the constant, so the fast-drain never engaged and a hub coming
            # back from a long outage caught up at one batch per interval.
            delay = self._backoff or (1 if sent >= batch_size(block) else max(5, interval))
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

    def pending(self) -> int:
        return self._fwd.pending() if self._fwd is not None else 0

    def last_sent_epoch(self) -> float:
        return self._fwd.last_sent_epoch if self._fwd is not None else 0.0

    def last_error(self) -> str:
        return self._fwd.last_error if self._fwd is not None else ""


FORWARDER = _ForwarderHandle()

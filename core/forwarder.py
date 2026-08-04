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
import urllib.error
import urllib.request

log = logging.getLogger("hub.forwarder")

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

    # -- one cycle, exposed so tests can drive it without a thread ------------
    def run_once(self) -> int:
        """Forward at most one batch. Returns rows accepted upstream (0 if idle)."""
        block = _cfg_block(self.cfg)
        if not block.get("enabled"):
            return 0
        url = ingest_url(block.get("url"))
        if not url:
            log.warning("upstream.enabled is set but upstream.url is empty; nothing to do")
            return 0
        site = str(block.get("site") or "").strip()
        if not site:
            # Without a site label HQ cannot tell this store's readings from any
            # other's. Refuse rather than silently pooling six stores into one
            # anonymous heap that no later migration can separate.
            log.warning("upstream.enabled is set but upstream.site is empty; refusing to forward")
            return 0
        batch = max(1, min(int(block.get("batch") or DEFAULT_BATCH), MAX_BATCH))

        try:
            last = int(self.db.meta_get(_HWM_KEY, "0") or 0)
        except (TypeError, ValueError):
            last = 0
        rows = self.db.rows_after(last, limit=batch)
        if not rows:
            self._backoff = 0
            return 0

        status = post_batch(url, str(block.get("token") or ""), site, rows)
        if 200 <= status < 300:
            self.db.meta_set(_HWM_KEY, str(rows[-1][0]))
            self._backoff = 0
            log.info("forwarded %d readings to %s as site=%s", len(rows), url, site)
            return len(rows)

        # 4xx means the request itself is wrong (bad token, malformed body).
        # Retrying identical bytes will not fix it, so keep the cursor and let the
        # warning stand rather than hammering an upstream that is telling us no.
        self._backoff = min(_BACKOFF_MAX, (self._backoff or _BACKOFF_START) * 2)
        log.warning("upstream POST %s -> %s; %d readings held, retrying in %ds",
                    url, status or "no response", len(rows), self._backoff)
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

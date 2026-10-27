"""Outbound "the hub is alive" ping, for the one failure the hub cannot report.

Every alarm Setpoint raises — out of range, probe silent — is raised BY the hub.
If the PC it runs on crashes, loses power, sleeps, or gets rebooted by Windows
Update with nobody signed in, those alarms stop silently: no email says "I am
gone". For a product sold as loss prevention that is the failure that loses the
freezer.

The answer is a dead man's switch held by somebody else: the hub requests a URL
every few minutes, and an outside service (healthchecks.io, or a self-hosted
Uptime Kuma "push" monitor) alerts the customer when the requests stop. Off by
default and nothing is sent until a URL is entered, so "nothing phones home"
stays true for anyone who does not ask for this.

A ping means the hub is DOING ITS JOB, not merely that the process exists. It is
sent from the alert monitor's own loop, only after a cycle that completed
cleanly, and never while database writes are failing — so a wedged monitor or a
full disk stops the pings exactly as a dead PC does.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional
from urllib.parse import urlsplit

import requests

log = logging.getLogger("hub.heartbeat")

DEFAULT_INTERVAL_SEC = 300
MIN_INTERVAL_SEC = 60
TIMEOUT_SEC = 10


def heartbeat_settings(cfg) -> tuple:
    """``(url, interval_sec)`` when the heartbeat is on and usable, else ``(None, 0)``."""
    hb = cfg.get("heartbeat", {}) or {}
    url = str(hb.get("url") or "").strip()
    if not hb.get("enabled") or not valid_heartbeat_url(url):
        return None, 0
    try:
        interval = int(hb.get("interval_sec", DEFAULT_INTERVAL_SEC))
    except (TypeError, ValueError):
        interval = DEFAULT_INTERVAL_SEC
    return url, max(MIN_INTERVAL_SEC, interval)


def valid_heartbeat_url(url: str) -> bool:
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.hostname)


def ping(url: str) -> tuple:
    """One request to ``url``. ``(ok, detail)``; never raises, never echoes the URL.

    The URL is a secret — on healthchecks.io the path IS the credential, and
    anyone holding it can send pings that mask an outage — so failures name the
    host and the exception type only, the same rule send_webhook follows.
    """
    host = urlsplit(url).hostname or "the heartbeat host"
    try:
        r = requests.get(url, timeout=TIMEOUT_SEC)
        if r.ok:
            return True, f"ok ({host})"
        return False, f"HTTP {r.status_code} from {host}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__} contacting {host}"


# The running hub's instance, for the diagnostics readout. Set by app.py when it
# starts the alert monitor; None in tests and before startup.
CURRENT: "Optional[Heartbeat]" = None


def current_status(cfg) -> dict:
    """Diagnostics view of the heartbeat, whether or not the monitor is running."""
    if CURRENT is not None:
        return CURRENT.status()
    url, interval = heartbeat_settings(cfg)
    return {"enabled": bool(url), "interval_sec": interval or None,
            "host": urlsplit(url).hostname if url else None,
            "last_ok_age_sec": None, "last_result": None}


class Heartbeat:
    """Rate-limits pings and runs each one off the caller's thread.

    The monitor loop calls :meth:`tick` once per clean cycle. A black-holed
    heartbeat host must not delay threshold evaluation, so the request runs on a
    short-lived daemon thread, and a tick while one is still in flight does
    nothing rather than stacking another.
    """

    def __init__(self, cfg, health=None, clock=time.time, spawn=None):
        self.cfg = cfg
        self.health = health
        self._clock = clock
        self._spawn = spawn or self._thread
        self._lock = threading.Lock()
        self._inflight = False
        self._last_attempt: Optional[float] = None
        self.last_ok: Optional[float] = None
        self.last_result: Optional[tuple] = None

    @staticmethod
    def _thread(fn):
        threading.Thread(target=fn, name="heartbeat", daemon=True).start()

    def tick(self) -> bool:
        """Start a ping if one is due. Returns True when one was started."""
        url, interval = heartbeat_settings(self.cfg)
        if not url:
            return False
        if self.health is not None and self.health.write_failing():
            log.warning("heartbeat withheld: database writes are failing")
            return False
        now = self._clock()
        with self._lock:
            if self._inflight:
                return False
            if self._last_attempt is not None and now - self._last_attempt < interval:
                return False
            self._inflight = True
            self._last_attempt = now
        self._spawn(lambda: self._run(url))
        return True

    def _run(self, url: str) -> None:
        try:
            ok, detail = ping(url)
            self.last_result = (ok, detail)
            if ok:
                self.last_ok = self._clock()
            else:
                log.warning("heartbeat ping failed: %s", detail)
        finally:
            with self._lock:
                self._inflight = False

    def status(self) -> dict:
        """Secret-free summary for diagnostics: on/off, last outcome, its age."""
        url, interval = heartbeat_settings(self.cfg)
        age = None if self.last_ok is None else round(self._clock() - self.last_ok, 1)
        return {"enabled": bool(url), "interval_sec": interval or None,
                "host": urlsplit(url).hostname if url else None,
                "last_ok_age_sec": age,
                "last_result": self.last_result[1] if self.last_result else None}

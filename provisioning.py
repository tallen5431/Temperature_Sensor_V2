from __future__ import annotations
import logging
import requests, socket, threading
from typing import Optional

log = logging.getLogger("hub.provisioning")


def resolve_host(host: str, timeout: float = 3.0) -> Optional[str]:
    """Resolve a hostname to an IPv4 string with a HARD timeout, or None.

    ``socket.gethostbyname`` ignores the socket default timeout and blocks on the
    OS resolver — on a host without a working mDNS/NSS resolver, resolving a
    ``.local`` name can hang for tens of seconds. These functions run on Flask/
    waitress worker threads and the provisioner loop, so an unbounded resolve
    could exhaust the worker pool and hang the dashboard. Running it in a daemon
    thread with ``join(timeout)`` bounds the wait. An IP literal returns quickly.
    """
    host = (host or "").rstrip(".")
    if not host:
        return None
    result: list = [None]

    def _do():
        try:
            result[0] = socket.gethostbyname(host)
        except Exception:
            pass

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout)
    return result[0]


def get_probe_status(base_host: str, port: int, timeout: float = 3.0) -> Optional[dict]:
    """GET /status from a probe. Returns parsed JSON dict or None on failure.

    Resolves to an IP first (bounded) and requests by IP, so an unresolvable
    ``.local`` name fails fast instead of blocking the worker thread inside
    ``requests``' own getaddrinfo (which the request timeout does not bound).
    """
    ip = resolve_host(base_host, timeout)
    if not ip:
        return None
    try:
        r = requests.get(f"http://{ip}:{port}/status", timeout=timeout)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None


def provision_probe(base_host: str, port: int, server_base: str, token: str = "",
                    interval_ms: int = 5000, timeout: float = 3.0) -> bool:
    """POST the hub's ingest URL + token + interval to a probe's /provision.

    Resolves the target to an IP with a bounded timeout and requests by IP, so a
    probe that can't be resolved fails fast rather than hanging the caller.
    """
    ip = resolve_host(base_host, timeout)
    if not ip:
        log.debug("provision: could not resolve %s", base_host)
        return False
    body = {
        "server_url": f"{server_base.rstrip('/')}/api/ingest",
        "token": token or "",
        "interval_ms": int(interval_ms),
    }
    try:
        r = requests.post(f"http://{ip}:{port}/provision", json=body, timeout=timeout)
        if r.ok:
            log.debug("provision %s OK", ip)
            return True
        log.debug("provision %s failed -> %s", ip, r.status_code)
    except Exception as e:
        log.debug("provision %s exception: %s", ip, e)
    return False

from __future__ import annotations
import logging
import requests, socket, threading
from typing import Optional

log = logging.getLogger("hub.provisioning")

# DS18B20 resolution is provisionable per probe: 9..12 bits (0.5 .. 0.0625 °C).
# 11 is the default (0.125 °C, ~375 ms conversion — 4x finer than 9-bit while
# still fitting the 500 ms minimum interval, which 12-bit's 750 ms would not).
RES_BITS_MIN, RES_BITS_MAX, RES_BITS_DEFAULT = 9, 12, 11


def clamp_resolution_bits(value, default: int = RES_BITS_DEFAULT) -> int:
    """Coerce a DS18B20 resolution to a valid integer in the 9..12-bit range."""
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return int(default)
    return max(RES_BITS_MIN, min(RES_BITS_MAX, n))


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
                    interval_ms: int = 5000, resolution_bits=None,
                    timeout: float = 3.0) -> bool:
    """POST the hub's ingest URL + token + interval to a probe's /provision.

    ``resolution_bits`` (9..12), when given, sets the probe's DS18B20 resolution;
    it's omitted from the payload when None so older callers/firmware are
    unaffected (an old probe ignores unknown fields; a hub that doesn't manage
    resolution simply doesn't send it).

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
    if resolution_bits is not None:
        body["resolution_bits"] = clamp_resolution_bits(resolution_bits)
    try:
        r = requests.post(f"http://{ip}:{port}/provision", json=body, timeout=timeout)
        if r.ok:
            log.debug("provision %s OK", ip)
            return True
        log.debug("provision %s failed -> %s", ip, r.status_code)
    except Exception as e:
        log.debug("provision %s exception: %s", ip, e)
    return False

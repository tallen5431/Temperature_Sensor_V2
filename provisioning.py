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


def desired_probe_config(cfg, probe_id: str) -> dict:
    """The interval / sensor resolution the hub wants this probe to be running.

    Single source of truth for "what should this probe be configured to",
    shared by the two delivery paths so they can never drift apart:

    * the auto-provisioner **pushes** it to the probe's ``POST /provision``, and
    * ``POST /api/ingest`` returns it so a probe can **pull** it.

    The pull path exists because push alone is unreliable for a deep-sleeping
    probe: it only serves its HTTP window for a few seconds every Nth wake, so
    on a long interval the hub almost never catches it awake and a settings
    change could sit undelivered indefinitely. The probe's own ingest POST, by
    contrast, happens every wake and always succeeds — so config rides home on
    the reply, at zero extra radio cost.

    Values mirror the provisioner: a per-probe ``probe_intervals`` override (in
    seconds) else the global ``interval_sec``; a per-probe ``probe_resolutions``
    override else the global ``resolution_bits``, clamped to the sensor's 9..12.
    """
    interval_ms = 5000
    try:
        interval_ms = int(float(cfg.get("interval_sec", 5) or 5) * 1000)
    except (TypeError, ValueError):
        pass
    if probe_id:
        try:
            override = (cfg.get("probe_intervals") or {}).get(probe_id)
            if override is not None:
                interval_ms = int(float(override) * 1000)
        except (TypeError, ValueError):
            pass
    interval_ms = max(500, interval_ms)   # the firmware's own floor

    try:
        global_res = cfg.get("resolution_bits", RES_BITS_DEFAULT)
        res_value = (cfg.get("probe_resolutions") or {}).get(probe_id, global_res) \
            if probe_id else global_res
        resolution_bits = clamp_resolution_bits(res_value)
    except Exception:  # noqa: BLE001 - config is user-editable; never break ingest
        resolution_bits = clamp_resolution_bits(None)

    return {"interval_ms": interval_ms, "resolution_bits": resolution_bits}

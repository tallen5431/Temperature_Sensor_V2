from __future__ import annotations
import ipaddress
import logging
from urllib.parse import urlsplit
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
                    timeout: float = 3.0, watch=None) -> bool:
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
    if watch is not None:
        # Sent even when the values are None: an explicit null is how a deleted
        # threshold disarms a probe that is still watching the old one. Omitting
        # the keys would leave it sampling every minute for a limit the hub no
        # longer holds. Older firmware ignores keys it doesn't know.
        body["alert_min_c"] = watch[0]
        body["alert_max_c"] = watch[1]
        body["sample_ms"] = int(watch[2] or 0)
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
    # Every conversion below is defensive: config.json is user-editable and
    # POST /api/config accepts arbitrary JSON, so a single bad value here (inf,
    # NaN, a 400-digit integer, a string) must not escape. This helper is on the
    # LIVE INGEST path now, so an exception would 500 every reading from every
    # probe and abort the provisioning cycle — one typo would take the fleet
    # down. OverflowError is caught explicitly: it is not a ValueError, and
    # float('inf') -> int() raises exactly that.
    interval_ms = 5000
    try:
        interval_ms = int(float(cfg.get("interval_sec", 5) or 5) * 1000)
    except (TypeError, ValueError, OverflowError):
        pass
    if probe_id:
        try:
            override = (cfg.get("probe_intervals") or {}).get(probe_id)
            if override is not None:
                interval_ms = int(float(override) * 1000)
        except (TypeError, ValueError, OverflowError):
            pass
    # Bound both ends: the firmware's 500 ms floor, and a ceiling that keeps the
    # value inside the uint32 the probe stores it in (~49 days).
    try:
        interval_ms = max(500, min(int(interval_ms), 4_294_967_295))
    except (TypeError, ValueError, OverflowError):
        interval_ms = 5000

    try:
        global_res = cfg.get("resolution_bits", RES_BITS_DEFAULT)
        res_value = (cfg.get("probe_resolutions") or {}).get(probe_id, global_res) \
            if probe_id else global_res
        resolution_bits = clamp_resolution_bits(res_value)
    except Exception:  # noqa: BLE001 - config is user-editable; never break ingest
        resolution_bits = clamp_resolution_bits(None)

    # --- threshold watch ------------------------------------------------------
    # Give the probe its own limits so it can notice an excursion between
    # reports instead of sitting on it. Reading the sensor is cheap; the radio
    # is what costs, so the probe samples at `sample_ms` with the radio off and
    # only transmits early when a reading crosses a limit. Without this a probe
    # on a 15-minute interval can be 15 minutes late to a thawing freezer, and
    # the firmware's disturbance burst does not cover it: that fires on a sudden
    # CHANGE, and a slow thaw has none.
    #
    # Sent as explicit nulls when the hub has no limit for this probe, so
    # deleting a threshold on the dashboard actually disarms the probe rather
    # than leaving it watching a limit nobody holds.
    alert_min_c = alert_max_c = None
    try:
        thresholds = cfg.get("alert_thresholds", {}) or {}
        thr = thresholds.get(probe_id) or thresholds.get("default") or {}
        for key, name in (("min", "alert_min_c"), ("max", "alert_max_c")):
            raw = thr.get(key)
            if raw is None:
                continue
            val = float(raw)
            if val != val or val in (float("inf"), float("-inf")):
                continue                      # NaN/inf: no limit is better than a wrong one
            if name == "alert_min_c":
                alert_min_c = val
            else:
                alert_max_c = val
    except Exception:  # noqa: BLE001 - config is user-editable; never break ingest
        alert_min_c = alert_max_c = None

    # How often to READ. Only meaningful below the report interval, and the
    # firmware ignores it otherwise. Default: a minute, or the report interval
    # itself when that is already shorter — sampling faster than you report is
    # the entire point, sampling faster than a minute is not worth the wakes.
    #
    # Per-probe first, like the reporting interval and the resolution above: a
    # walk-in on mains can afford to look every 10 s while a battery probe in a
    # remote freezer should not, and one number for the fleet forces the slowest
    # of those on everything. `probe_samples` holds the override; absent means
    # inherit the global.
    sample_ms = 0
    if alert_min_c is not None or alert_max_c is not None:
        try:
            sample_ms = int(float(cfg.get("probe_sample_sec", 60) or 60)) * 1000
        except (TypeError, ValueError, OverflowError):
            sample_ms = 60_000
        if probe_id:
            try:
                override = (cfg.get("probe_samples") or {}).get(probe_id)
                if override is not None:
                    sample_ms = int(float(override) * 1000)
            except (TypeError, ValueError, OverflowError):
                pass
        sample_ms = max(5_000, min(sample_ms, 4_294_967_295))
        if sample_ms >= interval_ms:
            sample_ms = 0     # nothing to gain; let the probe report as it reads

    return {"interval_ms": interval_ms, "resolution_bits": resolution_bits,
            "alert_min_c": alert_min_c, "alert_max_c": alert_max_c,
            "sample_ms": sample_ms}


def reporting_plan(cfg, probe_id: str = "") -> dict:
    """What a probe will actually do, in the two cadences that differ.

    There are two numbers and the UI only ever showed one of them, under a name
    that belonged to the other. ``interval_ms`` is how often the probe TRANSMITS;
    the field for it was labelled "Read Interval". ``sample_ms`` is how often it
    READS, and it had no control at all — a global ``probe_sample_sec`` you could
    only reach by editing config.json. So the threshold watch, which is the whole
    reason the two numbers are separate, could not be turned on or even seen from
    the app, and the one field on screen described the wrong half of it.

    Derived from :func:`desired_probe_config` rather than re-read from config, so
    what a page says a probe is doing is computed from the same bytes the probe
    is sent. ``sample_sec`` equals ``report_sec`` when the watch is off, because
    then the probe really does read and report on the same beat.
    """
    want = desired_probe_config(cfg, probe_id)
    sample_ms = want.get("sample_ms") or 0
    report_sec = want["interval_ms"] / 1000.0
    return {
        "report_sec": report_sec,
        "sample_sec": (sample_ms / 1000.0) if sample_ms else report_sec,
        "watching": bool(sample_ms),
        "has_limit": (want.get("alert_min_c") is not None
                      or want.get("alert_max_c") is not None),
    }


def usable_server_base(base: str) -> bool:
    """True when ``base`` is an address a PROBE could actually reach.

    The hub derives its own base URL by autodetecting a LAN IP. When that fails
    (an air-gapped host with no default route, a DHCP blip, a bridge-networked
    container) it can fall back to loopback — and provisioning a probe with
    ``http://127.0.0.1:8088/api/ingest`` points the probe at *itself*. Every
    reading then fails, the probe buffers until its 1.9 MB cap and starts
    dropping data, and the hub records the config as successfully delivered so it
    never re-pushes. Refusing to push a base the probe cannot reach keeps the
    previous, working configuration in place instead.
    """
    try:
        host = (urlsplit(str(base or "")).hostname or "").strip("[]")
    except Exception:  # noqa: BLE001 - a malformed base is simply unusable
        return False
    if not host or host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True      # a real hostname — assume resolvable by the probe
    return not (ip.is_loopback or ip.is_link_local or ip.is_unspecified)

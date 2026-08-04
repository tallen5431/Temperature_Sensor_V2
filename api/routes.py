from __future__ import annotations

import datetime
import ipaddress
import time
from typing import Any, Callable, Dict, List, Tuple

from flask import Blueprint, jsonify, request

from provisioning import provision_probe, resolve_host, desired_probe_config
from core.diagnostics import build_diagnostics
from core.secret_compare import constant_time_eq
from core.storage import (normalize_payload, extract_humidity, compute_vpd,
                          sanitize_probe_id, sanitize_site, is_future_stamp,
                          absolute_epoch)
try:  # battery telemetry helper — may be absent on an older core.storage build
    from core.storage import extract_battery
except ImportError:
    def extract_battery(payload):
        return None
from core.status import reporting_probe_ids, hub_health_window
from core.alerts import threshold_for
from core.storage import threshold_breach
from core.version import HUB_VERSION, PRODUCT_NAME
from core.applog import HEALTH, get_logger
from core.metrics import LATEST
from core.mqtt_publish import MQTT
from core.audit import AUDIT

log = get_logger("api")

# A probe is considered "online" if it has been seen within this many seconds.
DEFAULT_ONLINE_TIMEOUT_SEC = 60

# Reject absurdly large ingest bodies (DoS / disk-fill protection).
MAX_INGEST_BYTES = 64 * 1024

# Hard cap on readings accepted in one /ingest_csv call (the ≤1000-rows/request
# contract in PROTOCOL.md §7). The 64 KB byte limit already bounds this in
# practice; this is a belt-and-suspenders guard against a small-but-dense body.
MAX_BATCH_ROWS = 1000

# Named rolling windows accepted by ``GET /api/readings`` (mirrors the CSV
# download's ?window= values in app.py). ``all`` / unknown -> no window.
_WINDOW_SECONDS = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800, "30d": 2592000}

# Probes reporting within this window are considered "present" for
# ``/api/readings/latest`` (matches the dashboard's 7-day per-probe view), so a
# long-retired probe doesn't linger in the latest-values feed.
_LATEST_PRESENCE_SEC = 7 * 86400


def _num(v):
    """Coerce a DB/pandas value to a JSON-safe float, mapping NaN/None -> None.

    ``jsonify`` renders a float NaN as the bare token ``NaN`` (invalid JSON), so
    a missing humidity/VPD must become ``null`` instead."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN != NaN


def _reading_row(r) -> Dict[str, Any]:
    """Normalise one reading (pandas Series or dict) to a JSON object."""
    def g(k):
        try:
            return r[k] if k in r else None
        except (KeyError, TypeError):
            return None
    pid = g("probe_id")
    ts = g("timestamp")
    return {
        "probe_id": ("" if pid is None else str(pid)),
        "timestamp": (None if ts is None else str(ts)),
        "temperature_c": _num(g("temperature_c")),
        "temperature_f": _num(g("temperature_f")),
        "humidity_pct": _num(g("humidity_pct")),
        "vpd_kpa": _num(g("vpd_kpa")),
        "battery_pct": _num(g("battery_pct")),
    }


def _parse_date_epoch(s, end_of_day=False):
    """Parse a hub-local ``YYYY-MM-DD`` (or full ISO) string to a unix epoch.
    A bare date maps to the start (or, for ``end_of_day``, the last second) of
    that day. Returns None for blank/invalid input so the filter is skipped."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = datetime.datetime.fromisoformat(s.replace("Z", ""))
        if len(s) == 10 and end_of_day:
            # Include sub-second rows in the final second: readings can carry
            # fractional (ms) epochs, so a bound of ...59 with `epoch <= bound`
            # would drop 23:59:59.001–.999 on the `to` date. Return a fractional
            # bound at the very end of the day.
            d = d.replace(hour=23, minute=59, second=59, microsecond=999999)
            return d.timestamp()
        return int(d.timestamp())
    except (ValueError, TypeError):
        return None

_UNAUTH_WARN_EVERY_SEC = 60.0
_unauth_last_warn = [0.0, 0]     # [last warn monotonic, suppressed since]


def _deny_unauthorized():
    """Standard 401 response, counted and (rate-limited) logged.

    A silent 401 is the worst failure mode at this seam: a probe whose device
    token went stale posts, is rejected, buffers, and sleeps — every wake,
    forever — while the hub showed nothing at all and the Devices grid just said
    "offline". Counting it makes the cause visible in /api/health and
    /api/diagnostics; the log line names the probe so it can be re-provisioned.
    Rate-limited because a mis-tokened probe fleet could otherwise flood the log.
    """
    total = HEALTH.record_unauthorized()
    now = time.monotonic()
    _unauth_last_warn[1] += 1
    if now - _unauth_last_warn[0] >= _UNAUTH_WARN_EVERY_SEC:
        pid = sanitize_probe_id(request.headers.get("X-Probe-ID") or "")
        log.warning("unauthorized API request from %s probe=%r (%d in the last "
                    "%ds, %d total) — token mismatch; re-provision the probe",
                    request.remote_addr, pid or "?", _unauth_last_warn[1],
                    int(_UNAUTH_WARN_EVERY_SEC), total)
        _unauth_last_warn[0] = now
        _unauth_last_warn[1] = 0
    return jsonify(ok=False, error="unauthorized"), 401


def _json_body() -> dict:
    """The request's parsed JSON as a dict, or ``{}`` for a missing, unparseable,
    or non-object body. A top-level JSON array/number/string is not a valid
    payload for these endpoints; coercing it to ``{}`` keeps ``.get()`` safe so a
    malformed body takes the normal validation path (a clean 400/401) instead of
    an unhandled ``AttributeError`` -> 500."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


# Config keys whose values must never be returned over the API.
_SECRET_KEYS = ("provision_token", "server_token", "token", "secret", "password",
                "api_key", "apikey")


def _redact(data, _parent: str = ""):
    """Return a deep copy with secret values masked.

    Recurses into nested dicts/lists so secrets that live in sub-trees
    (``notifications.email.smtp_password``, ``notifications.webhook.url`` — a
    bearer token in the path) are masked, not just top-level keys. The dashboard
    is open on the LAN by default, so ``GET /api/config`` must never echo a secret.
    """
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            kl = str(k).lower()
            is_secret = any(s in kl for s in _SECRET_KEYS)
            # A webhook URL carries its auth in the path/query — treat as a secret.
            if kl == "url" and "webhook" in str(_parent).lower():
                is_secret = True
            if is_secret:
                # Mask the whole value — including a dict/list — so a secret
                # stored under a secret-named key can't leak via its leaves.
                out[k] = "***set***" if v else ""
            elif isinstance(v, (dict, list)):
                out[k] = _redact(v, kl)
            else:
                out[k] = v
        return out
    if isinstance(data, list):
        return [_redact(x, _parent) for x in data]
    return data


def _is_safe_provision_target(host: str) -> bool:
    """Reject SSRF-style provision targets. Probes live on the private LAN, so
    only private addresses are valid — this blocks loopback, link-local (incl.
    the 169.254.169.254 cloud-metadata endpoint), and public/off-LAN hosts the
    hub could otherwise be tricked into POSTing to."""
    resolved = resolve_host(host)  # bounded — never blocks the request thread
    if not resolved:
        return False
    try:
        ip = ipaddress.ip_address(resolved)
    except Exception:
        return False
    return bool(ip.is_private and not ip.is_loopback and not ip.is_link_local
                and not ip.is_multicast)


def _batch_events(req) -> list:
    """Optional ``events`` array from a bulk-ingest body. ``[]`` if absent.

    JSON only, and deliberately so: the CSV form is the probe's on-flash buffer
    format, and probes have no event log. Only a forwarding hub sends these.
    """
    if "application/json" not in (req.headers.get("Content-Type") or "").lower():
        return []
    body = req.get_json(silent=True)
    if not isinstance(body, dict):
        return []
    events = body.get("events")
    return [e for e in events if isinstance(e, dict)] if isinstance(events, list) else []


def _parse_batch(req):
    """Parse a bulk-ingest body into a list of reading dicts, or None if unusable.

    Two wire formats, both accepted so the probe sends whichever is cheapest:
      * ``text/csv`` (default) — the probe's on-flash buffer format, one reading
        per line: ``timestamp,temp_c,temp_f,probe_id``. No per-reading JSON to
        build on the MCU; it just POSTs a chunk of the buffer file verbatim.
      * ``application/json`` — ``{"readings": [ {..}, .. ]}`` or a bare array
        (handy for tests and other clients).
    Each element comes back as a dict ``normalize_payload`` understands.
    """
    ctype = (req.headers.get("Content-Type") or "").lower()
    if "application/json" in ctype:
        body = req.get_json(silent=True)
        if isinstance(body, dict):
            body = body.get("readings")
        if not isinstance(body, list):
            return None
        return [r for r in body if isinstance(r, dict)]
    rows = []
    for line in (req.get_data(as_text=True) or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 4:
            continue  # structurally corrupt line — skip
        rows.append({"timestamp": parts[0], "temperature_c": parts[1],
                     "temperature_f": parts[2], "probe_id": parts[3]})
    return rows


def create_api(cfg: Any, db: Any, discovery: Any, public_base: Callable[[], str],
               server_token: str = "") -> Blueprint:
    bp = Blueprint("api", __name__, url_prefix="/api")

    TOKEN = (server_token or "").strip()

    # --- authentication helper (constant-time comparison) ---
    def _check_auth() -> bool:
        if not TOKEN:
            return True
        tok = request.headers.get("X-Token") or request.args.get("token")
        if not tok and request.is_json:
            tok = _json_body().get("token")
        # constant_time_eq rather than hmac.compare_digest: the latter raises
        # TypeError on a non-ASCII str, so a hostile client could turn its own
        # 401 into a 500 by sending a non-ASCII X-Token, and a hand-set
        # SERVER_TOKEN with an accented character would 500 every probe's ingest.
        return bool(tok) and constant_time_eq(tok, TOKEN)

    def _online_timeout() -> int:
        try:
            return int(cfg.get("probe_online_timeout_sec", DEFAULT_ONLINE_TIMEOUT_SEC))
        except Exception:
            return DEFAULT_ONLINE_TIMEOUT_SEC

    # --- discovery listing ---
    def _iter_probes() -> List[Dict[str, Any]]:
        if discovery is None:
            return []
        try:
            vals = discovery.list_probes().values()
        except Exception:
            vals = []
        timeout = _online_timeout()
        now = time.time()
        out: List[Dict[str, Any]] = []
        for obj in vals:
            is_dict = isinstance(obj, dict)
            get = (lambda k, d=None: (obj.get(k, d) if is_dict else getattr(obj, k, d)))
            props = get("properties", {}) or {}
            host = get("host")
            ip = get("ip")
            port = get("port", 80) or 80
            name = get("name") or get("id") or props.get("name")
            pid = props.get("id") or get("probe_id") or get("id") or name
            last_seen = get("last_seen")
            age = None
            try:
                if isinstance(last_seen, (int, float)):
                    age = max(0.0, now - float(last_seen))
            except Exception:
                age = None
            out.append({
                "host": host,
                "ip": ip,
                "port": port,
                "name": name,
                "probe_id": pid,
                "last_seen": last_seen,
                "age_sec": round(age, 1) if age is not None else None,
                "online": (age is not None and age <= timeout),
            })

        # Overlay database-reporting freshness (the same interval-aware window the
        # dashboard/Diagnostics use) so this endpoint agrees with the built-in UI:
        #  * a probe posting on its own (possibly slow deep-sleep) cadence counts
        #    as online even when mDNS hasn't seen it inside the fixed timeout, and
        #  * a DB-only probe (deep-sleep radio off, never mDNS-discovered) is still
        #    listed here instead of vanishing from the API between wakes.
        try:
            reporting = reporting_probe_ids(cfg, db)
        except Exception:
            reporting = set()
        seen = set()
        for p in out:
            if p["probe_id"]:
                seen.add(p["probe_id"])
                if p["probe_id"] in reporting:
                    p["online"] = True
        for pid in sorted(reporting - seen):
            out.append({
                "host": None, "ip": None, "port": None, "name": pid,
                "probe_id": pid, "last_seen": None, "age_sec": None,
                "online": True, "source": "readings",
            })
        return sorted(out, key=lambda p: (p.get("name") or "", p.get("ip") or ""))

    # --- endpoints ---
    @bp.get("/health")
    def health():
        probes = _iter_probes()
        try:
            readings = db.count()
        except Exception:
            readings = None  # DB momentarily locked/unreadable — stay a 200 health surface
        return jsonify(
            ok=True,
            version=HUB_VERSION,
            product=PRODUCT_NAME,
            probes=len(probes),
            probes_online=sum(1 for p in probes if p["online"]),
            readings=readings,
            base=public_base(),
            time=datetime.datetime.now().isoformat(timespec="seconds"),
            **HEALTH.snapshot(hub_health_window(cfg)),
        )

    @bp.get("/diagnostics")
    def diagnostics():
        """A single, secret-free snapshot of hub health for self-service support."""
        return jsonify(build_diagnostics(cfg, db, discovery, public_base(),
                                         HUB_VERSION, PRODUCT_NAME))

    @bp.get("/config")
    def get_config():
        """Return config as JSON with secret values redacted (auth required).

        Even redacted, the config exposes SMTP host/recipients, MQTT host and
        thresholds, so it is gated by the device token like the write path.
        """
        if not _check_auth():
            return _deny_unauthorized()
        if isinstance(cfg, dict):
            return jsonify(_redact(cfg))
        if hasattr(cfg, "to_dict"):
            try:
                return jsonify(_redact(cfg.to_dict()))
            except Exception:
                pass
        if hasattr(cfg, "data"):
            try:
                lock = getattr(cfg, "lock", None)
                data_obj = getattr(cfg, "data") or {}
                if lock:
                    with lock:
                        return jsonify(_redact(dict(data_obj)))
                return jsonify(_redact(dict(data_obj)))
            except Exception:
                pass
        return jsonify({})

    @bp.post("/config")
    def set_config():
        """Update config values and persist (auth required)."""
        if not _check_auth():
            return _deny_unauthorized()
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify(ok=False, error="invalid_json"), 400

        if isinstance(cfg, dict):
            cfg.update(data)
            return jsonify(ok=True, config=_redact(cfg))

        if hasattr(cfg, "update"):
            try:
                cfg.update(data)
                snapshot = cfg.to_dict() if hasattr(cfg, "to_dict") else dict(getattr(cfg, "data", {}))
                return jsonify(ok=True, config=_redact(snapshot))
            except Exception as e:
                return jsonify(ok=False, error=str(e)), 400

        return jsonify(ok=True)

    @bp.get("/probes")
    def list_probes():
        return jsonify(_iter_probes())

    @bp.get("/readings/latest")
    def readings_latest():
        """Latest reading per probe as JSON — the JSON twin of ``/metrics`` and
        the 90% case for "poll the current temperatures into another process".

        Returns ``{"count", "readings": [{probe_id, timestamp, temperature_c,
        temperature_f, humidity_pct, vpd_kpa}, ...]}``. Unauthenticated, matching
        ``/api/health`` and ``/api/probes`` — it exposes readings, not secrets.
        Bounded to probes seen in the last 7 days so retired probes drop out.
        """
        try:
            df = db.latest_per_probe(window_seconds=_LATEST_PRESENCE_SEC)
            rows = [_reading_row(r) for _, r in df.iterrows()
                    if str(r.get("probe_id") or "").strip()]
        except Exception:
            log.exception("readings/latest failed")
            return jsonify(ok=False, error="unavailable"), 503
        rows.sort(key=lambda r: r["probe_id"])
        return jsonify(count=len(rows), readings=rows)

    @bp.get("/readings")
    def readings():
        """Historical readings as JSON. Same filters as the CSV download:
        ``?window=24h`` (rolling), ``?probe=<id>``, an absolute
        ``?from=YYYY-MM-DD&to=YYYY-MM-DD`` range, and ``?limit=N``.

        The ``readings`` list is capped (newest kept) so a months-long store
        can't return an unbounded body; ``stats`` (when present) is computed over
        the FULL window, not just the returned rows — the same split the
        dashboard uses between its downsampled chart and exact statistics.
        """
        args = request.args
        window_label = (args.get("window") or "").strip().lower()
        window = _WINDOW_SECONDS.get(window_label)
        probe = (args.get("probe") or args.get("probe_id") or "").strip() or None
        start_epoch = _parse_date_epoch(args.get("from"), end_of_day=False)
        end_epoch = _parse_date_epoch(args.get("to"), end_of_day=True)
        try:
            limit = int(args.get("limit")) if args.get("limit") else None
        except (TypeError, ValueError):
            limit = None
        try:
            rows = db.fetch_readings(window_seconds=window, probe_id=probe,
                                     start_epoch=start_epoch, end_epoch=end_epoch,
                                     limit=limit)
        except Exception:
            log.exception("readings query failed")
            return jsonify(ok=False, error="unavailable"), 503
        readings_out = [_reading_row(r) for r in rows]
        # Attach exact stats only for a plain rolling-window query; window_stats
        # has no from/to filter, so pairing it with an absolute range would report
        # numbers that don't match the returned rows. Omit it there instead.
        stats = None
        if start_epoch is None and end_epoch is None:
            try:
                s = db.window_stats(window_seconds=window, probe_id=probe)
                if s and s.get("count"):
                    stats = {"count": s["count"], "min_c": s["min"], "max_c": s["max"],
                             "avg_c": s["avg"], "min_ts": s["min_ts"], "max_ts": s["max_ts"]}
            except Exception:
                stats = None
        return jsonify(probe=probe, window=window_label or "all",
                       count=len(readings_out), stats=stats, readings=readings_out)

    @bp.get("/audit/verify")
    def audit_verify():
        """Report tamper-evident audit-chain integrity (auth required)."""
        if not _check_auth():
            return _deny_unauthorized()
        return jsonify(AUDIT.verify())

    @bp.post("/provision")
    def provision():
        if not _check_auth():
            return _deny_unauthorized()
        data = _json_body()
        host = (data.get("host") or "").strip()
        try:
            port = int(data.get("port") or 80)
            if not (1 <= port <= 65535):
                raise ValueError
        except (ValueError, TypeError):
            return jsonify(ok=False, error="invalid port"), 400
        interval_ms = int(data.get("interval_ms") or data.get("interval") or 5000)
        # Optional per-probe DS18B20 resolution (9..12); omitted -> probe keeps its own.
        res_bits = data.get("resolution_bits")
        tok = (data.get("token") or TOKEN or "").strip()
        base = public_base().rstrip("/")

        targets: List[Tuple[str, int]] = []
        if host:
            # An explicit host comes straight from the request body; validate it
            # so /provision can't be used to SSRF the hub's own local services or
            # the cloud-metadata endpoint. (The host-less branch below only uses
            # mDNS-discovered probes, which are already trusted LAN targets.)
            if not _is_safe_provision_target(host):
                return jsonify(ok=False, error="host must be a private LAN address"), 400
            targets.append((host, port))
        else:
            for p in _iter_probes():
                target = (p.get("ip") or p.get("host") or "").rstrip(".")
                if target:
                    targets.append((target, int(p.get("port") or 80)))

        succeeded: List[str] = []
        failed: List[str] = []
        for h, prt in targets:
            try:
                if provision_probe(h, prt, base, token=tok, interval_ms=interval_ms,
                                   resolution_bits=res_bits):
                    succeeded.append(f"{h}:{prt}")
                else:
                    failed.append(f"{h}:{prt}")
            except Exception:
                failed.append(f"{h}:{prt}")
        return jsonify(
            ok=bool(succeeded),
            provided_to=succeeded,
            failed=failed,
            total=len(targets),
            success_count=len(succeeded),
            server_base=base,
        )

    def _calibration_offset(probe_id: str) -> float:
        if not probe_id:
            return 0.0
        try:
            return float((cfg.get("calibration_offsets", {}) or {}).get(probe_id, 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _friendly(probe_id: str) -> str:
        try:
            names = cfg.get("probe_names", {}) or {}
            return names.get(probe_id, probe_id) if isinstance(names, dict) else probe_id
        except Exception:
            return probe_id

    def _store(data: dict, remote_addr: str, probe_id: str):
        # Bound the probe id to a safe token before it reaches the DB / CSV / MQTT.
        probe_id = sanitize_probe_id(probe_id)
        ts, t_c, t_f = normalize_payload(data)
        # Apply per-probe calibration so the stored value is the corrected
        # temperature (DS18B20 sensors vary by up to ~0.5 °C).
        offset = _calibration_offset(probe_id)
        if offset:
            t_c += offset
            t_f = (t_c * 9.0 / 5.0) + 32.0

        # Optional humidity -> Vapour Pressure Deficit (grow variant). A
        # temperature-only probe simply omits humidity and stores NULL.
        humidity = extract_humidity(data)
        vpd = None
        if humidity is not None:
            try:
                leaf_offset = (cfg.get("settings", {}) or {}).get("vpd_leaf_offset_c", 0.0)
            except Exception:
                leaf_offset = 0.0
            vpd = compute_vpd(t_c, humidity, leaf_offset)

        # Optional battery level from mains-free probes; missing/invalid -> NULL.
        battery = extract_battery(data)

        db.append(ts, t_c, t_f, probe_id=probe_id, humidity=humidity, vpd=vpd,
                  battery=battery, site=sanitize_site(request.headers.get("X-Site")),
                  # Carry the unambiguous instant when the probe sent one (it
                  # stamps in UTC), so the DST fall-back hour doesn't collapse
                  # two readings onto one epoch.
                  epoch=absolute_epoch(data.get("timestamp") or data.get("ts")))
        HEALTH.record_write()

        if probe_id:
            # In-memory latest-reading registry powers the Prometheus /metrics endpoint.
            LATEST.record(probe_id, t_c, humidity=humidity, vpd=vpd)
            # Optional MQTT publish (Home Assistant auto-discovery); never fatal.
            try:
                MQTT.publish_reading(probe_id, t_c, _friendly(probe_id), humidity=humidity, vpd=vpd)
            except Exception:
                pass
        if discovery and probe_id:
            try:
                # Use ONLY the transport-observed peer address — never a `host`
                # from the body. A body-supplied hostname lands in the discovery
                # registry, and the auto-provisioner then resolves it and POSTs
                # the hub's device token to whatever it points at, which would
                # let any client that can reach /api/ingest exfiltrate the token
                # to an off-LAN address (and hijack a real probe's entry by
                # colliding on its id). The bulk path already did this correctly.
                discovery.update_last_seen(probe_id, host=remote_addr or "",
                                           ip=remote_addr or "")
            except Exception:
                pass

    @bp.post("/ingest")
    def ingest():
        if not _check_auth():
            return _deny_unauthorized()
        if request.content_length and request.content_length > MAX_INGEST_BYTES:
            return jsonify(ok=False, error="payload too large"), 413
        data = _json_body()
        probe_id = request.headers.get("X-Probe-ID") or (data.get("probe_id") or "")
        try:
            _store(data, request.remote_addr or "", probe_id)
        except (ValueError, KeyError, TypeError):
            HEALTH.record_reject()
            return jsonify(ok=False, error="temperature value required"), 400
        except Exception:
            # A genuine storage failure (disk full, DB locked) must surface in the
            # health snapshot, not masquerade as a rejected reading or a bare 500.
            HEALTH.record_failure()
            log.exception("ingest write failed")
            return jsonify(ok=False, error="storage error"), 503
        # Respect the operator's off-switch. `auto_provision: false` means "do not
        # let the hub manage my probes" — it gated only the background pusher, so
        # this reply would have kept overwriting a probe configured by hand (via
        # POST /api/provision or the captive portal) with the hub's global
        # interval, and unlike the pusher there was no way to opt out. Omitting
        # the key is a no-op on the probe (applyHubConfig ignores an absent
        # `config`), so this is safe in both directions.
        if not cfg.get("auto_provision", True):
            return jsonify(ok=True)
        # Ride the hub's desired config home on the reply so a probe can PULL it.
        # The auto-provisioner's push (POST /provision on the probe) only lands if
        # it catches the probe awake, and a deep-sleeping probe serves its HTTP
        # window for ~3 s every Nth wake — on a long interval that is a fraction
        # of a percent of the time, so a settings change could sit undelivered
        # indefinitely. This POST, by contrast, happens every wake and always
        # succeeds. Costs no extra radio time and older firmware ignores the key.
        # Look the override up under the SANITIZED id — that is the id the row was
        # stored under and the one the Devices page writes overrides for, so using
        # the raw header here would silently miss a per-probe setting.
        return jsonify(ok=True,
                       config=desired_probe_config(cfg, sanitize_probe_id(probe_id)))

    @bp.get("/ingest")
    def ingest_query():
        # Ingest is POST-only (PROTOCOL.md §6). A GET that mutates the log is a
        # drive-by CSRF/poisoning vector (<img src=".../api/ingest?...">) and would
        # leak any ?token= into browser history / server logs / Referer headers.
        return jsonify(ok=False, error="method not allowed; use POST"), 405

    @bp.post("/ingest_csv")
    def ingest_csv():
        # Bulk backlog drain (PROTOCOL.md §7). A probe recovering from an outage
        # (weak freezer Wi-Fi, hub down) can hold thousands of buffered readings;
        # uploading them one-POST-per-reading is slow and burns radio/battery.
        # This takes a whole chunk in one round-trip — CSV (the probe's on-flash
        # buffer format) or JSON — validates each reading exactly like /ingest,
        # and writes them in a single transaction (db.bulk_insert). The
        # single-reading /ingest stays for live readings, so older firmware is
        # unaffected.
        if not _check_auth():
            return _deny_unauthorized()
        if request.content_length and request.content_length > MAX_INGEST_BYTES:
            return jsonify(ok=False, error="payload too large"), 413
        rows = _parse_batch(request)
        if rows is None:
            return jsonify(ok=False, error="unparseable batch body"), 400
        if len(rows) > MAX_BATCH_ROWS:
            return jsonify(ok=False, error="too many rows (max %d)" % MAX_BATCH_ROWS), 413

        header_pid = request.headers.get("X-Probe-ID") or ""
        valid = []        # (ts, t_c, t_f, probe_id) tuples for bulk_insert
        newest = {}       # probe_id -> (ts, t_c): most-recent accepted reading
        worst = {}        # probe_id -> (kind, t_c, limit, ts): worst backlog breach
        rejected = 0
        # Receipt-stamp bulk rows the hub must stamp itself, spread 1 ms apart.
        # Two cases need this, and both are silent data loss without it, because
        # every such row would otherwise land on the SAME millisecond and all but
        # the first would be dropped by the UNIQUE(probe_id, epoch, site) index while
        # the endpoint still answered 200 — so the probe advances its checkpoint
        # and deletes the buffer it just lost:
        #   1. a row with NO timestamp at all, and
        #   2. a row stamped implausibly far in the FUTURE, which normalize_payload
        #      would clamp to "now" independently per row. A probe whose clock ran
        #      ahead during the very outage that filled its buffer drains a whole
        #      backlog of such rows, so this is the common case, not a corner one.
        recv_base = datetime.datetime.now()
        recv_now = recv_base.timestamp()
        synth = 0
        restamped = 0
        for row in rows:
            raw_ts = row.get("timestamp") or row.get("ts")
            if not raw_ts or is_future_stamp(raw_ts, recv_now):
                if raw_ts:
                    restamped += 1
                row = dict(row)
                row["timestamp"] = (recv_base + datetime.timedelta(
                    milliseconds=synth)).isoformat(timespec="milliseconds")
                synth += 1
            try:
                pid = sanitize_probe_id(row.get("probe_id") or header_pid)
                ts, t_c, t_f = normalize_payload(row)
            except (ValueError, KeyError, TypeError):
                rejected += 1
                continue
            # A buffer line truncated mid-write (a probe whose battery died while
            # appending) still splits into 4 fields — the cut lands in the LAST
            # one, the probe id — so it would be accepted as a real reading filed
            # under a mangled id like "Setpo", inventing a phantom probe. A probe
            # only ever drains its OWN buffer, so a row whose id disagrees with
            # the request's X-Probe-ID is corrupt, not merely unexpected.
            if header_pid and pid and pid != sanitize_probe_id(header_pid):
                rejected += 1
                continue
            offset = _calibration_offset(pid)
            if offset:
                t_c += offset
                t_f = (t_c * 9.0 / 5.0) + 32.0
            # Carry the optional telemetry the live path stores, so a grow probe
            # draining a backlog doesn't come back as temperature-only.
            humidity = extract_humidity(row)
            vpd = None
            if humidity is not None:
                try:
                    leaf = (cfg.get("settings", {}) or {}).get("vpd_leaf_offset_c", 0.0)
                    vpd = compute_vpd(t_c, humidity, leaf)
                except Exception:  # noqa: BLE001 - VPD is derived; never fail a row
                    vpd = None
            valid.append((ts, t_c, t_f, pid, humidity, vpd, extract_battery(row),
                          absolute_epoch(row.get("timestamp") or row.get("ts"))))
            prev = newest.get(pid)
            if prev is None or ts > prev[0]:
                newest[pid] = (ts, t_c)
            # Track the WORST excursion in this backlog per probe (see the
            # backfill-breach block after the insert).
            thr = threshold_for(cfg.get("alert_thresholds", {}) or {}, pid)
            breach = threshold_breach(t_c, thr.get("min"), thr.get("max"))
            if breach:
                limit = thr.get("max") if breach == "high" else thr.get("min")
                cur = worst.get(pid)
                worse = cur is None or cur[0] != breach or (
                    t_c > cur[1] if breach == "high" else t_c < cur[1])
                if cur is None or worse:
                    worst[pid] = (breach, t_c, limit, ts)

        accepted = 0
        if valid:
            try:
                # Batch-level site (X-Site), not per-row: a forwarding hub sends
                # only its own readings, so one label per batch cannot disagree
                # with itself, and it works for the CSV body format too. Empty
                # for a probe posting directly — every reading on a single-site
                # hub — which is what keeps those rows eligible to forward.
                accepted = db.bulk_insert(
                    valid, site=sanitize_site(request.headers.get("X-Site")))
            except Exception:
                HEALTH.record_failure()
                log.exception("batch ingest write failed")
                return jsonify(ok=False, error="storage error"), 503
            for _ in range(accepted):
                HEALTH.record_write()
            # Backfilled breaches. The alert engine only ever evaluates each
            # probe's LATEST reading, so a threshold excursion that happened
            # entirely during an outage — the freezer that thawed while the hub
            # was down, which is the single most important thing not to miss —
            # was stored by this drain and then never alerted, because by the
            # time the probe reconnected it was reading normally again. Record
            # the worst excursion per probe in the event log (stamped at the time
            # it actually occurred) so it shows up in Recent events and the
            # history instead of vanishing. Deliberately NOT dispatched as a
            # live notification: it is old news by definition, and this runs on a
            # request thread.
            for pid, (kind, t_c, limit, when) in worst.items():
                # ...but ONLY for excursions the alert engine will not see. If the
                # worst excursion IS this probe's newest row, the engine evaluates
                # it on its next pass and logs it live, so recording it here too
                # double-logs the same breach. That was invisible while
                # /ingest_csv only ever served probes draining a buffer; a
                # FORWARDING hub sends every batch through this endpoint, so on an
                # HQ hub every single store breach was landing in the event log
                # twice. Backfill exists for breaches that are already old news —
                # those still get their entry.
                if newest.get(pid) and newest[pid][0] == when:
                    continue
                try:
                    db.record_event(kind, pid, temperature_c=t_c, limit=limit, ts=when)
                    log.info("backfilled %s breach for probe=%r at %s (%.2f C)",
                             kind, pid, when, t_c)
                except Exception:  # noqa: BLE001 - telemetry must never fail ingest
                    pass
            # Reflect current state ONCE per probe (its newest reading) in the
            # Prometheus registry + last-seen, rather than replaying the backlog.
            # MQTT is deliberately left to the live /ingest path so historical
            # rows aren't (re)published to Home Assistant out of order.
            for pid, (_, t_c) in newest.items():
                if not pid:
                    continue
                try:
                    LATEST.record(pid, t_c)
                except Exception:
                    pass
                if discovery:
                    try:
                        discovery.update_last_seen(pid, host="", ip=request.remote_addr or "")
                    except Exception:
                        pass
        for _ in range(rejected):
            HEALTH.record_reject()
        if restamped:
            # Surface it: a probe whose clock ran ahead is silently having its
            # chronology rewritten to drain time, and neither side would
            # otherwise report anything. Also returned so the probe (and a
            # support transcript) can see it happened.
            log.warning("ingest_csv: re-stamped %d/%d future-dated row(s) from probe=%r "
                        "— check the probe's clock (NTP) or the hub's",
                        restamped, len(rows), header_pid or "?")
        # Alert-lifecycle events, optional and JSON-only. A probe never sends
        # these — only a forwarding hub does, carrying what its OWN alert engine
        # decided against its OWN thresholds. That is a different record from the
        # readings beside them and the one an auditor asks for, so it rides the
        # same request rather than needing its own endpoint, auth path and
        # failure mode: one round trip, and either both land or neither does.
        events_in = _batch_events(request)
        events_ok = 0
        if events_in:
            site = sanitize_site(request.headers.get("X-Site"))
            for ev in events_in[:MAX_BATCH_ROWS]:
                try:
                    db.record_event(str(ev.get("kind") or ""),
                                    sanitize_probe_id(ev.get("probe_id") or ""),
                                    temperature_c=ev.get("temperature_c"),
                                    limit=ev.get("limit_c"),
                                    ts=ev.get("timestamp") or ev.get("ts"),
                                    site=site)
                    events_ok += 1
                except Exception:  # noqa: BLE001 - an event must never fail readings
                    pass
        return jsonify(ok=True, accepted=accepted, rejected=rejected,
                       restamped=restamped, events=events_ok)

    return bp

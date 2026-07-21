from __future__ import annotations

import datetime
import hmac
import ipaddress
import time
from typing import Any, Callable, Dict, List, Tuple

from flask import Blueprint, jsonify, request

from provisioning import provision_probe, resolve_host
from core.diagnostics import build_diagnostics
from core.storage import normalize_payload, extract_humidity, compute_vpd, sanitize_probe_id
from core.status import reporting_probe_ids
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
            d = d.replace(hour=23, minute=59, second=59)
        return int(d.timestamp())
    except (ValueError, TypeError):
        return None

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
            data = request.get_json(silent=True) or {}
            tok = data.get("token")
        return bool(tok) and hmac.compare_digest(str(tok), TOKEN)

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
        return jsonify(
            ok=True,
            version=HUB_VERSION,
            product=PRODUCT_NAME,
            probes=len(probes),
            probes_online=sum(1 for p in probes if p["online"]),
            readings=db.count(),
            base=public_base(),
            time=datetime.datetime.now().isoformat(timespec="seconds"),
            **HEALTH.snapshot(),
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
            return jsonify(ok=False, error="unauthorized"), 401
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
            return jsonify(ok=False, error="unauthorized"), 401
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
            return jsonify(ok=False, error="unauthorized"), 401
        return jsonify(AUDIT.verify())

    @bp.post("/provision")
    def provision():
        if not _check_auth():
            return jsonify(ok=False, error="unauthorized"), 401
        data = request.get_json(silent=True) or {}
        host = (data.get("host") or "").strip()
        try:
            port = int(data.get("port") or 80)
            if not (1 <= port <= 65535):
                raise ValueError
        except (ValueError, TypeError):
            return jsonify(ok=False, error="invalid port"), 400
        interval_ms = int(data.get("interval_ms") or data.get("interval") or 5000)
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
                if provision_probe(h, prt, base, token=tok, interval_ms=interval_ms):
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

        db.append(ts, t_c, t_f, probe_id=probe_id, humidity=humidity, vpd=vpd)
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
                host = data.get("host") or remote_addr or ""
                discovery.update_last_seen(probe_id, host=host, ip=remote_addr or "")
            except Exception:
                pass

    @bp.post("/ingest")
    def ingest():
        if not _check_auth():
            return jsonify(ok=False, error="unauthorized"), 401
        if request.content_length and request.content_length > MAX_INGEST_BYTES:
            return jsonify(ok=False, error="payload too large"), 413
        data = request.get_json(silent=True) or {}
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
        return jsonify(ok=True)

    @bp.get("/ingest")
    def ingest_query():
        # Ingest is POST-only (PROTOCOL.md §6). A GET that mutates the log is a
        # drive-by CSRF/poisoning vector (<img src=".../api/ingest?...">) and would
        # leak any ?token= into browser history / server logs / Referer headers.
        return jsonify(ok=False, error="method not allowed; use POST"), 405

    return bp

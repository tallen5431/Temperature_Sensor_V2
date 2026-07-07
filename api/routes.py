from __future__ import annotations
from flask import Blueprint, request, jsonify
from typing import Any, Dict, List, Tuple, Callable
from pathlib import Path
import datetime

from auto_provision import provision_probe
from core.storage import (
    normalize_payload, append_row, apply_calibration, sanitize_probe_id,
    extract_humidity, compute_vpd,
)
from core.notifications import NOTIFIER
from core.applog import HEALTH, get_logger
from core.config import redact_secrets
from core.metrics import LATEST
from core.mqtt_publish import MQTT
from core.version import __version__, PROTOCOL_VERSION

log = get_logger("api")

# Reject absurdly large ingest bodies (DoS / disk-fill protection).
MAX_INGEST_BYTES = 64 * 1024
MAX_CSV_ROWS = 1000


def create_api(cfg: Any, csv_path: str, discovery: Any, public_base: Callable[[], str], server_token: str = "") -> Blueprint:
    bp = Blueprint("api", __name__, url_prefix="/api")

    TOKEN = (server_token or "").strip()
    CSV_PATH = Path(csv_path)

    # --- authentication helper ---
    # An empty TOKEN means "open" (useful for tests / air-gapped dev). The
    # shipped product ALWAYS resolves a non-empty token at startup (generated if
    # needed) and pushes it to probes via the provisioner, so the customer's LAN
    # is secure-by-default without any manual setup.
    def _check_auth() -> bool:
        if not TOKEN:
            return True
        tok = request.headers.get("X-Token") or request.args.get("token")
        if not tok and request.is_json:
            data = request.get_json(silent=True) or {}
            tok = data.get("token")
        return tok == TOKEN

    def _cfg_get(key, default=None):
        try:
            return cfg.get(key, default)
        except Exception:
            return default

    def _friendly(probe_id: str) -> str:
        names = _cfg_get("probe_names", {}) or {}
        return names.get(probe_id, probe_id)

    # --- discovery listing ---
    def _iter_probes() -> List[Dict[str, Any]]:
        if discovery is None:
            return []
        try:
            vals = discovery.list_probes().values()
        except Exception:
            vals = []
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
            out.append({
                "host": host,
                "ip": ip,
                "port": port,
                "name": name,
                "probe_id": pid,
                "last_seen": get("last_seen"),
            })
        return sorted(out, key=lambda p: (p.get("name") or "", p.get("ip") or ""))

    # --- endpoints ---
    @bp.get("/health")
    def health():
        return jsonify(
            ok=True,
            version=__version__,
            protocol=PROTOCOL_VERSION,
            probes=len(_iter_probes()),
            base=public_base(),
            time=datetime.datetime.now().isoformat(timespec="seconds"),
            **HEALTH.snapshot(),
        )

    @bp.get("/config")
    def get_config():
        """Return config as JSON with all secrets redacted (auth required)."""
        if not _check_auth():
            return jsonify(ok=False, error="unauthorized"), 401
        if hasattr(cfg, "public_dict"):
            try:
                return jsonify(cfg.public_dict())
            except Exception:
                pass
        if hasattr(cfg, "to_dict"):
            try:
                return jsonify(redact_secrets(cfg.to_dict()))
            except Exception:
                pass
        if isinstance(cfg, dict):
            return jsonify(redact_secrets(dict(cfg)))
        return jsonify({})

    @bp.post("/config")
    def set_config():
        """Update config values and persist. Secrets are redacted from the response."""
        if not _check_auth():
            return jsonify(ok=False, error="unauthorized"), 401

        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify(ok=False, error="invalid_json"), 400

        try:
            if hasattr(cfg, "update"):
                cfg.update(data)
                snap = cfg.public_dict() if hasattr(cfg, "public_dict") else redact_secrets(cfg.to_dict())
                return jsonify(ok=True, config=snap)
            if isinstance(cfg, dict):
                cfg.update(data)
                return jsonify(ok=True, config=redact_secrets(dict(cfg)))
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 400
        return jsonify(ok=True)

    @bp.get("/probes")
    def list_probes():
        return jsonify(_iter_probes())

    @bp.post("/provision")
    def provision():
        if not _check_auth():
            return jsonify(ok=False, error="unauthorized"), 401
        data = request.get_json(silent=True) or {}
        host = (data.get("host") or "").strip()
        port = int(data.get("port") or 80)
        interval_ms = int(data.get("interval_ms") or data.get("interval") or 5000)
        tok = (data.get("token") or TOKEN or "").strip()
        base = public_base().rstrip("/")

        targets: List[Tuple[str, int]] = []
        if host:
            targets.append((host, port))
        else:
            for p in _iter_probes():
                target = (p.get("ip") or p.get("host") or "").rstrip(".")
                if target:
                    targets.append((target, int(p.get("port") or 80)))

        ok_any = False
        succeeded: List[str] = []
        failed: List[str] = []
        for h, prt in targets:
            try:
                if provision_probe(h, prt, base, token=tok, interval_ms=interval_ms):
                    ok_any = True
                    succeeded.append(f"{h}:{prt}")
                else:
                    failed.append(f"{h}:{prt}")
            except Exception:
                failed.append(f"{h}:{prt}")
        return jsonify(
            ok=ok_any,
            provided_to=succeeded,
            failed=failed,
            total=len(targets),
            success_count=len(succeeded),
            server_base=base,
        )

    def _log_reading(data: dict, probe_id_hint: str) -> Tuple[bool, int, str]:
        """Validate + calibrate + persist a single reading. Returns (ok, status, err)."""
        try:
            ts, t_c, t_f = normalize_payload(data)
        except Exception as e:
            HEALTH.record_reject()
            return False, 400, str(e) or "temperature value required"

        probe_id = sanitize_probe_id(probe_id_hint or data.get("probe_id") or "")

        # Apply per-probe calibration before logging (recompute F from calibrated C).
        cal = _cfg_get("calibration", {}) or {}
        t_c = apply_calibration(t_c, probe_id, cal)
        t_f = (t_c * 9.0 / 5.0) + 32.0

        # Optional humidity → Vapour Pressure Deficit (grow niche).
        humidity = extract_humidity(data)
        vpd = None
        if humidity is not None:
            leaf_offset = (_cfg_get("settings", {}) or {}).get("vpd_leaf_offset_c", 0.0)
            vpd = compute_vpd(t_c, humidity, leaf_offset)

        try:
            append_row(CSV_PATH, ts, t_c, t_f, probe_id=probe_id,
                       humidity_pct=humidity, vpd_kpa=vpd)
        except Exception as e:
            return False, 500, str(e)

        if probe_id:
            # Latest-reading registry powers the Prometheus /metrics endpoint.
            LATEST.record(probe_id, t_c, humidity=humidity, vpd=vpd)
            if discovery is not None:
                try:
                    discovery.register_seen(probe_id, ip=request.remote_addr or "", port=80)
                except Exception:
                    pass
            friendly = _friendly(probe_id)
            # Server-side threshold evaluation → email/webhook if configured.
            NOTIFIER.evaluate(cfg, probe_id, t_c, friendly, humidity=humidity, vpd=vpd)
            # Optional MQTT publish (Home Assistant auto-discovery).
            MQTT.publish_reading(probe_id, t_c, friendly, humidity=humidity, vpd=vpd)
        return True, 200, ""

    @bp.post("/ingest")
    def ingest():
        if not _check_auth():
            return jsonify(ok=False, error="unauthorized"), 401
        if request.content_length and request.content_length > MAX_INGEST_BYTES:
            return jsonify(ok=False, error="payload too large"), 413
        data = request.get_json(silent=True) or {}
        header_id = request.headers.get("X-Probe-ID") or ""
        body_id = data.get("probe_id") or ""
        # Protocol invariant: the mDNS TXT id must equal X-Probe-ID. Warn (don't
        # crash) so a misbehaving probe is diagnosable rather than silent.
        if header_id and body_id and header_id != body_id:
            log.warning("probe_id mismatch: header=%s body=%s", header_id, body_id)
        ok, status, err = _log_reading(data, header_id or body_id)
        if not ok:
            return jsonify(ok=False, error=err), status
        return jsonify(ok=True)

    @bp.get("/ingest")
    def ingest_get_removed():
        # GET used to mutate the CSV → a drive-by <img> could poison the log.
        # Ingest is POST-only now.
        return jsonify(ok=False, error="method not allowed; use POST"), 405

    @bp.post("/ingest_csv")
    def ingest_csv():
        if not _check_auth():
            return jsonify(ok=False, error="unauthorized"), 401
        if request.content_length and request.content_length > MAX_INGEST_BYTES:
            return jsonify(ok=False, error="payload too large"), 413
        text = request.data.decode("utf-8", "ignore")
        n = 0
        for line in text.splitlines():
            if n >= MAX_CSV_ROWS:
                break
            parts = [p.strip() for p in line.split(",")]
            if not parts or not parts[0]:
                continue
            pid = parts[1] if len(parts) > 1 else ""
            ok, _status, _err = _log_reading({"temperature_c": parts[0]}, pid)
            if ok:
                n += 1
        return jsonify(ok=True, rows=n)

    return bp

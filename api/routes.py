from __future__ import annotations

import datetime
import hmac
import time
from typing import Any, Callable, Dict, List, Tuple

from flask import Blueprint, jsonify, request

from provisioning import provision_probe
from core.storage import normalize_payload

# A probe is considered "online" if it has been seen within this many seconds.
DEFAULT_ONLINE_TIMEOUT_SEC = 60

# Config keys whose values must never be returned over the API.
_SECRET_KEYS = ("provision_token", "server_token", "token", "secret", "password")


def _redact(data: dict) -> dict:
    """Return a shallow copy with secret values masked."""
    out = {}
    for k, v in (data or {}).items():
        if any(s in str(k).lower() for s in _SECRET_KEYS):
            out[k] = "***set***" if v else ""
        else:
            out[k] = v
    return out


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
        return sorted(out, key=lambda p: (p.get("name") or "", p.get("ip") or ""))

    # --- endpoints ---
    @bp.get("/health")
    def health():
        probes = _iter_probes()
        return jsonify(
            ok=True,
            probes=len(probes),
            probes_online=sum(1 for p in probes if p["online"]),
            readings=db.count(),
            base=public_base(),
            time=datetime.datetime.now().isoformat(timespec="seconds"),
        )

    @bp.get("/config")
    def get_config():
        """Return config as JSON with secret values redacted."""
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

    def _store(data: dict, remote_addr: str, probe_id: str):
        ts, t_c, t_f = normalize_payload(data)
        db.append(ts, t_c, t_f, probe_id=probe_id)
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
        data = request.get_json(silent=True) or {}
        probe_id = request.headers.get("X-Probe-ID") or (data.get("probe_id") or "")
        try:
            _store(data, request.remote_addr or "", probe_id)
        except (ValueError, KeyError, TypeError):
            return jsonify(ok=False, error="temperature value required"), 400
        return jsonify(ok=True)

    @bp.get("/ingest")
    def ingest_query():
        if not _check_auth():
            return jsonify(ok=False, error="unauthorized"), 401
        data = {k: v for k, v in request.args.items()}
        probe_id = request.args.get("probe_id") or ""
        try:
            _store(data, request.remote_addr or "", probe_id)
        except (ValueError, KeyError, TypeError):
            return jsonify(ok=False, error="temperature value required"), 400
        return jsonify(ok=True)

    return bp

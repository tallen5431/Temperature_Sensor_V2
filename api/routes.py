from __future__ import annotations
from flask import Blueprint, request, jsonify
from typing import Any, Dict, List, Tuple, Callable
from pathlib import Path
import os, csv, datetime

from auto_provision import provision_probe
from core.storage import normalize_payload, append_row


def create_api(cfg: Any, csv_path: str, discovery: Any, public_base: Callable[[], str], server_token: str = "") -> Blueprint:
    bp = Blueprint("api", __name__, url_prefix="/api")

    TOKEN = (server_token or "").strip()
    CSV_PATH = Path(csv_path)

    # --- authentication helper ---
    if not TOKEN:
        def _check_auth() -> bool:
            return True
    else:
        def _check_auth() -> bool:
            tok = request.headers.get("X-Token") or request.args.get("token")
            if not tok and request.is_json:
                data = request.get_json(silent=True) or {}
                tok = data.get("token")
            return tok == TOKEN

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
                "last_seen": get("last_seen")
            })
        # stable sort by name/ip for UI consistency
        return sorted(out, key=lambda p: (p.get("name") or "", p.get("ip") or ""))

    # --- endpoints ---
    @bp.get("/health")
    def health():
        return jsonify(
            ok=True,
            probes=len(_iter_probes()),
            base=public_base(),
            time=datetime.datetime.now().isoformat(timespec="seconds")
        )

    @bp.get("/config")
    def get_config():
        """Return config as JSON.

        Supports:
          - dict config
          - Config-like object with .data (and optional .lock)
          - objects implementing .to_dict()
        """
        # Plain dict
        if isinstance(cfg, dict):
            return jsonify(cfg)

        # Prefer to_dict() if present
        if hasattr(cfg, "to_dict"):
            try:
                return jsonify(cfg.to_dict())
            except Exception:
                pass

        # Prefer cfg.data if present (your Config class)
        if hasattr(cfg, "data"):
            try:
                lock = getattr(cfg, "lock", None)
                data_obj = getattr(cfg, "data") or {}
                if lock:
                    with lock:
                        return jsonify(dict(data_obj))
                return jsonify(dict(data_obj))
            except Exception:
                pass

        return jsonify({})

    @bp.post("/config")
    def set_config():
        """Update config values and persist when possible."""
        if not _check_auth():
            return jsonify(ok=False, error="unauthorized"), 401

        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify(ok=False, error="invalid_json"), 400

        # Dict config: update in place
        if isinstance(cfg, dict):
            cfg.update(data)
            return jsonify(ok=True, config=cfg)

        # Config class: update cfg.data under lock, then save()
        if hasattr(cfg, "data"):
            try:
                lock = getattr(cfg, "lock", None)
                if lock:
                    with lock:
                        cfg.data.update(data)  # type: ignore[attr-defined]
                else:
                    cfg.data.update(data)  # type: ignore[attr-defined]

                if hasattr(cfg, "save"):
                    try:
                        cfg.save()  # type: ignore[attr-defined]
                    except Exception:
                        # Don't fail request if persistence fails
                        pass

                return jsonify(ok=True, config=dict(getattr(cfg, "data") or {}))
            except Exception as e:
                return jsonify(ok=False, error=str(e)), 400

        # Last resort: try update(), then setattr
        if hasattr(cfg, "update"):
            try:
                cfg.update(data)
                return jsonify(ok=True)
            except Exception:
                pass

        for k, v in data.items():
            try:
                setattr(cfg, k, v)
            except Exception:
                pass

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
            server_base=base
        )

    @bp.post("/ingest")
    def ingest():  # updates discovery last_seen for active probes
        if not _check_auth():
            return jsonify(ok=False, error="unauthorized"), 401
        data = request.get_json(silent=True) or {}
        try:
            ts, t_c, t_f = normalize_payload(data)
        except Exception:
            return jsonify(ok=False, error="temperature value required"), 400
        probe_id = request.headers.get("X-Probe-ID") or (data.get("probe_id") or "")
        try:
            append_row(CSV_PATH, ts, t_c, t_f, probe_id=probe_id)
            # mark probe as seen (optimized - removed duplicate logic)
            if discovery and probe_id:
                try:
                    import time
                    probes = discovery.list_probes()
                    matched = False

                    # Try to find and update existing probe
                    for key, v in probes.items():
                        if not v:
                            continue

                        # Match by exact key, name, or properties.id (not substring)
                        v_id = None
                        v_name = None
                        v_props_id = None

                        if isinstance(v, dict):
                            v_id = v.get('id')
                            v_name = v.get('name')
                            v_props_id = v.get('properties', {}).get('id')
                        else:
                            v_id = getattr(v, 'id', None)
                            v_name = getattr(v, 'name', None)
                            v_props_id = getattr(v, 'properties', {}).get('id')

                        # Exact match only (fixes substring matching bug)
                        if key == probe_id or v_id == probe_id or v_name == probe_id or v_props_id == probe_id:
                            try:
                                if isinstance(v, dict):
                                    v['last_seen'] = time.time()
                                else:
                                    v.last_seen = time.time()
                                matched = True
                                break
                            except Exception:
                                pass

                    # If no match found, create new probe entry
                    if not matched:
                        try:
                            from probe_discovery import ProbeInfo
                            probes[probe_id] = ProbeInfo(
                                name=probe_id,
                                host=data.get('host') or request.remote_addr or '',
                                ip=request.remote_addr or '',
                                port=80,
                                properties={'id': probe_id},
                                last_seen=time.time()
                            )
                        except Exception:
                            # Fallback to dict if ProbeInfo fails
                            probes[probe_id] = {
                                'id': probe_id,
                                'name': probe_id,
                                'host': data.get('host') or request.remote_addr or '',
                                'ip': request.remote_addr or '',
                                'port': 80,
                                'properties': {'id': probe_id},
                                'last_seen': time.time()
                            }
                except Exception:
                    pass
        except Exception:
            _append_csv(str(CSV_PATH), t_c, probe_id)
        return jsonify(ok=True)

    @bp.get("/ingest")
    def ingest_query():
        if not _check_auth():
            return jsonify(ok=False, error="unauthorized"), 401
        data = {k: v for k, v in request.args.items()}
        try:
            ts, t_c, t_f = normalize_payload(data)
        except Exception:
            return jsonify(ok=False, error="temperature value required"), 400
        probe_id = request.args.get("probe_id") or ""
        try:
            append_row(CSV_PATH, ts, t_c, t_f, probe_id=probe_id)
        except Exception:
            _append_csv(str(CSV_PATH), t_c, probe_id)
        return jsonify(ok=True)

    @bp.post("/ingest_csv")
    def ingest_csv():
        if not _check_auth():
            return jsonify(ok=False, error="unauthorized"), 401
        text = request.data.decode("utf-8", "ignore")
        n = 0
        for line in text.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if not parts:
                continue
            try:
                t_c = float(parts[0])
            except Exception:
                continue
            pid = parts[1] if len(parts) > 1 else ""
            _append_csv(str(CSV_PATH), t_c, pid)
            n += 1
        return jsonify(ok=True, rows=n)

    return bp


def _append_csv(csv_path: str, t_c: float, probe_id: str) -> None:
    exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["timestamp", "temperature_c", "temperature_f", "probe_id"])
        t_f = (t_c * 9.0 / 5.0) + 32.0
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        w.writerow([ts, f"{t_c:.3f}", f"{t_f:.3f}", probe_id])

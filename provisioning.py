from __future__ import annotations
import requests, socket
from typing import Optional


def get_probe_status(base_host: str, port: int, timeout: float = 3.0) -> Optional[dict]:
    """GET /status from a probe. Returns parsed JSON dict or None on failure.

    Tries the resolved IP first (faster, avoids mDNS on Windows), then falls
    back to the hostname so .local names still work on Linux/macOS.
    """
    h = (base_host or "").rstrip(".")
    candidates = []
    try:
        ip = socket.gethostbyname(h)
        if ip and ip != h:
            candidates.append(f"http://{ip}:{port}/status")
    except Exception:
        pass
    candidates.append(f"http://{h}:{port}/status")

    for url in candidates:
        try:
            r = requests.get(url, timeout=timeout)
            if r.ok:
                return r.json()
        except Exception:
            pass
    return None


def provision_probe(base_host: str, port: int, server_base: str, token: str = "",
                    interval_ms: int = 5000, timeout: float = 3.0) -> bool:
    """
    Try both IP and hostname to reach /provision so Windows .local issues don't block it.
    """
    h = (base_host or "").rstrip(".")
    body = {
        "server_url": f"{server_base.rstrip('/')}/api/ingest",
        "token": token or "",
        "interval_ms": int(interval_ms),
    }

    # Prepare both IP and hostname candidates
    candidates = []
    try:
        ip = socket.gethostbyname(h)
        if ip and ip != h:
            candidates.append(f"http://{ip}:{port}/provision")
    except Exception:
        pass
    candidates.append(f"http://{h}:{port}/provision")

    for url in candidates:
        try:
            r = requests.post(url, json=body, timeout=timeout)
            if r.ok:
                print(f"[provision] {url} OK")
                return True
            else:
                print(f"[provision] {url} failed -> {r.status_code}")
        except Exception as e:
            print(f"[provision] {url} exception: {e}")
    return False
from __future__ import annotations
import requests, socket

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
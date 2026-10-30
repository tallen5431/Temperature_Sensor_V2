"""Is a hub already running on this port?

Once the hub runs in the background at boot (a scheduled task or service), the
Start-menu icon becomes the way people open the dashboard — and clicking it
started a SECOND hub. That copy launched its own alert monitor, provisioner and
mDNS advert before waitress discovered the port was taken, so for a few seconds
two monitors judged the same readings (duplicate alerts) and then the second
one died with a traceback. Asking first turns the click into what the person
meant: open the dashboard of the hub that is already running.
"""
from __future__ import annotations

import socket
from typing import Optional, Tuple

import requests

FREE, HUB, BUSY = "free", "hub", "busy"


def probe_port(port: int, host: str = "127.0.0.1",
               timeout: float = 2.0) -> Tuple[str, Optional[dict]]:
    """``(FREE, None)``, ``(HUB, health)`` or ``(BUSY, None)`` for ``port``.

    HUB means something on the port answers ``/api/health`` the way a Setpoint
    hub does (it stays reachable with the dashboard login on, by design). BUSY
    means some other program holds the port, which the caller should report
    rather than open a browser onto.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError:
        return FREE, None
    try:
        r = requests.get(f"http://{host}:{port}/api/health", timeout=timeout)
        body = r.json() if r.ok else None
    except (requests.RequestException, ValueError):
        body = None
    # version + base are what a hub's /api/health always carries; checked by shape
    # rather than by product name so a white-labelled build is recognised too.
    if isinstance(body, dict) and "version" in body and "base" in body:
        return HUB, body
    return BUSY, None

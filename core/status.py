"""Live hub status, derived from the discovery list and the database.

Pure and side-effect free so it can be unit-tested without a UI or network.
The Dash footer maps the returned state to display text/colour.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable


def hub_status(probes: Iterable[Any], online_timeout: float,
               total_readings: int, now: float | None = None) -> Dict[str, Any]:
    """Summarise hub health.

    Returns ``{"state", "online", "total", "readings"}`` where ``state`` is one of:
      * ``"online"``  — at least one probe reported within ``online_timeout`` seconds
      * ``"offline"`` — probes are known but all have gone quiet
      * ``"idle"``    — no probes known, but readings exist (probe was here, now gone)
      * ``"waiting"`` — fresh install, nothing has ever reported
    """
    now = time.time() if now is None else now
    total = 0
    online = 0
    for p in probes:
        total += 1
        last = p.get("last_seen") if isinstance(p, dict) else getattr(p, "last_seen", None)
        if isinstance(last, (int, float)) and (now - float(last)) <= online_timeout:
            online += 1

    if online:
        state = "online"
    elif total:
        state = "offline"
    elif total_readings:
        state = "idle"
    else:
        state = "waiting"
    return {"state": state, "online": online, "total": total, "readings": int(total_readings)}

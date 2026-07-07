# core/audit.py
"""Tamper-evident, append-only audit trail.

Business/facility buyers (and any future regulated path — FDA 21 CFR Part 11,
EU Annex 11) expect a computer-generated, time-stamped record of who changed
what and when, that cannot be silently edited. This is a lightweight foundation:
each entry stores the hash of the previous entry, forming a chain — altering or
deleting any past entry breaks verification.

It is NOT a validated Part-11 system on its own (that needs enforced per-user
identity, e-signatures, and formal validation), but it is a real procurement
differentiator now and the correct substrate to build on later. See COMPLIANCE.md.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import threading
from pathlib import Path

from core.applog import get_logger

log = get_logger("audit")

GENESIS = "0" * 64

# Fields that are hashed, in a fixed order, so the chain is reproducible.
_HASHED = ("ts", "actor", "action", "detail", "prev")


def _hash_entry(entry: dict) -> str:
    payload = json.dumps({k: entry[k] for k in _HASHED}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._path: Path | None = None
        self._last_hash = GENESIS

    def configure(self, path) -> None:
        """Point the log at a file and seed the chain head from its last entry."""
        with self._lock:
            self._path = Path(path)
            self._last_hash = GENESIS
            try:
                if self._path.exists():
                    last = None
                    with open(self._path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                last = line
                    if last:
                        self._last_hash = json.loads(last).get("hash", GENESIS)
            except Exception as e:
                log.warning("Could not read existing audit log: %s", e)

    def record(self, action: str, detail: str = "", actor: str = "system") -> None:
        """Append one chained, timestamped entry. No-op until configured."""
        with self._lock:
            if not self._path:
                return
            entry = {
                "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "actor": str(actor),
                "action": str(action),
                "detail": str(detail),
                "prev": self._last_hash,
            }
            entry["hash"] = _hash_entry(entry)
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
                self._last_hash = entry["hash"]
            except Exception as e:
                log.warning("Could not write audit entry: %s", e)

    def verify(self) -> dict:
        """Recompute the hash chain and report integrity."""
        with self._lock:
            path = self._path
        if not path or not Path(path).exists():
            return {"ok": True, "entries": 0, "intact": True}
        prev = GENESIS
        n = 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    e = json.loads(line)
                    if e.get("prev") != prev or _hash_entry(e) != e.get("hash"):
                        return {"ok": True, "entries": n, "intact": False, "broken_at": i}
                    prev = e["hash"]
                    n += 1
        except Exception as ex:
            return {"ok": False, "error": str(ex)}
        return {"ok": True, "entries": n, "intact": True}


AUDIT = AuditLog()

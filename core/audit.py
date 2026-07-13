# core/audit.py
"""Tamper-evident, append-only audit trail.

Business/facility buyers (and any future regulated path — FDA 21 CFR Part 11,
EU Annex 11) expect a computer-generated, time-stamped record of who changed
what and when, that cannot be silently edited. This is a lightweight foundation:
each entry stores the hash of the previous entry, forming a chain — altering a
past entry breaks verification. Deleting trailing entries would leave a shorter
but internally-consistent chain, so an out-of-band anchor (``<log>.tip``,
recording the true entry count + head hash, updated on every write) is
cross-checked so tail-truncation is detected too. (A privileged adversary who
rewrites both the log and the anchor can still defeat it — a tamper-*evident*,
not tamper-*proof*, record.)

It is NOT a validated Part-11 system on its own (that needs enforced per-user
identity, e-signatures, and formal validation), but it is a real procurement
differentiator now and the correct substrate to build on later. See COMPLIANCE.md.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
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
        self._tip_path: Path | None = None
        self._last_hash = GENESIS
        self._count = 0
        self._anchor_broken = False

    def _read_tip(self) -> dict | None:
        """The out-of-band anchor: {count, hash} of the true chain tip. Linkage
        alone can't detect deleting trailing entries (the shorter chain still
        verifies from genesis); this records the real length + head so a
        tail-truncation is caught."""
        try:
            if self._tip_path and self._tip_path.exists():
                return json.loads(self._tip_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return None

    def _write_tip(self) -> None:
        if not self._tip_path:
            return
        try:
            tmp = self._tip_path.with_name(self._tip_path.name + ".tmp")
            tmp.write_text(json.dumps({"count": self._count, "hash": self._last_hash}),
                           encoding="utf-8")
            os.replace(tmp, self._tip_path)
        except Exception as e:
            log.warning("Could not write audit anchor: %s", e)

    def configure(self, path) -> None:
        """Point the log at a file and seed the chain head from its last entry."""
        with self._lock:
            self._path = Path(path)
            self._tip_path = self._path.with_name(self._path.name + ".tip")
            self._last_hash = GENESIS
            self._count = 0
            self._anchor_broken = False
            try:
                if self._path.exists():
                    last, n = None, 0
                    with open(self._path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                last = line
                                n += 1
                    self._count = n
                    if last:
                        self._last_hash = json.loads(last).get("hash", GENESIS)
            except Exception as e:
                log.warning("Could not read existing audit log: %s", e)
            # Catch a truncation that happened while the hub was down: the anchor
            # remembers the true length/head from the last write.
            tip = self._read_tip()
            if tip is not None:
                tc = int(tip.get("count", 0))
                if tc > self._count or (tc == self._count and tip.get("hash") != self._last_hash):
                    self._anchor_broken = True
                    log.error("Audit anchor mismatch: log has %d entr(ies) (head %s), anchor "
                              "expects %d (head %s) — the audit log may have been truncated.",
                              self._count, self._last_hash[:12], tc, str(tip.get("hash"))[:12])

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
                self._count += 1
                self._write_tip()
            except Exception as e:
                log.warning("Could not write audit entry: %s", e)

    def verify(self) -> dict:
        """Recompute the hash chain and report integrity."""
        with self._lock:
            path = self._path
            anchor_broken = self._anchor_broken
            tip = self._read_tip()
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
        result = {"ok": True, "entries": n, "intact": True, "anchored": tip is not None}
        # Cross-check the anchor: a tail-truncation leaves an internally-consistent
        # shorter chain the linkage check can't catch, but the anchor still knows
        # the true length/head.
        if anchor_broken:
            result["intact"] = False
            result["reason"] = "anchor mismatch detected at startup (possible truncation)"
        elif tip is not None:
            tc = int(tip.get("count", 0))
            if tc > n or (tc == n and tip.get("hash") != prev):
                result["intact"] = False
                result["reason"] = "log disagrees with anchor (possible tail truncation)"
        return result


AUDIT = AuditLog()

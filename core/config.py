# core/config.py
from __future__ import annotations
import json, logging, os, threading
from pathlib import Path

from core.config_schema import normalize_config

log = logging.getLogger("hub.config")

class Config:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.data = {"interval_sec": 5, "pull_enabled": True, "auto_provision": True, "provision_token": ""}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
                else:
                    log.warning("config.json is not a JSON object; ignoring its contents")
            except Exception as e:
                # A corrupt/half-written file must not silently discard the user's
                # settings. Preserve it for recovery instead of overwriting it on
                # the next save, and start from defaults.
                log.error("config.json could not be parsed (%s); preserving it and using defaults", e)
                try:
                    corrupt = self.path.with_name(self.path.name + ".corrupt")
                    os.replace(self.path, corrupt)
                    log.error("moved unparseable config to %s", corrupt.name)
                except OSError:
                    pass
        # Coerce hand-edited values to safe types/ranges so a bad file can't
        # crash the hub; surface every correction in the log.
        self.data, _warnings = normalize_config(self.data)
        for w in _warnings:
            log.warning("config: %s", w)

    def _write_atomic(self, data: dict) -> None:
        """Persist config crash-safely: write a temp file in the same directory,
        fsync it, then atomically rename over the target. A crash/power-loss can
        never leave a truncated config.json (which would reset every setting)."""
        payload = json.dumps(data, indent=2)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
        # Config can hold SMTP/webhook/token secrets — keep it owner-only.
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def save(self):
        with self.lock:
            self._write_atomic(self.data)

    # convenience
    def get(self, k, default=None):
        with self.lock:
            return self.data.get(k, default)

    def set(self, k, v):
        with self.lock:
            self.data[k] = v
            self.data, warns = normalize_config(self.data)
            self.save()
        for w in warns:
            log.warning("config: %s", w)

    def update(self, mapping: dict):
        """Merge keys from mapping into config and persist.

        The merged result is re-normalised so programmatic/API writes are coerced
        to safe types exactly like a hand-edited file is on load — otherwise a
        POST /api/config could persist a value that crashes the next startup.

        The change is recorded in the tamper-evident audit trail by KEY NAME
        only — never the values, which may be secrets (tokens, SMTP passwords).
        """
        if not isinstance(mapping, dict):
            return
        with self.lock:
            self.data.update(mapping)
            self.data, warns = normalize_config(self.data)
            self.save()
        for w in warns:
            log.warning("config: %s", w)
        try:
            from core.audit import AUDIT
            keys = ", ".join(sorted(str(k) for k in mapping))
            AUDIT.record("config.update", detail=keys)
        except Exception:
            pass

    def to_dict(self) -> dict:
        with self.lock:
            return dict(self.data)

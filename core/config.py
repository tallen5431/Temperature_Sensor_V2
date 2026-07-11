# core/config.py
from __future__ import annotations
import json, logging, threading
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
                log.warning("config.json could not be parsed (%s); using defaults", e)
        # Coerce hand-edited values to safe types/ranges so a bad file can't
        # crash the hub; surface every correction in the log.
        self.data, _warnings = normalize_config(self.data)
        for w in _warnings:
            log.warning("config: %s", w)

    def save(self):
        with self.lock:
            self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    # convenience
    def get(self, k, default=None):
        with self.lock:
            return self.data.get(k, default)

    def set(self, k, v):
        with self.lock:
            self.data[k] = v
            self.save()

    def update(self, mapping: dict):
        """Merge keys from mapping into config and persist.

        The change is recorded in the tamper-evident audit trail by KEY NAME
        only — never the values, which may be secrets (tokens, SMTP passwords).
        """
        if not isinstance(mapping, dict):
            return
        with self.lock:
            self.data.update(mapping)
            self.save()
        try:
            from core.audit import AUDIT
            keys = ", ".join(sorted(str(k) for k in mapping))
            AUDIT.record("config.update", detail=keys)
        except Exception:
            pass

    def to_dict(self) -> dict:
        with self.lock:
            return dict(self.data)

# core/config.py
from __future__ import annotations
import json, threading
from pathlib import Path

class Config:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.data = {"interval_sec": 5, "pull_enabled": True, "auto_provision": True, "provision_token": ""}
        if self.path.exists():
            try:
                self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except Exception:
                pass

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
        """Merge keys from mapping into config and persist."""
        if not isinstance(mapping, dict):
            return
        with self.lock:
            self.data.update(mapping)
            self.save()

    def to_dict(self) -> dict:
        with self.lock:
            return dict(self.data)

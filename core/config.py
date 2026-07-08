# core/config.py
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from pathlib import Path

from core.applog import get_logger

log = get_logger("config")

# Keys that must never be serialized into an API response. "password" covers the
# generic password fields under ui_auth and mqtt (in addition to smtp_password).
SECRET_KEYS = {"provision_token", "server_token", "smtp_password", "password"}

# Neutral factory defaults. A shipped unit shows *no* personal data, *no* joke
# labels, and a professional, white-labelable brand. Everything here is
# overridable by the maker (config.example.json) or the customer (config.json /
# config.local.json) without touching code.
DEFAULTS: dict = {
    "interval_sec": 5,
    "auto_provision": True,
    "pull_enabled": True,
    "provision_token": "",  # auto-generated on first run if empty
    "branding": {
        "product_name": "ThermaHub",
        "brand_name": "ThermaHub",
        "support_url": "https://example.com/support",
        "primary_color": "#00bcd4",
        "copyright": "ThermaHub",
        "logo_path": "/assets/logo.svg",
    },
    "settings": {
        "default_unit": "celsius",  # "celsius" | "fahrenheit"
        "timezone": "",  # empty = server local time
        "vpd_leaf_offset_c": 0.0,  # leaf-below-air offset for VPD (growers use ~2.0)
    },
    "notifications": {
        "enabled": False,
        "recipients": [],
        "webhook_url": "",
        "debounce_sec": 900,
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "smtp_from": "",
        "smtp_tls": True,
    },
    "calibration": {},          # {"<probe_id>": {"offset_c": 0.0, "gain": 1.0}}
    "alert_thresholds": {"default": {"min": 2, "max": 8}},  # fridge defaults
    "probe_names": {},
    # Log retention: keep recent readings full-resolution, thin older ones, and
    # drop anything past downsample_days — so a 24/7 log can't fill the disk.
    "retention": {
        "enabled": True,
        "raw_days": 14,                 # keep every reading for this many days
        "downsample_days": 365,         # keep thinned readings up to here, then drop
        "downsample_interval_min": 15,  # older data: ~1 reading per probe per N min
    },
    # Optional dashboard login (shared office/lab LANs). Off by default so a
    # single-user home setup stays frictionless.
    "ui_auth": {"enabled": False, "username": "", "password": ""},
    # Homelab / self-hosted integrations.
    "metrics": {"enabled": True},   # Prometheus /metrics endpoint
    "mqtt": {                       # off by default; publishes to Home Assistant etc.
        "enabled": False,
        "host": "localhost",
        "port": 1883,
        "username": "",
        "password": "",
        "base_topic": "thermahub",
        "discovery_prefix": "homeassistant",
        "discovery_enabled": True,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into a copy of base (nested dicts merged)."""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    """Persistent, thread-safe configuration.

    Writes are atomic (temp file + os.replace) so a crash mid-save can never
    leave the customer with a truncated config.json. A ``config.local.json``
    sidecar (gitignored) is layered on top for per-customer overrides so the
    shipped example stays clean.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.local_path = self.path.with_name("config.local.json")
        self.lock = threading.RLock()
        self.data = _deep_merge(DEFAULTS, {})

        # Base config (may have been copied from the example on first run).
        self.data = _deep_merge(self.data, self._read_json(self.path))
        # Per-customer overrides win.
        self.data = _deep_merge(self.data, self._read_json(self.local_path))

    @staticmethod
    def _read_json(p: Path) -> dict:
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception as e:
            log.warning("Could not parse %s (%s); ignoring it", p, e)
            return {}

    @staticmethod
    def _atomic_write(p: Path, data: dict) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".cfg-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)  # atomic on POSIX and Windows
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass

    def save(self) -> None:
        """Persist customer-facing config to config.local.json atomically.

        We never rewrite the shipped/example base file; overrides live in the
        sidecar so a factory reset is just deleting config.local.json.
        """
        with self.lock:
            self._atomic_write(self.local_path, self.data)

    # convenience -------------------------------------------------------------
    def get(self, k, default=None):
        with self.lock:
            return self.data.get(k, default)

    def set(self, k, v):
        with self.lock:
            self.data[k] = v
            self.save()

    def update(self, mapping: dict):
        if not isinstance(mapping, dict):
            return
        with self.lock:
            self.data = _deep_merge(self.data, mapping)
            self.save()
        # Record the change (top-level keys only — never the values, which may
        # include secrets) in the tamper-evident audit trail.
        try:
            from core.audit import AUDIT
            AUDIT.record("config.update", detail=",".join(sorted(mapping.keys())))
        except Exception:
            pass

    def to_dict(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.data))  # deep copy

    def public_dict(self) -> dict:
        """Config with all secrets redacted — safe to return from the API."""
        return redact_secrets(self.to_dict())


def redact_secrets(obj):
    """Recursively replace any secret-keyed value with a redaction marker."""
    if isinstance(obj, dict):
        return {
            k: ("***set***" if (k in SECRET_KEYS and v) else redact_secrets(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact_secrets(v) for v in obj]
    return obj


def ensure_config_file(config_path: Path, example_path: Path) -> None:
    """On first run, seed config.json from the shipped example if it's missing."""
    config_path = Path(config_path)
    example_path = Path(example_path)
    if config_path.exists():
        return
    try:
        if example_path.exists():
            shutil.copyfile(example_path, config_path)
            log.info("First run: created %s from %s", config_path.name, example_path.name)
    except Exception as e:
        log.warning("Could not seed %s from example: %s", config_path, e)

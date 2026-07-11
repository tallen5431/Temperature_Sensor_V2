"""Validation / normalisation for the runtime config (``config.json``).

A customer or support engineer may hand-edit ``config.json`` — a partial file,
a string where a number belongs, an object replaced by ``null``.  None of that
should ever crash the hub.  :func:`normalize_config` coerces every known field
to a sane type and range, replacing anything invalid with a documented default,
and returns a list of human-readable warnings for the log.  Unknown keys are
left untouched so the config stays forward-compatible.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Tuple

Warnings = List[str]


def _to_number(val: Any, minimum, integer: bool):
    """Return ``(value, ok)`` — ``ok`` is False when ``val`` is not a finite number."""
    try:
        n = float(val)
    except (TypeError, ValueError):
        return None, False
    if math.isnan(n) or math.isinf(n):
        return None, False
    if integer:
        n = int(n)
    if minimum is not None and n < minimum:
        n = int(minimum) if integer else float(minimum)
    return n, True


def _coerce_bool(val: Any):
    """Return ``(bool, recognised)``."""
    if isinstance(val, bool):
        return val, True
    if isinstance(val, (int, float)):
        return bool(val), True
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True, True
        if s in ("0", "false", "no", "off", ""):
            return False, True
    return None, False


# (key, default, minimum, is_integer)
_NUMBERS = [
    ("interval_sec", 5, 0.5, False),
    ("probe_online_timeout_sec", 60, 1, True),
    ("retention_days", 0, 0, True),
    ("alert_freshness_sec", 600, 1, True),
    ("offline_after_sec", 300, 1, True),
    ("alert_hysteresis_c", 0.5, 0, False),
]
_BOOLS = [("pull_enabled", True), ("auto_provision", True)]
_DICTS = ["probe_names", "alert_thresholds", "calibration_offsets", "probe_intervals"]

_NOTIF_BOOLS = [("enabled", False), ("notify_recovery", True), ("offline_alerts", True)]
_EMAIL_BOOLS = [("enabled", False), ("use_tls", True)]


def _fix_number(d: Dict[str, Any], key, default, minimum, integer, warns: Warnings):
    if key not in d:
        return
    raw = d[key]
    n, ok = _to_number(raw, minimum, integer)
    if not ok:
        warns.append(f"{key}={raw!r} is not a number; using {default}")
        d[key] = default
        return
    d[key] = n
    try:
        if float(raw) != float(n):
            warns.append(f"{key}={raw!r} adjusted to {n}")
    except (TypeError, ValueError):
        warns.append(f"{key}={raw!r} adjusted to {n}")


def _fix_bool(d: Dict[str, Any], key, default, warns: Warnings, label=None):
    if key not in d or isinstance(d[key], bool):
        return
    raw = d[key]
    b, ok = _coerce_bool(raw)
    if not ok:
        b = default
    warns.append(f"{label or key}={raw!r} coerced to {b}")
    d[key] = b


def normalize_config(raw: Any) -> Tuple[Dict[str, Any], Warnings]:
    """Return ``(clean_config, warnings)``.  Never raises."""
    warns: Warnings = []
    if not isinstance(raw, dict):
        return {}, ["top-level config is not an object; using defaults"]

    cfg = copy.deepcopy(raw)

    for key, default, minimum, integer in _NUMBERS:
        _fix_number(cfg, key, default, minimum, integer, warns)

    for key, default in _BOOLS:
        _fix_bool(cfg, key, default, warns)

    if "provision_token" in cfg and not isinstance(cfg["provision_token"], str):
        warns.append("provision_token must be a string; resetting to empty")
        cfg["provision_token"] = ""

    for key in _DICTS:
        if key in cfg and not isinstance(cfg[key], dict):
            warns.append(f"{key} must be an object; resetting to empty")
            cfg[key] = {}

    # --- notifications subtree -------------------------------------------------
    notif = cfg.get("notifications")
    if "notifications" in cfg and not isinstance(notif, dict):
        warns.append("notifications must be an object; resetting")
        cfg["notifications"] = {}
        notif = cfg["notifications"]

    if isinstance(notif, dict):
        for key, default in _NOTIF_BOOLS:
            _fix_bool(notif, key, default, warns, label=f"notifications.{key}")
        _fix_number(notif, "cooldown_sec", 1800, 1, True, warns)

        email = notif.get("email")
        if "email" in notif and not isinstance(email, dict):
            warns.append("notifications.email must be an object; resetting")
            notif["email"] = {}
            email = notif["email"]
        if isinstance(email, dict):
            for key, default in _EMAIL_BOOLS:
                _fix_bool(email, key, default, warns, label=f"notifications.email.{key}")
            _fix_number(email, "smtp_port", 587, 1, True, warns)
            if email.get("smtp_port", 1) > 65535:
                warns.append("notifications.email.smtp_port out of range; using 587")
                email["smtp_port"] = 587

        webhook = notif.get("webhook")
        if "webhook" in notif and not isinstance(webhook, dict):
            warns.append("notifications.webhook must be an object; resetting")
            notif["webhook"] = {}
            webhook = notif["webhook"]
        if isinstance(webhook, dict):
            _fix_bool(webhook, "enabled", False, warns, label="notifications.webhook.enabled")

    return cfg, warns

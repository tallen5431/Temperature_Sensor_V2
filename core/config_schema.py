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
    ("rate_alert_c", 0.0, 0, False),
    ("rate_window_min", 10, 1, True),
    ("resolution_bits", 11, 9, True),
]
_BOOLS = [("pull_enabled", True), ("auto_provision", True)]
_DICTS = ["probe_names", "alert_thresholds", "calibration_offsets", "probe_intervals",
          "probe_resolutions"]

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

    # resolution_bits also has an UPPER bound (DS18B20 supports 9..12 bit); the
    # _NUMBERS pass only enforces the 9 floor.
    if "resolution_bits" in cfg:
        try:
            if int(cfg["resolution_bits"]) > 12:
                warns.append(f"resolution_bits={cfg['resolution_bits']!r} > 12; using 12")
                cfg["resolution_bits"] = 12
        except (TypeError, ValueError):
            pass

    for key, default in _BOOLS:
        _fix_bool(cfg, key, default, warns)

    if "provision_token" in cfg and not isinstance(cfg["provision_token"], str):
        warns.append("provision_token must be a string; resetting to empty")
        cfg["provision_token"] = ""

    for key in _DICTS:
        if key in cfg and not isinstance(cfg[key], dict):
            warns.append(f"{key} must be an object; resetting to empty")
            cfg[key] = {}

    # Coerce the inner min/max of each per-probe threshold. A hand-edited string
    # bound (e.g. {"default": {"max": "30"}}) would otherwise raise TypeError in
    # the alert loop's comparisons and silently kill ALL alerting + retention.
    thresholds = cfg.get("alert_thresholds")
    if isinstance(thresholds, dict):
        for pid, entry in list(thresholds.items()):
            if not isinstance(entry, dict):
                warns.append(f"alert_thresholds[{pid!r}] must be an object; dropping")
                del thresholds[pid]
                continue
            for bound in ("min", "max"):
                if bound in entry and entry[bound] is not None:
                    n, ok = _to_number(entry[bound], None, False)  # temps may be negative
                    if not ok:
                        warns.append(
                            f"alert_thresholds[{pid!r}].{bound}={entry[bound]!r} is not a number; dropping")
                        entry.pop(bound, None)
                    else:
                        entry[bound] = n

    # --- ui_auth / metrics / settings / mqtt subtrees --------------------------
    # These reach app.py / consumers unguarded; a wrong-typed value (e.g. a
    # numeric ui_auth.username) would crash startup. Coerce them like the rest.
    ua = cfg.get("ui_auth")
    if "ui_auth" in cfg and not isinstance(ua, dict):
        warns.append("ui_auth must be an object; resetting")
        cfg["ui_auth"] = {}
        ua = cfg["ui_auth"]
    if isinstance(ua, dict):
        _fix_bool(ua, "enabled", False, warns, label="ui_auth.enabled")
        for f in ("username", "password"):
            if f in ua and not isinstance(ua[f], str):
                warns.append(f"ui_auth.{f} must be a string; coercing")
                ua[f] = "" if ua[f] is None else str(ua[f])

    metrics = cfg.get("metrics")
    if "metrics" in cfg and not isinstance(metrics, dict):
        warns.append("metrics must be an object; resetting")
        cfg["metrics"] = {}
        metrics = cfg["metrics"]
    if isinstance(metrics, dict):
        _fix_bool(metrics, "enabled", True, warns, label="metrics.enabled")

    settings = cfg.get("settings")
    if "settings" in cfg and not isinstance(settings, dict):
        warns.append("settings must be an object; resetting")
        cfg["settings"] = {}
        settings = cfg["settings"]
    if isinstance(settings, dict):
        _fix_number(settings, "vpd_leaf_offset_c", 0.0, None, False, warns)

    mqtt = cfg.get("mqtt")
    if "mqtt" in cfg and not isinstance(mqtt, dict):
        warns.append("mqtt must be an object; resetting")
        cfg["mqtt"] = {}
        mqtt = cfg["mqtt"]
    if isinstance(mqtt, dict):
        _fix_bool(mqtt, "enabled", False, warns, label="mqtt.enabled")
        if "port" in mqtt:
            _fix_number(mqtt, "port", 1883, 1, True, warns)
            if mqtt.get("port", 1) > 65535:
                warns.append("mqtt.port out of range; using 1883")
                mqtt["port"] = 1883
        for f in ("host", "username", "password", "base_topic", "discovery_prefix"):
            if f in mqtt and mqtt[f] is not None and not isinstance(mqtt[f], str):
                warns.append(f"mqtt.{f} must be a string; coercing")
                mqtt[f] = str(mqtt[f])

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

        summary = notif.get("daily_summary")
        if "daily_summary" in notif and not isinstance(summary, dict):
            warns.append("notifications.daily_summary must be an object; resetting")
            notif["daily_summary"] = {}
            summary = notif["daily_summary"]
        if isinstance(summary, dict):
            _fix_bool(summary, "enabled", False, warns, label="notifications.daily_summary.enabled")
            _fix_number(summary, "hour", 8, 0, True, warns)
            if summary.get("hour", 0) > 23:
                warns.append("notifications.daily_summary.hour out of range; using 8")
                summary["hour"] = 8

    return cfg, warns

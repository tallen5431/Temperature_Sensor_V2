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
    except (TypeError, ValueError, OverflowError):
        # OverflowError: a JSON integer literal too large for a C double (~1e308)
        # — float(huge_int) raises it, and it is NOT a ValueError subclass, so it
        # would otherwise escape normalize_config's "never raises" contract.
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


# (key, default, minimum, maximum, is_integer). ``maximum`` is None for the
# fields where "large" is merely unusual rather than invalid — a 30-day
# retention and a 30-year one are both things an operator may legitimately mean.
_NUMBERS = [
    ("interval_sec", 5, 0.5, None, False),
    ("probe_online_timeout_sec", 60, 1, None, True),
    ("retention_days", 0, 0, None, True),
    ("alert_freshness_sec", 600, 1, None, True),
    ("offline_after_sec", 300, 1, None, True),
    ("alert_hysteresis_c", 0.5, 0, None, False),
    ("rate_alert_c", 0.0, 0, None, False),
    ("rate_window_min", 10, 1, None, True),
    # 9..12 bit is the DS18B20's own range, so the ceiling is a real limit and
    # clamping to it is the right answer rather than a fallback.
    ("resolution_bits", 11, 9, 12, True),
    # Tuning knobs every consumer already defends itself against, which is
    # exactly why they belong here too: an unnormalised value is silently
    # ignored at the point of use while config.json keeps showing it, so the
    # setting looks applied and is not. Same reasoning as probe_intervals below.
    ("probe_sample_sec", 60, 1, None, True),
    ("health_fresh_sec", 120, 1, None, False),
    ("probe_prune_after_sec", 3600, 1, None, True),
]
_BOOLS = [("pull_enabled", True), ("auto_provision", True)]
_DICTS = ["probe_names", "alert_thresholds", "calibration_offsets", "probe_intervals",
          "probe_resolutions"]

_NOTIF_BOOLS = [("enabled", False), ("notify_recovery", True), ("offline_alerts", True)]
_EMAIL_BOOLS = [("enabled", False), ("use_tls", True)]


def _fix_number(d: Dict[str, Any], key, default, minimum, integer, warns: Warnings,
                maximum=None, over_max=None, label=None):
    """Coerce ``d[key]`` to a number inside ``[minimum, maximum]``.

    ``label`` names the field in warnings, matching :func:`_fix_bool`. Nested
    fields need it: three subtrees have an ``enabled``, two have a port, and
    ``hour=99 adjusted to 8`` does not say whose hour it was.

    ``maximum`` bounds the top the way ``minimum`` bounds the bottom, so a field
    with both declares them together instead of having its ceiling hand-rolled
    afterwards — five of them were, each with its own wording and only one
    guarded against a non-numeric value.

    What to do when a value exceeds the ceiling differs by field, so ``over_max``
    says which. Absent means clamp to ``maximum``: 12 bits is the sensor's real
    limit, so ``resolution_bits: 20`` genuinely means 12. Passing a value
    substitutes that instead, for ceilings that mark the input as nonsense rather
    than merely too large — an SMTP port of 99999 becomes 587, because 65535
    would be just as unusable and far more confusing to find in a log.
    """
    if key not in d:
        return
    name = label or key
    raw = d[key]
    n, ok = _to_number(raw, minimum, integer)
    if not ok:
        warns.append(f"{name}={raw!r} is not a number; using {default}")
        d[key] = default
        return
    if maximum is not None and n > maximum:
        n = over_max if over_max is not None else maximum
        n = int(n) if integer else float(n)
    d[key] = n
    try:
        if float(raw) != float(n):
            warns.append(f"{name}={raw!r} adjusted to {n}")
    except (TypeError, ValueError):
        warns.append(f"{name}={raw!r} adjusted to {n}")


def _subtree(parent: Dict[str, Any], key: str, warns: Warnings, label=None):
    """Return ``parent[key]`` as a dict, or ``None`` when the key is absent.

    A present-but-wrong-typed subtree (``"mqtt": 5``) is reset to ``{}`` with a
    warning, so every caller can collapse to a single ``is not None`` check
    instead of repeating the three-step present/typed/rebind dance nine times.

    Absent stays absent on purpose: normalising a config must not invent keys the
    operator never wrote — ``normalize_config({})`` returns ``{}``, and callers
    throughout the hub read "key missing" as "use the built-in default".
    """
    if key not in parent:
        return None
    val = parent[key]
    if not isinstance(val, dict):
        warns.append(f"{label or key} must be an object; resetting")
        parent[key] = {}
        return parent[key]
    return val


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

    for key, default, minimum, maximum, integer in _NUMBERS:
        _fix_number(cfg, key, default, minimum, integer, warns, maximum=maximum)

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

    # Coerce the per-probe scalar maps the same way. Every CONSUMER of these
    # already defends itself (desired_probe_config and _calibration_offset both
    # swallow a bad value and fall back), so an uncoerced entry does not crash
    # anything -- which is exactly the problem. It is silently ignored, while the
    # Devices card renders the RAW config value: hand-edit an interval to "30s"
    # and the card reads "Interval: 30s s" while the probe keeps running the
    # global interval. Correcting it here makes the stored config, the value in
    # effect, and the value displayed agree, and tells the operator what changed
    # instead of leaving a setting that looks applied but is not.
    for key, minimum, allow_negative in (("probe_intervals", 0.5, False),
                                         ("probe_resolutions", 9, False),
                                         ("calibration_offsets", None, True)):
        table = cfg.get(key)
        if not isinstance(table, dict):
            continue
        for pid, raw in list(table.items()):
            if raw is None:
                del table[pid]
                continue
            n, ok = _to_number(raw, None if allow_negative else minimum,
                               key == "probe_resolutions")
            if not ok:
                warns.append(f"{key}[{pid!r}]={raw!r} is not a number; dropping")
                del table[pid]
            else:
                # Warn only when the VALUE moved (a clamp), not when the type
                # merely tightened ("1800" -> 1800.0) -- matching _fix_number, so
                # a config written with quoted numbers doesn't flood the log.
                try:
                    changed = float(raw) != float(n)
                except (TypeError, ValueError):
                    changed = True
                if changed:
                    warns.append(f"{key}[{pid!r}]={raw!r} adjusted to {n}")
                table[pid] = n

    # --- ui_auth / metrics / settings / mqtt subtrees --------------------------
    # These reach app.py / consumers unguarded; a wrong-typed value (e.g. a
    # numeric ui_auth.username) would crash startup. Coerce them like the rest.
    ua = _subtree(cfg, "ui_auth", warns)
    if ua is not None:
        _fix_bool(ua, "enabled", False, warns, label="ui_auth.enabled")
        for f in ("username", "password"):
            if f in ua and not isinstance(ua[f], str):
                warns.append(f"ui_auth.{f} must be a string; coercing")
                ua[f] = "" if ua[f] is None else str(ua[f])

    metrics = _subtree(cfg, "metrics", warns)
    if metrics is not None:
        _fix_bool(metrics, "enabled", True, warns, label="metrics.enabled")

    settings = _subtree(cfg, "settings", warns)
    if settings is not None:
        _fix_number(settings, "vpd_leaf_offset_c", 0.0, None, False, warns,
                    label="settings.vpd_leaf_offset_c")

    # --- upstream (multi-site roll-up; see core/forwarder.py) ---------------
    upstream = _subtree(cfg, "upstream", warns)
    if upstream is not None:
        _fix_bool(upstream, "enabled", False, warns, label="upstream.enabled")
        for f in ("url", "token", "site"):
            if f in upstream and upstream[f] is not None and not isinstance(upstream[f], str):
                warns.append(f"upstream.{f} must be a string; coercing")
                upstream[f] = str(upstream[f])
        _fix_number(upstream, "interval_sec", 30, 5, True, warns,
                    label="upstream.interval_sec")
        # PROTOCOL.md §7 caps /ingest_csv at 1000 rows per request; a larger
        # batch would be rejected wholesale every cycle and the backlog would
        # never drain. The cap is real, so clamp to it rather than substituting.
        _fix_number(upstream, "batch", 500, 1, True, warns, maximum=1000,
                    label="upstream.batch")

    mqtt = _subtree(cfg, "mqtt", warns)
    if mqtt is not None:
        _fix_bool(mqtt, "enabled", False, warns, label="mqtt.enabled")
        _fix_number(mqtt, "port", 1883, 1, True, warns, maximum=65535,
                    over_max=1883, label="mqtt.port")
        for f in ("host", "username", "password", "base_topic", "discovery_prefix"):
            if f in mqtt and mqtt[f] is not None and not isinstance(mqtt[f], str):
                warns.append(f"mqtt.{f} must be a string; coercing")
                mqtt[f] = str(mqtt[f])

    # --- notifications subtree -------------------------------------------------
    notif = _subtree(cfg, "notifications", warns)
    if notif is not None:
        for key, default in _NOTIF_BOOLS:
            _fix_bool(notif, key, default, warns, label=f"notifications.{key}")
        _fix_number(notif, "cooldown_sec", 1800, 1, True, warns,
                    label="notifications.cooldown_sec")

        # Back-online confirmation window for flap damping. ``null`` (or absent)
        # means "auto" — self-tune to each probe's offline window — so it is left
        # untouched; a present value must be an int >= 0 (0 disables damping). A
        # garbage value is dropped back to auto rather than silently pinned.
        if "flap_grace_sec" in notif and notif["flap_grace_sec"] is not None:
            n, ok = _to_number(notif["flap_grace_sec"], 0, True)
            if not ok:
                warns.append(
                    f"notifications.flap_grace_sec={notif['flap_grace_sec']!r} is not a "
                    "number; using auto")
                notif.pop("flap_grace_sec", None)
            else:
                notif["flap_grace_sec"] = n

        email = _subtree(notif, "email", warns, label="notifications.email")
        if email is not None:
            for key, default in _EMAIL_BOOLS:
                _fix_bool(email, key, default, warns, label=f"notifications.email.{key}")
            _fix_number(email, "smtp_port", 587, 1, True, warns, maximum=65535,
                        over_max=587, label="notifications.email.smtp_port")

        webhook = _subtree(notif, "webhook", warns, label="notifications.webhook")
        if webhook is not None:
            _fix_bool(webhook, "enabled", False, warns, label="notifications.webhook.enabled")

        summary = _subtree(notif, "daily_summary", warns,
                           label="notifications.daily_summary")
        if summary is not None:
            _fix_bool(summary, "enabled", False, warns, label="notifications.daily_summary.enabled")
            _fix_number(summary, "hour", 8, 0, True, warns, maximum=23, over_max=8,
                        label="notifications.daily_summary.hour")

    return cfg, warns

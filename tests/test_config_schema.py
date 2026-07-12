"""Tests for config validation/normalisation (core.config_schema).

A hand-edited or partial config.json must never crash the hub: bad types are
coerced, out-of-range values clamped, and every correction is reported.
"""
from core.config_schema import normalize_config


def test_valid_config_passes_unchanged():
    raw = {
        "interval_sec": 5,
        "probe_online_timeout_sec": 60,
        "retention_days": 7,
        "pull_enabled": True,
        "auto_provision": True,
        "provision_token": "",
        "probe_names": {"p1": "Fridge"},
        "notifications": {
            "enabled": True,
            "cooldown_sec": 1800,
            "email": {"enabled": False, "smtp_port": 587, "use_tls": True},
            "webhook": {"enabled": False, "url": ""},
        },
    }
    clean, warns = normalize_config(raw)
    assert warns == []
    assert clean["interval_sec"] == 5
    assert clean["notifications"]["email"]["smtp_port"] == 587


def test_string_threshold_bounds_are_coerced_to_numbers():
    # A hand-edited string bound must not survive to crash the alert loop; it is
    # coerced to a real number (a parseable string coerces silently).
    clean, _ = normalize_config(
        {"alert_thresholds": {"default": {"max": "30", "min": -18}}})
    mx = clean["alert_thresholds"]["default"]["max"]
    assert isinstance(mx, (int, float)) and mx == 30.0
    assert clean["alert_thresholds"]["default"]["min"] == -18  # negatives preserved


def test_non_numeric_threshold_bound_is_dropped():
    clean, warns = normalize_config(
        {"alert_thresholds": {"p1": {"max": "hot"}, "p2": "nonsense"}})
    assert "max" not in clean["alert_thresholds"]["p1"]     # unparseable bound dropped
    assert "p2" not in clean["alert_thresholds"]            # non-dict entry dropped
    assert warns


def test_numeric_ui_auth_credentials_are_stringified():
    # A numeric username/PIN would crash startup (.strip()/hmac) if left as int.
    clean, warns = normalize_config({"ui_auth": {"enabled": True, "username": 42, "password": 1234}})
    assert clean["ui_auth"]["username"] == "42"
    assert clean["ui_auth"]["password"] == "1234"
    assert warns


def test_bad_subtree_types_reset_not_crash():
    clean, _ = normalize_config({"ui_auth": "nope", "mqtt": 5, "metrics": [], "settings": None})
    assert clean["ui_auth"] == {}
    assert clean["mqtt"] == {}
    assert clean["metrics"] == {}


def test_string_numbers_are_coerced():
    clean, warns = normalize_config({"interval_sec": "5", "retention_days": "10"})
    assert clean["interval_sec"] == 5
    assert clean["retention_days"] == 10
    assert clean["retention_days"] == 10 and isinstance(clean["retention_days"], int)


def test_invalid_number_falls_back_to_default():
    clean, warns = normalize_config({"interval_sec": "not-a-number"})
    assert clean["interval_sec"] == 5
    assert any("interval_sec" in w for w in warns)


def test_below_minimum_is_clamped():
    clean, warns = normalize_config({"interval_sec": 0.1, "probe_online_timeout_sec": -5})
    assert clean["interval_sec"] == 0.5            # min read interval
    assert clean["probe_online_timeout_sec"] == 1  # min 1 second
    assert len(warns) == 2


def test_bool_coercion():
    clean, warns = normalize_config({"auto_provision": "false", "pull_enabled": 1})
    assert clean["auto_provision"] is False
    assert clean["pull_enabled"] is True
    assert len(warns) == 2


def test_non_dict_collections_reset():
    clean, warns = normalize_config({"probe_names": ["not", "a", "dict"], "calibration_offsets": "nope"})
    assert clean["probe_names"] == {}
    assert clean["calibration_offsets"] == {}
    assert len(warns) == 2


def test_notifications_non_dict_reset():
    clean, warns = normalize_config({"notifications": "enabled"})
    assert clean["notifications"] == {}
    assert any("notifications" in w for w in warns)


def test_smtp_port_out_of_range():
    clean, warns = normalize_config({"notifications": {"email": {"smtp_port": 99999}}})
    assert clean["notifications"]["email"]["smtp_port"] == 587
    assert any("smtp_port" in w for w in warns)


def test_nested_notification_bools_coerced():
    clean, warns = normalize_config({"notifications": {"enabled": "yes", "email": {"use_tls": "no"}}})
    assert clean["notifications"]["enabled"] is True
    assert clean["notifications"]["email"]["use_tls"] is False


def test_missing_keys_produce_no_warnings():
    clean, warns = normalize_config({})
    assert warns == []
    assert clean == {}


def test_garbage_top_level_returns_empty():
    clean, warns = normalize_config(["this", "is", "a", "list"])
    assert clean == {}
    assert warns


def test_input_is_not_mutated():
    raw = {"interval_sec": "5", "probe_names": "bad"}
    normalize_config(raw)
    assert raw["interval_sec"] == "5"   # original untouched (deep-copied)
    assert raw["probe_names"] == "bad"

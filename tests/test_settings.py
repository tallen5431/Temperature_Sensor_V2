"""Tests for the Settings notifications/MQTT config builders and the Devices
edit modal's unit conversions (pure logic)."""
from components.settings_panel import build_notifications_config, build_mqtt_config
from components.devices_panel import (
    temp_c_to_unit,
    temp_unit_to_c,
    delta_c_to_unit,
    delta_unit_to_c,
)


def _form(**over):
    base = dict(enabled=True, cooldown_min=30, recovery=True, email_enabled=True,
                host="smtp.x", port=587, tls=True, user="u", sender="from@x",
                to="to@x", webhook_enabled=False, url="", password="")
    base.update(over)
    return [base[k] for k in ("enabled", "cooldown_min", "recovery", "email_enabled",
                              "host", "port", "tls", "user", "sender", "to",
                              "webhook_enabled", "url", "password")]


def test_cooldown_minutes_to_seconds():
    cfg = build_notifications_config(*_form(cooldown_min=15))
    assert cfg["cooldown_sec"] == 900


def test_cooldown_floor_is_60s():
    cfg = build_notifications_config(*_form(cooldown_min=0))
    assert cfg["cooldown_sec"] == 60


def test_blank_password_keeps_existing():
    cfg = build_notifications_config(*_form(password=""), existing_password="stored-secret")
    assert cfg["email"]["password"] == "stored-secret"


def test_new_password_overrides():
    cfg = build_notifications_config(*_form(password="new-pw"), existing_password="old")
    assert cfg["email"]["password"] == "new-pw"


def test_invalid_port_falls_back():
    cfg = build_notifications_config(*_form(port="not-a-number"))
    assert cfg["email"]["smtp_port"] == 587


def test_strips_whitespace_and_coerces_bools():
    cfg = build_notifications_config(*_form(host="  smtp.y  ", enabled=1, email_enabled=0))
    assert cfg["email"]["smtp_host"] == "smtp.y"
    assert cfg["enabled"] is True
    assert cfg["email"]["enabled"] is False


def test_offline_alerts_default_and_override():
    assert build_notifications_config(*_form())["offline_alerts"] is True
    assert build_notifications_config(*_form(), offline_alerts=False)["offline_alerts"] is False


# --- Daily summary -----------------------------------------------------------

def test_daily_summary_defaults_off():
    cfg = build_notifications_config(*_form())
    assert cfg["daily_summary"] == {"enabled": False, "hour": 8}


def test_daily_summary_round_trip():
    cfg = build_notifications_config(*_form(), daily_summary_enabled=True,
                                     daily_summary_hour=7)
    assert cfg["daily_summary"] == {"enabled": True, "hour": 7}


def test_daily_summary_hour_clamped_and_fallback():
    assert build_notifications_config(
        *_form(), daily_summary_hour=99)["daily_summary"]["hour"] == 23
    assert build_notifications_config(
        *_form(), daily_summary_hour=-5)["daily_summary"]["hour"] == 0
    assert build_notifications_config(
        *_form(), daily_summary_hour="noon")["daily_summary"]["hour"] == 8


# --- MQTT (Settings -> Integrations) -----------------------------------------

def test_mqtt_config_round_trip():
    out = build_mqtt_config(True, " broker.local ", "1883", "ha", "pw", "setpoint", True)
    assert out == {"enabled": True, "host": "broker.local", "port": 1883,
                   "username": "ha", "password": "pw", "base_topic": "setpoint",
                   "discovery_enabled": True}


def test_mqtt_blank_password_keeps_saved():
    existing = {"password": "stored-secret", "discovery_prefix": "homeassistant"}
    out = build_mqtt_config(True, "b", 1883, "u", "", "setpoint", True, existing=existing)
    assert out["password"] == "stored-secret"
    # Keys the form does not expose survive a save untouched.
    assert out["discovery_prefix"] == "homeassistant"


def test_mqtt_new_password_overrides_and_fallbacks():
    out = build_mqtt_config(True, "b", "not-a-port", "u", "new-pw", "", False,
                            existing={"password": "old"})
    assert out["password"] == "new-pw"
    assert out["port"] == 1883               # unparseable port falls back
    assert out["base_topic"] == "setpoint"   # blank base topic falls back
    assert out["discovery_enabled"] is False


# --- Devices edit modal: unit-aware thresholds & calibration -----------------

def test_threshold_fahrenheit_round_trip():
    # Stored Celsius -> displayed Fahrenheit -> saved back to the same Celsius.
    assert temp_c_to_unit(2.0, "fahrenheit") == 35.6
    assert temp_unit_to_c(35.6, "fahrenheit") == 2.0
    assert temp_c_to_unit(30.0, "fahrenheit") == 86.0
    assert temp_unit_to_c(86.0, "fahrenheit") == 30.0


def test_offset_is_a_delta_not_an_absolute_temperature():
    # A calibration offset is a temperature DIFFERENCE: -0.5 C of correction is
    # -0.9 F (scale only, no +32 shift) — NOT 31.1 F.
    assert delta_c_to_unit(-0.5, "fahrenheit") == -0.9
    assert delta_unit_to_c(-0.9, "fahrenheit") == -0.5
    # Kelvin deltas are identical to Celsius deltas.
    assert delta_c_to_unit(-0.5, "kelvin") == -0.5
    assert delta_unit_to_c(-0.5, "kelvin") == -0.5


def test_kelvin_absolute_round_trip():
    assert temp_c_to_unit(0.0, "kelvin") == 273.15
    assert temp_unit_to_c(273.15, "kelvin") == 0.0


def test_celsius_and_none_pass_through():
    assert temp_c_to_unit(10.0, "celsius") == 10.0
    assert temp_unit_to_c(10.0, "celsius") == 10.0
    assert temp_c_to_unit(None, "fahrenheit") is None
    assert temp_unit_to_c(None, "fahrenheit") is None
    assert delta_c_to_unit(None, "fahrenheit") is None
    assert delta_unit_to_c(None, "fahrenheit") is None

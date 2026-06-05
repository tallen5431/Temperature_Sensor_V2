"""Tests for the Settings notifications-config builder (pure logic)."""
from components.settings_panel import build_notifications_config


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

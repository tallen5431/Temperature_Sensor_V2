"""Tests for notification channels and the dispatcher (core.notifications)."""
import pytest

import core.notifications as N
from core.config import Config
from core.notifications import Notifier, parse_recipients, send_email, send_webhook


def test_parse_recipients():
    assert parse_recipients("a@x.com, b@y.com; c@z.com") == ["a@x.com", "b@y.com", "c@z.com"]
    assert parse_recipients(["a@x.com", " b@y.com "]) == ["a@x.com", "b@y.com"]
    assert parse_recipients("") == []


def test_send_email_not_configured():
    ok, info = send_email({}, "subj", "body")
    assert ok is False and "not configured" in info


def test_webhook_error_does_not_leak_url_secret(monkeypatch):
    # Regression: a webhook URL can carry a bearer token in its path/query. On a
    # connection error, requests/urllib3 embed that token in the exception text
    # (host and path rendered separately), which the old whole-URL scrub missed,
    # leaking it to the hub log AND the Settings UI. The reported info must name
    # the host for diagnosis but never carry the token.
    SECRET = "TOK_SECRET_123"
    url = f"https://hooks.example.com/services/abc?token={SECRET}"

    def boom(*a, **k):
        raise N.requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='hooks.example.com', port=443): "
            f"Max retries exceeded with url: /services/abc?token={SECRET}")

    monkeypatch.setattr(N.requests, "post", boom)
    ok, info = send_webhook({"url": url}, {"message": "x"})
    assert ok is False
    assert SECRET not in info
    assert "hooks.example.com" in info


def test_send_email_success(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=0):
            sent["host"] = host
            sent["port"] = port
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starttls(self, context=None):
            sent["tls"] = True
        def login(self, user, pwd):
            sent["login"] = user
        def send_message(self, msg):
            sent["to"] = msg["To"]
            sent["subject"] = msg["Subject"]

    monkeypatch.setattr(N.smtplib, "SMTP", FakeSMTP)
    cfg = {"smtp_host": "smtp.test", "smtp_port": 587, "use_tls": True,
           "username": "u", "password": "p", "from": "a@test", "to": "b@test"}
    ok, info = send_email(cfg, "Hello", "Body")
    assert ok is True and info == "sent"
    assert sent["host"] == "smtp.test" and sent["tls"] is True
    assert sent["to"] == "b@test" and sent["subject"] == "Hello"


def test_send_webhook_success(monkeypatch):
    captured = {}

    class FakeResp:
        ok = True
        status_code = 200

    def fake_post(url, json=None, timeout=0):
        captured["url"] = url
        captured["json"] = json
        return FakeResp()

    monkeypatch.setattr(N.requests, "post", fake_post)
    ok, info = send_webhook({"url": "https://hook"}, {"message": "hi", "probe_id": "p"})
    assert ok is True and info == "sent"
    assert captured["url"] == "https://hook"
    assert captured["json"]["text"] == "hi"  # Slack-compatible field present


def test_send_webhook_http_error(monkeypatch):
    class FakeResp:
        ok = False
        status_code = 500

    monkeypatch.setattr(N.requests, "post", lambda *a, **k: FakeResp())
    ok, info = send_webhook({"url": "https://hook"}, {"message": "hi"})
    assert ok is False and "500" in info


def test_dispatch_runs_only_enabled_channels(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(N, "send_email", lambda cfg, s, b: (calls.append("email"), (True, "sent"))[1])
    monkeypatch.setattr(N, "send_webhook", lambda cfg, e: (calls.append("webhook"), (True, "sent"))[1])

    cfg = Config(tmp_path / "c.json")
    cfg.update({"notifications": {"enabled": True,
                                  "email": {"enabled": True, "smtp_host": "x", "to": "y"},
                                  "webhook": {"enabled": False, "url": ""}}})
    results = Notifier(cfg).dispatch({"subject": "s", "message": "m"})
    assert calls == ["email"]  # webhook disabled
    assert results == [("email", True, "sent")]


def test_dispatch_channel_failure_isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(N, "send_email", lambda cfg, s, b: (False, "boom"))
    monkeypatch.setattr(N, "send_webhook", lambda cfg, e: (True, "sent"))
    cfg = Config(tmp_path / "c.json")
    cfg.update({"notifications": {"enabled": True,
                                  "email": {"enabled": True, "smtp_host": "x", "to": "y"},
                                  "webhook": {"enabled": True, "url": "z"}}})
    results = Notifier(cfg).dispatch({"subject": "s", "message": "m"})
    # Both attempted; email failed, webhook still sent.
    assert ("email", False, "boom") in results
    assert ("webhook", True, "sent") in results


# --- send_email must never raise -------------------------------------------
# Its contract is (ok, reason). Notifier.dispatch does not wrap it, and neither
# does the Settings "Send test" callback, so anything that escapes becomes an
# unhandled callback error there and a bare "notification dispatch error" in the
# alert monitor's log — with nothing naming the field at fault.

BAD_HEADERS = [
    ("to", "chef@example.com\nBcc: attacker@evil.example"),
    ("to", "chef@example.com\r\nBcc: attacker@evil.example"),
    ("from", "hub@example.com\nX-Injected: yes"),
]


@pytest.mark.parametrize("field,value", BAD_HEADERS,
                         ids=[f"{f}-{i}" for i, (f, _v) in enumerate(BAD_HEADERS)])
def test_a_line_break_in_a_header_is_reported_not_raised(field, value):
    """Python's email package refuses these — correctly, it is header injection
    — by raising ValueError. That escaped send_email, whose whole job is to
    return a reason instead of raising."""
    from core.notifications import send_email
    cfg = {"smtp_host": "127.0.0.1", "smtp_port": 2525,
           "to": "chef@example.com", field: value}
    ok, info = send_email(cfg, "Chest Freezer", "body")
    assert ok is False
    assert "line break" in info, info


def test_a_line_break_in_the_subject_is_reported_not_raised():
    from core.notifications import send_email
    cfg = {"smtp_host": "127.0.0.1", "smtp_port": 2525, "to": "chef@example.com"}
    ok, info = send_email(cfg, "Chest Freezer\nBcc: attacker@evil.example", "body")
    assert ok is False and "line break" in info


def test_the_dispatcher_survives_it_too():
    """The path a real breach takes."""
    from core.notifications import Notifier

    class _Cfg:
        def get(self, key, default=None):
            return {"notifications": {
                "enabled": True,
                "email": {"enabled": True, "smtp_host": "127.0.0.1",
                          "smtp_port": 2525,
                          "to": "chef@example.com\nBcc: attacker@evil.example"},
            }}.get(key, default)

    results = Notifier(_Cfg()).dispatch({"subject": "s", "message": "m"})
    assert results == [("email", False, results[0][2])]
    assert "line break" in results[0][2]


def test_an_ordinary_recipient_list_is_unaffected():
    """The guard must not reject the multi-recipient forms operators really use."""
    from core.notifications import parse_recipients
    assert parse_recipients("a@x.com, b@y.com; c@z.com") == \
        ["a@x.com", "b@y.com", "c@z.com"]

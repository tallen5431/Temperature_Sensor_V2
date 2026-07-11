"""Tests for notification channels and the dispatcher (core.notifications)."""
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

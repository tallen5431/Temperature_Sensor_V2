"""Notification channels (email + webhook) and the dispatcher.

Channel config is read from the hub config object at send time, so changes made
in Settings take effect without a restart.  Each channel fails independently —
a broken webhook never blocks the email, and vice-versa.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import List, Tuple

import requests

log = logging.getLogger("hub.notifications")


def parse_recipients(to_field) -> List[str]:
    if isinstance(to_field, (list, tuple)):
        return [str(x).strip() for x in to_field if str(x).strip()]
    return [p.strip() for p in str(to_field or "").replace(";", ",").split(",") if p.strip()]


def send_email(email_cfg: dict, subject: str, body: str) -> Tuple[bool, str]:
    host = (email_cfg.get("smtp_host") or "").strip()
    recipients = parse_recipients(email_cfg.get("to"))
    if not host or not recipients:
        return False, "email not configured (need smtp_host and to)"

    port = int(email_cfg.get("smtp_port") or 587)
    user = (email_cfg.get("username") or "").strip()
    password = email_cfg.get("password") or ""
    sender = (email_cfg.get("from") or user or "temperature-hub@localhost").strip()
    use_tls = email_cfg.get("use_tls", True)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    try:
        if port == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, timeout=15, context=ctx) as s:
                if user:
                    s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as s:
                if use_tls:
                    s.starttls(context=ssl.create_default_context())
                if user:
                    s.login(user, password)
                s.send_message(msg)
        return True, "sent"
    except Exception as e:  # noqa: BLE001 - report any SMTP failure to the caller
        log.warning("email send failed: %s", e)
        return False, str(e)


def send_webhook(webhook_cfg: dict, event: dict) -> Tuple[bool, str]:
    url = (webhook_cfg.get("url") or "").strip()
    if not url:
        return False, "webhook not configured (need url)"
    # A "text" field makes the payload work out-of-the-box with Slack-style
    # endpoints, while the structured fields suit Zapier/IFTTT/custom relays.
    payload = {"text": event.get("message", ""), **event}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.ok:
            return True, "sent"
        return False, f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        # The webhook URL can carry a bearer token in its path/query and is
        # treated as a secret elsewhere; scrub it from the error before logging
        # or returning it (requests embeds the full URL in its exception text).
        msg = str(e).replace(url, "<webhook-url>")
        log.warning("webhook send failed: %s", msg)
        return False, msg


class Notifier:
    """Dispatches an event to all enabled channels. Returns per-channel results."""

    def __init__(self, cfg):
        self.cfg = cfg

    def _conf(self) -> dict:
        return self.cfg.get("notifications", {}) or {}

    def enabled(self) -> bool:
        return bool(self._conf().get("enabled"))

    def dispatch(self, event: dict) -> List[Tuple[str, bool, str]]:
        conf = self._conf()
        results: List[Tuple[str, bool, str]] = []

        email = conf.get("email", {}) or {}
        if email.get("enabled"):
            ok, info = send_email(email, event.get("subject", "Temperature alert"),
                                  event.get("message", ""))
            results.append(("email", ok, info))

        webhook = conf.get("webhook", {}) or {}
        if webhook.get("enabled"):
            ok, info = send_webhook(webhook, event)
            results.append(("webhook", ok, info))

        for channel, ok, info in results:
            log.info("notification via %s: %s (%s)", channel, "ok" if ok else "FAILED", info)
        return results

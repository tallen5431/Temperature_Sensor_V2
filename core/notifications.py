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
from urllib.parse import urlsplit

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
    sender = (email_cfg.get("from") or user or "setpoint@localhost").strip()
    use_tls = email_cfg.get("use_tls", True)

    try:
        # Building the message is INSIDE the try, not before it. Python's email
        # package refuses a header containing a line break — correctly, that is
        # header injection — by raising ValueError, and with the construction
        # outside, that escaped a function whose whole contract is to return
        # (ok, reason) and never raise. Notifier.dispatch does not catch, so one
        # malformed recipient in config.json turned the Settings "Send test"
        # button into an unhandled callback error, and turned every real alert
        # into a bare "notification dispatch error" in the log with nothing
        # naming the field at fault.
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg.set_content(body)
    except ValueError as e:
        log.warning("email not sent — bad header value: %s", e)
        return False, ("A recipient, sender or subject contains a line break, "
                       "which an email header cannot hold. Check the To/From "
                       "addresses in Settings.")

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


# Alert kinds a person should be interrupted for. Recoveries, tests and summaries
# go out at normal priority so a phone does not ring for good news.
_URGENT_KINDS = frozenset({"high", "low", "offline", "rate", "missed"})


def _webhook_request(url: str, event: dict):
    """``(post_url, requests.post kwargs)`` shaped for the service at ``url``.

    One generic body — Slack's ``text`` plus the structured fields — suits
    Slack, Teams, Google Chat, Zapier, IFTTT and custom relays. Three services
    the Settings page names as recognised do NOT accept it, and fail in ways an
    operator would not see until the night it mattered:

    - **ntfy** treats a POST body to ``/<topic>`` as the literal message, so the
      phone showed a wall of JSON. Its documented JSON form goes to the server
      root with the topic inside the body, which also carries a title and a
      priority the phone can act on.
    - **Pushover** requires ``token``, ``user`` and ``message`` and rejects
      anything else with a 400. The URL the operator pastes carries the first
      two (``?token=…&user=…``).
    - **Discord** requires ``content`` and rejects ``text`` as an empty message.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    subject = event.get("subject", "") or ""
    message = event.get("message", "") or ""
    urgent = event.get("kind") in _URGENT_KINDS

    if "ntfy" in host:
        segments = [s for s in parts.path.split("/") if s]
        if segments:
            root = parts._replace(path="/" + "/".join(segments[:-1])).geturl()
            body = {"topic": segments[-1], "title": subject, "message": message,
                    "priority": 4 if urgent else 3,
                    "tags": ["warning"] if urgent else ["white_check_mark"]}
            return root, {"json": body}

    if host == "api.pushover.net":
        from urllib.parse import parse_qs
        q = parse_qs(parts.query)
        form = {"token": (q.get("token") or [""])[0], "user": (q.get("user") or [""])[0],
                "title": subject[:250], "message": message[:1024] or subject,
                "priority": 1 if urgent else 0}
        return parts._replace(query="").geturl(), {"data": form}

    if host in ("discord.com", "discordapp.com") and "/api/webhooks/" in parts.path:
        content = f"**{subject}**\n{message}" if subject else message
        return url, {"json": {"content": content[:2000]}}

    # A "text" field makes the payload work out-of-the-box with Slack-style
    # endpoints, while the structured fields suit Zapier/IFTTT/custom relays.
    return url, {"json": {"text": message, **event}}


def send_webhook(webhook_cfg: dict, event: dict) -> Tuple[bool, str]:
    url = (webhook_cfg.get("url") or "").strip()
    if not url:
        return False, "webhook not configured (need url)"
    post_url, kwargs = _webhook_request(url, event)
    form = kwargs.get("data")
    if form is not None and not (form["token"] and form["user"]):
        return False, ("Pushover needs ?token=<app token>&user=<user key> "
                       "on the end of the webhook URL")
    try:
        r = requests.post(post_url, timeout=10, **kwargs)
        if r.ok:
            return True, "sent"
        return False, f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        # The webhook URL can carry a bearer token in its path/query and is a
        # secret. requests/urllib3 render the host and the token-bearing
        # path+query SEPARATELY in their exception text (e.g. "...with url:
        # /path?token=..."), so a whole-URL str(e).replace(url, ...) never
        # matches and would leak the token to the log AND the Settings UI. Build
        # the message from the exception type and host only — never echo str(e).
        host = urlsplit(url).hostname or "the webhook host"
        msg = f"{type(e).__name__} contacting {host}"
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

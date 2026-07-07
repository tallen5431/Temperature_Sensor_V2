# core/notifications.py
"""Out-of-range notifications for unattended monitoring.

Alerts are evaluated *server-side on ingest* (not only in a browser callback),
so a fridge/freezer excursion overnight is surfaced even when no dashboard tab
is open — the core reason someone buys an unattended temperature monitor.

Supports SMTP email and generic webhooks (Slack/Discord/IFTTT/etc). All sends
are best-effort and can never break the ingest path.
"""
from __future__ import annotations

import json
import smtplib
import threading
import time
import urllib.request
from email.message import EmailMessage

from core.applog import get_logger

log = get_logger("notify")


class NotificationManager:
    def __init__(self):
        self._lock = threading.Lock()
        # probe_id -> {"state": "ok"|"high"|"low", "last_notified": epoch}
        self._state: dict[str, dict] = {}

    # -- evaluation -----------------------------------------------------------
    def evaluate(self, cfg, probe_id: str, temp_c: float, friendly_name: str | None = None,
                 humidity: float | None = None, vpd: float | None = None) -> None:
        """Check a fresh reading against thresholds and fire on transitions.

        Evaluates temperature and, when present, humidity and VPD — each against
        its own threshold pair and tracked independently, so a grower gets VPD
        alerts without a subscription.
        """
        try:
            notif = cfg.get("notifications", {}) or {}
            if not notif.get("enabled"):
                return
            thresholds = cfg.get("alert_thresholds", {}) or {}
            tcfg = thresholds.get(probe_id) or thresholds.get("default") or {}
            name = friendly_name or probe_id or "probe"
            debounce = int(notif.get("debounce_sec", 900) or 0)

            checks = [("temperature", temp_c, tcfg.get("min"), tcfg.get("max"), "°C")]
            if humidity is not None:
                checks.append(("humidity", humidity, tcfg.get("humidity_min"), tcfg.get("humidity_max"), "%"))
            if vpd is not None:
                checks.append(("vpd", vpd, tcfg.get("vpd_min"), tcfg.get("vpd_max"), "kPa"))

            for metric, value, lo, hi, unit in checks:
                if lo is None and hi is None:
                    continue
                self._eval_metric(notif, probe_id, name, metric, value, lo, hi, unit, debounce)
        except Exception as e:
            log.warning("notification evaluation failed for %s: %s", probe_id, e)

    def _eval_metric(self, notif, probe_id, name, metric, value, lo, hi, unit, debounce):
        new_state = "ok"
        if hi is not None and value > float(hi):
            new_state = "high"
        elif lo is not None and value < float(lo):
            new_state = "low"

        skey = f"{probe_id}:{metric}"
        with self._lock:
            prev = self._state.get(skey, {"state": "ok", "last_notified": 0.0})
            now = time.time()
            should_send = False
            subject = body = ""

            if new_state != "ok" and prev["state"] != new_state:
                if now - prev.get("last_notified", 0.0) >= debounce:
                    should_send = True
                    limit = hi if new_state == "high" else lo
                    arrow = "above" if new_state == "high" else "below"
                    subject = f"[{name}] {metric} {arrow} threshold"
                    body = (f"{name} {metric} is {value:.1f} {unit}, {arrow} the "
                            f"{new_state} threshold of {float(limit):.1f} {unit}.")
            elif new_state == "ok" and prev["state"] != "ok":
                should_send = True
                subject = f"[{name}] {metric} back to normal"
                body = f"{name} {metric} has returned to normal range ({value:.1f} {unit})."

            self._state[skey] = {
                "state": new_state,
                "last_notified": now if should_send else prev.get("last_notified", 0.0),
            }

        if should_send:
            self._dispatch(notif, subject, body)

    # -- delivery -------------------------------------------------------------
    def _dispatch(self, notif: dict, subject: str, body: str) -> None:
        log.info("ALERT: %s — %s", subject, body)
        if notif.get("recipients") and notif.get("smtp_host"):
            self._send_email(notif, subject, body)
        if notif.get("webhook_url"):
            self._send_webhook(notif["webhook_url"], subject, body)

    def _send_email(self, notif: dict, subject: str, body: str) -> None:
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = notif.get("smtp_from") or notif.get("smtp_user") or "thermahub@localhost"
            msg["To"] = ", ".join(notif.get("recipients", []))
            msg.set_content(body)

            host = notif["smtp_host"]
            port = int(notif.get("smtp_port", 587) or 587)
            with smtplib.SMTP(host, port, timeout=15) as s:
                if notif.get("smtp_tls", True):
                    s.starttls()
                if notif.get("smtp_user"):
                    s.login(notif["smtp_user"], notif.get("smtp_password", ""))
                s.send_message(msg)
            log.info("Alert email sent to %s", msg["To"])
        except Exception as e:
            log.warning("Failed to send alert email: %s", e)

    def _send_webhook(self, url: str, subject: str, body: str) -> None:
        try:
            payload = json.dumps({"text": f"{subject}\n{body}"}).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=15).read()
            log.info("Alert webhook posted to %s", url)
        except Exception as e:
            log.warning("Failed to post alert webhook: %s", e)

    # -- test button ----------------------------------------------------------
    def send_test(self, cfg) -> tuple[bool, str]:
        notif = cfg.get("notifications", {}) or {}
        if not (notif.get("smtp_host") and notif.get("recipients")) and not notif.get("webhook_url"):
            return False, "No email (SMTP host + recipients) or webhook configured."
        try:
            self._dispatch(notif, "ThermaHub test alert", "This is a test notification from ThermaHub.")
            return True, "Test notification sent."
        except Exception as e:
            return False, f"Failed: {e}"


NOTIFIER = NotificationManager()

"""Settings page: notification channels and data management.

The form skeleton is static; a one-shot interval populates it from the live
config when the page opens.  Saving writes back through ``cfg.update`` so the
running alert monitor and notifier pick up changes without a restart.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import Input, Output, State, html, dcc, no_update

from core.notifications import Notifier
from core.alerts import format_event
from core.mqtt_publish import MQTT


def _section_title(text):
    return html.H6(text, className="fw-bold mt-3 mb-2")


NotificationSettings = dbc.Card(dbc.CardBody([
    html.H5("Alerts", className="card-title"),
    html.P("Get notified when a probe goes out of range or drops offline. "
           "The temperature limits that trigger alerts are set per probe on the "
           "Devices page.", className="text-muted small"),
    dcc.Link("Set each probe’s min/max limits on the Devices page →", href="/devices",
             className="small d-block mb-2"),

    dbc.Switch(id="notif-enabled", label="Enable alerts", value=False),
    html.Div(id="alert-config-note", className="mt-1"),

    # Everything below only takes effect while "Enable alerts" is on. When it's
    # off the whole block is dimmed and made non-interactive (see
    # _toggle_alert_config) so a user can't fill the form, see it fully lit, and
    # walk away believing alerts are configured when nothing will ever fire.
    html.Div(id="alert-config-body", children=[

    # --- When to alert -------------------------------------------------------
    _section_title("When to alert"),
    dbc.Row([
        dbc.Col([
            html.Small("Re-alert every (minutes)", className="text-muted d-block"),
            dbc.Input(id="notif-cooldown-min", type="number", min=1, step=1, value=30),
            html.Small("How often to remind you while a probe stays out of range.",
                       className="text-muted"),
        ], md=6),
        dbc.Col([
            dbc.Switch(id="notif-recovery", label="Notify when a probe returns to normal",
                       value=True, className="mt-4"),
        ], md=6),
    ], className="g-2 mt-1"),

    dbc.Row([
        dbc.Col([
            html.Small("Deadband (°C)", className="text-muted d-block"),
            dbc.Input(id="notif-hysteresis", type="number", min=0, step=0.1, value=0.5),
            html.Small("How far a probe must move back inside its limit before the alert "
                       "clears — stops a probe sitting on the line from flapping.",
                       className="text-muted"),
        ], md=6),
    ], className="g-2 mt-1"),

    dbc.Row([
        dbc.Col([
            dbc.Switch(id="notif-offline-enabled", label="Alert when a probe goes offline",
                       value=True),
        ], md=6),
        dbc.Col([
            html.Small("Offline after (minutes)", className="text-muted d-block"),
            dbc.Input(id="offline-after-min", type="number", min=1, step=1, value=5),
            html.Small("Flag a probe that stops reporting for this long.",
                       className="text-muted"),
        ], md=6),
    ], className="g-2 mt-1"),

    dbc.Row([
        dbc.Col([
            html.Small("Rate alert (°C rise)", className="text-muted d-block"),
            dbc.Input(id="notif-rate-alert", type="number", min=0, step=0.5, value=0),
            html.Small("0 = off — catches a failing freezer early.",
                       className="text-muted"),
        ], md=6),
        dbc.Col([
            html.Small("within (minutes)", className="text-muted d-block"),
            dbc.Input(id="notif-rate-window", type="number", min=1, step=1, value=10),
            html.Small("Alert when a probe rises this many degrees inside the window.",
                       className="text-muted"),
        ], md=6),
    ], className="g-2 mt-1"),

    # --- Where to send alerts ------------------------------------------------
    _section_title("Where to send alerts"),
    dbc.Switch(id="notif-email-enabled", label="Email", value=False),
    dbc.Collapse(dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col([html.Small("SMTP host", className="text-muted"),
                     dbc.Input(id="email-host", placeholder="smtp.gmail.com")], md=8),
            dbc.Col([html.Small("Port", className="text-muted"),
                     dbc.Input(id="email-port", type="number", value=587)], md=4),
        ], className="g-2"),
        dbc.Switch(id="email-tls", label="Use STARTTLS (encryption — leave on for most providers)",
                   value=True, className="mt-2"),
        dbc.Row([
            dbc.Col([html.Small("Username", className="text-muted"),
                     dbc.Input(id="email-user", placeholder="you@example.com")], md=6),
            dbc.Col([html.Small("Password", className="text-muted"),
                     dbc.Input(id="email-pass", type="password", placeholder="(unchanged)"),
                     html.Small("Leave blank to keep the saved password.",
                                className="text-muted")], md=6),
        ], className="g-2 mt-1"),
        dbc.Row([
            dbc.Col([html.Small("From address", className="text-muted"),
                     dbc.Input(id="email-from", placeholder="alerts@example.com")], md=6),
            dbc.Col([html.Small("To (comma-separated)", className="text-muted"),
                     dbc.Input(id="email-to", placeholder="me@example.com, ops@example.com")], md=6),
        ], className="g-2 mt-1"),
        dbc.Row([
            dbc.Col([
                dbc.Switch(id="daily-summary-enabled",
                           label="Send a daily summary email", value=False,
                           className="mt-2"),
                html.Small("One email a day with each probe's min/max/average.",
                           className="text-muted"),
            ], md=6),
            dbc.Col([
                html.Small("Send at (hour, 0–23)", className="text-muted d-block"),
                dbc.Input(id="daily-summary-hour", type="number", min=0, max=23,
                          step=1, value=8),
            ], md=6),
        ], className="g-2 mt-1"),
    ]), className="mt-2 mb-1"), id="email-collapse", is_open=False),

    dbc.Switch(id="notif-webhook-enabled", label="Webhook", value=False, className="mt-2"),
    dbc.Collapse(dbc.Card(dbc.CardBody([
        html.Small("Posts JSON (with a Slack-compatible \"text\" field) to this URL.",
                   className="text-muted d-block"),
        dbc.Input(id="webhook-url", placeholder="https://hooks.slack.com/services/...",
                  className="mt-1"),
    ]), className="mt-2 mb-1"), id="webhook-collapse", is_open=False),

    ]),  # end alert-config-body

    html.Div([
        dbc.Button("Save", id="notif-save", color="primary", className="mt-3 me-2"),
        dbc.Button("Send test", id="notif-test", color="secondary", outline=True, className="mt-3"),
        html.Small("Save first, then send a test to the channels above.",
                   className="text-muted d-block mt-1"),
    ]),
    html.Div(id="notif-status", className="mt-2"),

    # Fires once when the page opens to load current values from config.
    dcc.Interval(id="settings-loaded", interval=300, n_intervals=0, max_intervals=1),
]), className="mb-3")


DataManagement = dbc.Card(dbc.CardBody([
    html.H5("Data & storage", className="card-title"),
    dbc.Row([
        dbc.Col([
            html.Small("Keep readings for (days)", className="text-muted d-block"),
            dbc.InputGroup([
                dbc.Input(id="retention-days", type="number", min=0, step=1, value=0),
                dbc.InputGroupText("days"),
            ]),
            html.Small(id="retention-note", className="text-muted"),
        ], md=6),
        dbc.Col([
            html.Small("Backup", className="text-muted d-block"),
            dbc.Button("⬇ Download database backup", id="backup-btn", color="secondary",
                       outline=True, href="/download/backup.db", external_link=True),
            html.Small("Downloads the full readings database as a file.",
                       className="text-muted d-block mt-1"),
        ], md=6, className="d-flex flex-column justify-content-center"),
    ], className="g-3"),
    dbc.Button("Save", id="data-save", color="primary", className="mt-3"),
    html.Div(id="data-status", className="mt-2"),
]), className="mb-3")


IntegrationsCard = dbc.Card(dbc.CardBody([
    html.H5("Integrations", className="card-title"),
    html.P("Publish every reading to an MQTT broker with Home Assistant "
           "auto-discovery — each probe appears there as a sensor automatically.",
           className="text-muted small"),

    dbc.Switch(id="mqtt-enabled", label="Publish to MQTT (Home Assistant)", value=False),
    dbc.Collapse(dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col([html.Small("Broker host", className="text-muted"),
                     dbc.Input(id="mqtt-host", placeholder="homeassistant.local")], md=8),
            dbc.Col([html.Small("Port", className="text-muted"),
                     dbc.Input(id="mqtt-port", type="number", value=1883)], md=4),
        ], className="g-2"),
        dbc.Row([
            dbc.Col([html.Small("Username", className="text-muted"),
                     dbc.Input(id="mqtt-user", placeholder="(optional)")], md=6),
            dbc.Col([html.Small("Password", className="text-muted"),
                     dbc.Input(id="mqtt-pass", type="password", placeholder="(unchanged)"),
                     html.Small("Leave blank to keep the saved password.",
                                className="text-muted")], md=6),
        ], className="g-2 mt-1"),
        dbc.Row([
            dbc.Col([html.Small("Base topic", className="text-muted"),
                     dbc.Input(id="mqtt-base-topic", placeholder="setpoint")], md=6),
            dbc.Col([dbc.Switch(id="mqtt-discovery",
                                label="Home Assistant auto-discovery",
                                value=True, className="mt-4")], md=6),
        ], className="g-2 mt-1"),
    ]), className="mt-2 mb-1"), id="mqtt-collapse", is_open=False),

    dbc.Button("Save", id="mqtt-save", color="primary", className="mt-3"),
    html.Div(id="mqtt-status", className="mt-2"),
]), className="mb-3")


SettingsPanel = html.Div([NotificationSettings, IntegrationsCard, DataManagement])


def _ok(msg):
    return dbc.Alert(msg, color="success", dismissable=True, className="mb-0")


def _err(msg):
    return dbc.Alert(msg, color="danger", dismissable=True, className="mb-0")


def build_notifications_config(enabled, cooldown_min, recovery, email_enabled, host, port,
                               tls, user, sender, to, webhook_enabled, url, password,
                               offline_alerts=True, existing_password="",
                               daily_summary_enabled=False, daily_summary_hour=8):
    """Turn raw Settings form values into a notifications config dict.

    Pure and module-level so it can be unit-tested.  A blank password means
    "keep the stored one"; cooldown is taken in minutes and stored as seconds.
    """
    try:
        cooldown_sec = max(60, int(float(cooldown_min)) * 60)
    except (TypeError, ValueError):
        cooldown_sec = 1800
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 587
    try:
        summary_hour = min(23, max(0, int(float(daily_summary_hour))))
    except (TypeError, ValueError):
        summary_hour = 8
    return {
        "enabled": bool(enabled),
        "cooldown_sec": cooldown_sec,
        "notify_recovery": bool(recovery),
        "offline_alerts": bool(offline_alerts),
        "email": {
            "enabled": bool(email_enabled),
            "smtp_host": (host or "").strip(),
            "smtp_port": port,
            "use_tls": bool(tls),
            "username": (user or "").strip(),
            "password": password if password else existing_password,
            "from": (sender or "").strip(),
            "to": (to or "").strip(),
        },
        "webhook": {"enabled": bool(webhook_enabled), "url": (url or "").strip()},
        "daily_summary": {"enabled": bool(daily_summary_enabled), "hour": summary_hour},
    }


def build_mqtt_config(enabled, host, port, username, password, base_topic, discovery,
                      existing=None):
    """Turn raw Integrations form values into the ``mqtt`` config block.

    Pure and module-level so it can be unit-tested.  A blank password keeps the
    saved one, and keys the form does not expose (e.g. ``discovery_prefix``)
    are carried over from the existing block untouched.
    """
    out = dict(existing or {})
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 1883
    out.update({
        "enabled": bool(enabled),
        "host": (host or "").strip(),
        "port": port,
        "username": (username or "").strip(),
        "password": password if password else out.get("password", ""),
        "base_topic": (base_topic or "").strip() or "setpoint",
        "discovery_enabled": bool(discovery),
    })
    return out


def register_settings_callbacks(app, cfg):
    @app.callback(
        Output("notif-enabled", "value"),
        Output("notif-cooldown-min", "value"),
        Output("notif-recovery", "value"),
        Output("notif-email-enabled", "value"),
        Output("email-host", "value"),
        Output("email-port", "value"),
        Output("email-tls", "value"),
        Output("email-user", "value"),
        Output("email-from", "value"),
        Output("email-to", "value"),
        Output("notif-webhook-enabled", "value"),
        Output("webhook-url", "value"),
        Output("retention-days", "value"),
        Output("notif-offline-enabled", "value"),
        Output("offline-after-min", "value"),
        Output("notif-rate-alert", "value"),
        Output("notif-rate-window", "value"),
        Output("daily-summary-enabled", "value"),
        Output("daily-summary-hour", "value"),
        Input("settings-loaded", "n_intervals"),
    )
    def _load(_n):
        n = cfg.get("notifications", {}) or {}
        email = n.get("email", {}) or {}
        webhook = n.get("webhook", {}) or {}
        summary = n.get("daily_summary", {}) or {}
        try:
            rate_alert = max(0.0, float(cfg.get("rate_alert_c", 0.0) or 0.0))
        except (TypeError, ValueError):
            rate_alert = 0.0
        try:
            rate_window = max(1, int(cfg.get("rate_window_min", 10) or 10))
        except (TypeError, ValueError):
            rate_window = 10
        try:
            summary_hour = min(23, max(0, int(summary.get("hour", 8))))
        except (TypeError, ValueError):
            summary_hour = 8
        return (
            bool(n.get("enabled", False)),
            int(n.get("cooldown_sec", 1800) or 1800) // 60,
            bool(n.get("notify_recovery", True)),
            bool(email.get("enabled", False)),
            email.get("smtp_host", ""),
            int(email.get("smtp_port", 587) or 587),
            bool(email.get("use_tls", True)),
            email.get("username", ""),
            email.get("from", ""),
            email.get("to", ""),
            bool(webhook.get("enabled", False)),
            webhook.get("url", ""),
            int(cfg.get("retention_days", 0) or 0),
            bool(n.get("offline_alerts", True)),
            max(1, int(cfg.get("offline_after_sec", 300) or 300) // 60),
            rate_alert,
            rate_window,
            bool(summary.get("enabled", False)),
            summary_hour,
        )

    @app.callback(
        Output("notif-hysteresis", "value"),
        Input("settings-loaded", "n_intervals"),
    )
    def _load_hysteresis(_n):
        try:
            return float(cfg.get("alert_hysteresis_c", 0.5))
        except (TypeError, ValueError):
            return 0.5

    # Progressive disclosure: only show a channel's fields once it's enabled.
    @app.callback(
        Output("email-collapse", "is_open"),
        Input("notif-email-enabled", "value"),
    )
    def _toggle_email(enabled):
        return bool(enabled)

    @app.callback(
        Output("webhook-collapse", "is_open"),
        Input("notif-webhook-enabled", "value"),
    )
    def _toggle_webhook(enabled):
        return bool(enabled)

    # --- Integrations (MQTT) --------------------------------------------------
    @app.callback(
        Output("mqtt-enabled", "value"),
        Output("mqtt-host", "value"),
        Output("mqtt-port", "value"),
        Output("mqtt-user", "value"),
        Output("mqtt-base-topic", "value"),
        Output("mqtt-discovery", "value"),
        Input("settings-loaded", "n_intervals"),
    )
    def _load_mqtt(_n):
        m = cfg.get("mqtt", {}) or {}
        return (
            bool(m.get("enabled", False)),
            m.get("host", ""),
            int(m.get("port", 1883) or 1883),
            m.get("username", ""),
            m.get("base_topic", "setpoint"),
            bool(m.get("discovery_enabled", True)),
        )

    @app.callback(
        Output("mqtt-collapse", "is_open"),
        Input("mqtt-enabled", "value"),
    )
    def _toggle_mqtt(enabled):
        return bool(enabled)

    @app.callback(
        Output("mqtt-status", "children"),
        Input("mqtt-save", "n_clicks"),
        State("mqtt-enabled", "value"),
        State("mqtt-host", "value"),
        State("mqtt-port", "value"),
        State("mqtt-user", "value"),
        State("mqtt-pass", "value"),
        State("mqtt-base-topic", "value"),
        State("mqtt-discovery", "value"),
        prevent_initial_call=True,
    )
    def _save_mqtt(_n, enabled, host, port, user, password, base_topic, discovery):
        try:
            existing = cfg.get("mqtt", {}) or {}
            cfg.update({"mqtt": build_mqtt_config(
                enabled, host, port, user, password, base_topic, discovery,
                existing=existing)})
        except Exception as e:  # noqa: BLE001
            return _err(f"Could not save: {e}")
        # Restart the publisher so the new settings take effect without a hub
        # restart, then report the LIVE connection state — a saved-but-
        # unreachable broker must not look like a working integration.
        try:
            MQTT.stop()
            MQTT.start(cfg)
        except Exception as e:  # noqa: BLE001
            return _err(f"Saved, but restarting the MQTT publisher failed: {e}")
        if not enabled:
            return _ok("MQTT settings saved — publishing is off.")
        if MQTT.is_ready():
            return _ok("MQTT settings saved — connected to the broker and publishing.")
        return dbc.Alert(
            "Saved, but MQTT is not publishing yet — check the broker host, port "
            "and credentials, and that paho-mqtt is installed (details in the hub log).",
            color="warning", dismissable=True, className="mb-0")

    # Dim + disable the whole alert-config block while the master switch is off,
    # with an inline note, so the form never looks live when it isn't.
    @app.callback(
        Output("alert-config-body", "style"),
        Output("alert-config-note", "children"),
        Input("notif-enabled", "value"),
    )
    def _toggle_alert_config(enabled):
        if enabled:
            return {}, None
        return (
            {"opacity": 0.5, "pointerEvents": "none"},
            html.Small(
                "Alerts are off — turn on “Enable alerts” above and Save to activate "
                "the settings below.", className="text-warning"),
        )

    # Retention is destructive above 0 — say so plainly as the user types.
    @app.callback(
        Output("retention-note", "children"),
        Output("retention-note", "className"),
        Input("retention-days", "value"),
    )
    def _retention_note(days):
        try:
            d = int(days or 0)
        except (TypeError, ValueError):
            d = 0
        if d <= 0:
            return "0 = keep everything, forever (the default for a data logger).", "text-muted"
        return (f"⚠ Readings older than {d} day{'s' if d != 1 else ''} are permanently deleted.",
                "text-warning")

    @app.callback(
        Output("notif-status", "children"),
        Input("notif-save", "n_clicks"),
        State("notif-enabled", "value"),
        State("notif-cooldown-min", "value"),
        State("notif-recovery", "value"),
        State("notif-offline-enabled", "value"),
        State("offline-after-min", "value"),
        State("notif-email-enabled", "value"),
        State("email-host", "value"),
        State("email-port", "value"),
        State("email-tls", "value"),
        State("email-user", "value"),
        State("email-from", "value"),
        State("email-to", "value"),
        State("notif-webhook-enabled", "value"),
        State("webhook-url", "value"),
        State("email-pass", "value"),
        State("notif-hysteresis", "value"),
        State("notif-rate-alert", "value"),
        State("notif-rate-window", "value"),
        State("daily-summary-enabled", "value"),
        State("daily-summary-hour", "value"),
        prevent_initial_call=True,
    )
    def _save(_n, enabled, cooldown_min, recovery, offline_enabled, offline_after_min,
              email_enabled, host, port, tls, user, sender, to, webhook_enabled, url, password,
              hysteresis, rate_alert, rate_window, summary_enabled, summary_hour):
        try:
            existing = ((cfg.get("notifications", {}) or {}).get("email", {}) or {}).get("password", "")
            notif = build_notifications_config(
                enabled, cooldown_min, recovery, email_enabled, host, port, tls, user,
                sender, to, webhook_enabled, url, password,
                offline_alerts=offline_enabled, existing_password=existing,
                daily_summary_enabled=summary_enabled, daily_summary_hour=summary_hour)
            updates = {"notifications": notif}
            try:
                updates["offline_after_sec"] = max(60, int(float(offline_after_min)) * 60)
            except (TypeError, ValueError):
                pass
            try:
                updates["alert_hysteresis_c"] = max(0.0, float(hysteresis))
            except (TypeError, ValueError):
                pass
            try:
                updates["rate_alert_c"] = max(0.0, float(rate_alert))
            except (TypeError, ValueError):
                pass
            try:
                updates["rate_window_min"] = max(1, int(float(rate_window)))
            except (TypeError, ValueError):
                pass
            cfg.update(updates)
            return _ok("✅ Notification settings saved.")
        except Exception as e:  # noqa: BLE001
            return _err(f"Could not save: {e}")

    @app.callback(
        Output("notif-status", "children", allow_duplicate=True),
        Input("notif-test", "n_clicks"),
        prevent_initial_call=True,
    )
    def _test(_n):
        conf = cfg.get("notifications", {}) or {}
        if not (conf.get("email", {}).get("enabled") or conf.get("webhook", {}).get("enabled")):
            return _err("Enable and save at least one channel (email or webhook) first.")
        subject, message = format_event(
            {"probe_id": "test", "kind": "test", "temperature_c": 21.0, "limit": None},
            {"test": "Test probe"},
        )
        results = Notifier(cfg).dispatch({"subject": "[Test] " + subject, "message": message,
                                          "probe_id": "test", "kind": "test"})
        if not results:
            return _err("No channels were attempted.")
        lines = [html.Div(f"{ch}: {'✅ sent' if ok else '❌ ' + info}") for ch, ok, info in results]
        all_ok = all(ok for _, ok, _ in results)
        # The test dispatches to the channels regardless of the master switch, so
        # a channel can report "sent" while live alerts are still OFF. Say so
        # plainly — this is the usual reason a real breach doesn't notify.
        if not conf.get("enabled"):
            lines.append(html.Div(
                "⚠ Live alerts are OFF — turn on “Enable alerts” at the top and click "
                "Save, or real breaches won’t notify you.", className="fw-bold mt-1"))
            return dbc.Alert([html.Strong("Test result: "), html.Br(), *lines],
                             color="warning", dismissable=True, className="mb-0")
        return (_ok if all_ok else _err)(
            html.Span([html.Strong("Test result: "), html.Br(), *lines]))

    @app.callback(
        Output("data-status", "children"),
        Input("data-save", "n_clicks"),
        State("retention-days", "value"),
        prevent_initial_call=True,
    )
    def _save_data(_n, days):
        try:
            cfg.update({"retention_days": max(0, int(days or 0))})
            return _ok("✅ Data settings saved.")
        except Exception as e:  # noqa: BLE001
            return _err(f"Could not save: {e}")

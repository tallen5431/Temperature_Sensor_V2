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


SettingsPanel = html.Div([NotificationSettings, DataManagement])


def _ok(msg):
    return dbc.Alert(msg, color="success", dismissable=True, className="mb-0")


def _err(msg):
    return dbc.Alert(msg, color="danger", dismissable=True, className="mb-0")


def build_notifications_config(enabled, cooldown_min, recovery, email_enabled, host, port,
                               tls, user, sender, to, webhook_enabled, url, password,
                               offline_alerts=True, existing_password=""):
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
    }


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
        Input("settings-loaded", "n_intervals"),
    )
    def _load(_n):
        n = cfg.get("notifications", {}) or {}
        email = n.get("email", {}) or {}
        webhook = n.get("webhook", {}) or {}
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
        prevent_initial_call=True,
    )
    def _save(_n, enabled, cooldown_min, recovery, offline_enabled, offline_after_min,
              email_enabled, host, port, tls, user, sender, to, webhook_enabled, url, password,
              hysteresis):
        try:
            existing = ((cfg.get("notifications", {}) or {}).get("email", {}) or {}).get("password", "")
            notif = build_notifications_config(
                enabled, cooldown_min, recovery, email_enabled, host, port, tls, user,
                sender, to, webhook_enabled, url, password,
                offline_alerts=offline_enabled, existing_password=existing)
            updates = {"notifications": notif}
            try:
                updates["offline_after_sec"] = max(60, int(float(offline_after_min)) * 60)
            except (TypeError, ValueError):
                pass
            try:
                updates["alert_hysteresis_c"] = max(0.0, float(hysteresis))
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

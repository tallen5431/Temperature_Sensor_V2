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
    html.H5("Notifications", className="card-title"),
    html.P("Get alerted by email or webhook when a probe crosses its min/max "
           "threshold. Thresholds are set per probe on the Devices page.",
           className="text-muted small"),

    dbc.Switch(id="notif-enabled", label="Enable notifications", value=False),
    dbc.Row([
        dbc.Col([
            html.Small("Reminder interval (minutes)", className="text-muted d-block"),
            dbc.Input(id="notif-cooldown-min", type="number", min=1, step=1, value=30),
            html.Small("How often to re-notify while a probe stays out of range.",
                       className="text-muted"),
        ], md=6),
        dbc.Col([
            dbc.Switch(id="notif-recovery", label="Notify on return to normal", value=True,
                       className="mt-4"),
        ], md=6),
    ], className="g-2 mt-1"),

    _section_title("Email (SMTP)"),
    dbc.Switch(id="notif-email-enabled", label="Enable email", value=False),
    dbc.Row([
        dbc.Col([html.Small("SMTP host", className="text-muted"),
                 dbc.Input(id="email-host", placeholder="smtp.gmail.com")], md=8),
        dbc.Col([html.Small("Port", className="text-muted"),
                 dbc.Input(id="email-port", type="number", value=587)], md=4),
    ], className="g-2"),
    dbc.Switch(id="email-tls", label="Use STARTTLS", value=True, className="mt-2"),
    dbc.Row([
        dbc.Col([html.Small("Username", className="text-muted"),
                 dbc.Input(id="email-user", placeholder="you@example.com")], md=6),
        dbc.Col([html.Small("Password", className="text-muted"),
                 dbc.Input(id="email-pass", type="password", placeholder="(unchanged)")], md=6),
    ], className="g-2 mt-1"),
    dbc.Row([
        dbc.Col([html.Small("From address", className="text-muted"),
                 dbc.Input(id="email-from", placeholder="alerts@example.com")], md=6),
        dbc.Col([html.Small("To (comma-separated)", className="text-muted"),
                 dbc.Input(id="email-to", placeholder="me@example.com, ops@example.com")], md=6),
    ], className="g-2 mt-1"),

    _section_title("Webhook"),
    dbc.Switch(id="notif-webhook-enabled", label="Enable webhook", value=False),
    html.Small("Posts JSON (with a Slack-compatible \"text\" field) to this URL.",
               className="text-muted d-block"),
    dbc.Input(id="webhook-url", placeholder="https://hooks.slack.com/services/...", className="mt-1"),

    html.Div([
        dbc.Button("Save", id="notif-save", color="primary", className="mt-3 me-2"),
        dbc.Button("Send test", id="notif-test", color="secondary", outline=True, className="mt-3"),
    ]),
    html.Div(id="notif-status", className="mt-2"),

    # Fires once when the page opens to load current values from config.
    dcc.Interval(id="settings-loaded", interval=300, n_intervals=0, max_intervals=1),
]), className="mb-3")


DataManagement = dbc.Card(dbc.CardBody([
    html.H5("Data Management", className="card-title"),
    dbc.Row([
        dbc.Col([
            html.Small("Retention (days, 0 = keep forever)", className="text-muted d-block"),
            dbc.Input(id="retention-days", type="number", min=0, step=1, value=0),
            html.Small("Readings older than this are automatically deleted.",
                       className="text-muted"),
        ], md=6),
        dbc.Col([
            html.Small("Backup", className="text-muted d-block"),
            dbc.Button("⬇ Download database backup", id="backup-btn", color="secondary",
                       outline=True, href="/download/backup.db", external_link=True),
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
                               existing_password=""):
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
        )

    def _collect_notifications(*form_values):
        existing = ((cfg.get("notifications", {}) or {}).get("email", {}) or {}).get("password", "")
        return build_notifications_config(*form_values, existing_password=existing)

    @app.callback(
        Output("notif-status", "children"),
        Input("notif-save", "n_clicks"),
        State("notif-enabled", "value"),
        State("notif-cooldown-min", "value"),
        State("notif-recovery", "value"),
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
        prevent_initial_call=True,
    )
    def _save(_n, *args):
        try:
            cfg.update({"notifications": _collect_notifications(*args)})
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
        lines = [f"{ch}: {'✅ sent' if ok else '❌ ' + info}" for ch, ok, info in results]
        all_ok = all(ok for _, ok, _ in results)
        return (_ok if all_ok else _err)(html.Span([html.Strong("Test result: "),
                                                     html.Br(), *[html.Div(l) for l in lines]]))

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

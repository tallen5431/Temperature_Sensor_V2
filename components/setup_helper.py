# components/setup_helper.py
from __future__ import annotations
from dash import html, dcc, Input, Output, State, no_update
import dash_bootstrap_components as dbc

from wifi_scan import SSIDWatcher
from core.notifications import NOTIFIER

# Background watcher for the probe's setup SoftAP (SSID begins with the brand).
_watcher = SSIDWatcher("ThermaProbe", interval_sec=5.0)
_watcher.start()


def _setup_helper_card():
    return dbc.Card(dbc.CardBody([
        html.Div(className="d-flex justify-content-between align-items-center", children=[
            html.H5("Connect a probe (setup helper)", className="mb-0"),
            html.Small(id="ap-seen-label", className="text-muted"),
        ]),
        html.P(
            "A new probe with no saved Wi-Fi starts its own temporary network so you can tell "
            "it which home Wi-Fi to join. This page watches for that network and guides you.",
            className="mt-2",
        ),
        html.Ol([
            html.Li("Power the probe (USB). Give it ~15 seconds."),
            html.Li("On your phone or PC, open Wi-Fi settings and join the network beginning with “ThermaProbe-”."),
            html.Li("A setup page opens (or browse to http://192.168.4.1). Pick your home Wi-Fi and enter its password."),
            html.Li("Rejoin your home Wi-Fi. The probe appears on the Dashboard and Devices pages automatically."),
        ], className="small"),
        dbc.Alert(id="ap-status", color="secondary", className="mt-2"),
        html.Div([
            html.A("Open probe setup page (http://192.168.4.1)", id="open-ap-link",
                   href="http://192.168.4.1", target="_blank",
                   className="btn btn-outline-primary btn-sm",
                   n_clicks=0, style={"pointerEvents": "none", "opacity": 0.5}),
        ], className="mt-2"),
        dcc.Interval(id="ap-poll", interval=4000, n_intervals=0),
    ]), className="mb-3")


def _preferences_card(cfg):
    settings = cfg.get("settings", {}) or {}
    return dbc.Card(dbc.CardBody([
        html.H5("Preferences"),
        dbc.Row([
            dbc.Col([
                dbc.Label("Default temperature unit"),
                dbc.RadioItems(
                    id="set-default-unit",
                    options=[{"label": "Celsius (°C)", "value": "celsius"},
                             {"label": "Fahrenheit (°F)", "value": "fahrenheit"}],
                    value=settings.get("default_unit", "celsius"),
                ),
            ], md=6),
            dbc.Col([
                dbc.Label("Timezone (blank = this computer's time)"),
                dbc.Input(id="set-timezone", type="text", value=settings.get("timezone", ""),
                          placeholder="e.g. America/New_York"),
            ], md=6),
        ], className="gy-2"),
        html.Hr(),
        html.H6("Probe provisioning"),
        dbc.Row([
            dbc.Col([
                dbc.Checkbox(id="set-auto-provision", label="Automatically set up new probes",
                             value=bool(cfg.get("auto_provision", True))),
            ], md=6),
            dbc.Col([
                dbc.Label("Reading interval (seconds)"),
                dbc.Input(id="set-interval", type="number", min=1, step=1,
                          value=int(cfg.get("interval_sec", 5))),
            ], md=6),
        ], className="gy-2"),
    ]), className="mb-3")


def _notifications_card(cfg):
    n = cfg.get("notifications", {}) or {}
    return dbc.Card(dbc.CardBody([
        html.H5("Alert notifications"),
        html.P("Get emailed or pinged when a probe goes out of range — even with no browser open. "
               "Thresholds are set per probe on the Devices page (default applies otherwise).",
               className="small text-muted"),
        dbc.Checkbox(id="set-notif-enabled", label="Enable notifications",
                     value=bool(n.get("enabled", False)), className="mb-2"),
        dbc.Row([
            dbc.Col([
                dbc.Label("Email recipients (comma-separated)"),
                dbc.Input(id="set-notif-recipients", type="text",
                          value=", ".join(n.get("recipients", []) or []),
                          placeholder="you@example.com, ops@example.com"),
            ], md=6),
            dbc.Col([
                dbc.Label("Webhook URL (Slack/Discord/etc — optional)"),
                # A webhook URL is a bearer secret — never seed it into the page
                # (the dashboard is open by default). Blank; kept on save when empty.
                dbc.Input(id="set-notif-webhook", type="text", value="",
                          placeholder="(unchanged if left blank)"),
            ], md=6),
        ], className="gy-2"),
        html.Hr(),
        html.H6("Email server (SMTP)", className="text-muted"),
        dbc.Row([
            dbc.Col([dbc.Label("SMTP host"),
                     dbc.Input(id="set-smtp-host", type="text", value=n.get("smtp_host", ""),
                               placeholder="smtp.gmail.com")], md=4),
            dbc.Col([dbc.Label("Port"),
                     dbc.Input(id="set-smtp-port", type="number", value=int(n.get("smtp_port", 587)))], md=2),
            dbc.Col([dbc.Label("From address"),
                     dbc.Input(id="set-smtp-from", type="text", value=n.get("smtp_from", ""))], md=6),
        ], className="gy-2"),
        dbc.Row([
            dbc.Col([dbc.Label("SMTP username"),
                     dbc.Input(id="set-smtp-user", type="text", value=n.get("smtp_user", ""))], md=6),
            dbc.Col([dbc.Label("SMTP password"),
                     # Never render the stored secret into the page (it would be
                     # sent to every browser that can open /settings). The save
                     # handler keeps the existing password when this is left blank.
                     dbc.Input(id="set-smtp-pass", type="password", value="",
                               placeholder="(unchanged if left blank)")], md=6),
        ], className="gy-2"),
        dbc.Row([
            dbc.Col([dbc.Checkbox(id="set-smtp-tls", label="Use STARTTLS",
                                  value=bool(n.get("smtp_tls", True)))], md=6),
            dbc.Col([dbc.Label("Re-alert cooldown (seconds)"),
                     dbc.Input(id="set-notif-debounce", type="number", min=0, step=30,
                               value=int(n.get("debounce_sec", 900)))], md=6),
        ], className="gy-2 mt-1"),
        html.Div([
            dbc.Button("Send test alert", id="notif-test", color="secondary", size="sm", className="me-2"),
            html.Span(id="notif-test-status", className="text-info"),
        ], className="mt-3"),
    ]), className="mb-3")


def build_settings_page(cfg):
    return html.Div([
        html.H4("Settings"),
        _setup_helper_card(),
        _preferences_card(cfg),
        _notifications_card(cfg),
        html.Div([
            dbc.Button("Save settings", id="settings-save", color="primary"),
            html.Span(id="settings-save-status", className="ms-3 text-success fw-bold"),
        ], className="mb-4"),
    ])


def register_settings_callbacks(app, cfg):
    @app.callback(
        Output("ap-status", "children"),
        Output("ap-status", "color"),
        Output("ap-seen-label", "children"),
        Output("open-ap-link", "style"),
        Input("ap-poll", "n_intervals"),
        prevent_initial_call=False,
    )
    def _update_ap(_n):
        seen = _watcher.seen()
        label = "Setup network: visible" if seen else "Setup network: not detected"
        if seen:
            msg = ("✅ Found a probe’s setup network nearby. Join the “ThermaProbe-…” Wi-Fi on your "
                   "device, then open the setup page below to choose your home Wi-Fi.")
            color, style = "success", {}
        else:
            msg = ("Waiting for a probe’s setup network… Power a probe that has no saved Wi-Fi so it "
                   "starts its setup network. This checks every few seconds.")
            color, style = "secondary", {"pointerEvents": "none", "opacity": 0.5}
        return msg, color, label, style

    @app.callback(
        Output("settings-save-status", "children"),
        Input("settings-save", "n_clicks"),
        State("set-default-unit", "value"),
        State("set-timezone", "value"),
        State("set-auto-provision", "value"),
        State("set-interval", "value"),
        State("set-notif-enabled", "value"),
        State("set-notif-recipients", "value"),
        State("set-notif-webhook", "value"),
        State("set-smtp-host", "value"),
        State("set-smtp-port", "value"),
        State("set-smtp-from", "value"),
        State("set-smtp-user", "value"),
        State("set-smtp-pass", "value"),
        State("set-smtp-tls", "value"),
        State("set-notif-debounce", "value"),
        prevent_initial_call=True,
    )
    def _save_settings(_n, unit, tz, auto_prov, interval, notif_on, recipients, webhook,
                       smtp_host, smtp_port, smtp_from, smtp_user, smtp_pass, smtp_tls, debounce):
        try:
            recips = [r.strip() for r in (recipients or "").split(",") if r.strip()]
            notif = {
                "enabled": bool(notif_on),
                "recipients": recips,
                "smtp_host": (smtp_host or "").strip(),
                "smtp_port": int(smtp_port or 587),
                "smtp_from": (smtp_from or "").strip(),
                "smtp_user": (smtp_user or "").strip(),
                "smtp_tls": bool(smtp_tls),
                "debounce_sec": int(debounce or 0),
            }
            # Secret-bearing fields are rendered blank; only overwrite them when
            # the user actually typed a replacement (else keep the stored value).
            if smtp_pass:
                notif["smtp_password"] = smtp_pass
            if webhook and webhook.strip():
                notif["webhook_url"] = webhook.strip()
            cfg.update({
                "settings": {"default_unit": unit or "celsius", "timezone": (tz or "").strip()},
                "auto_provision": bool(auto_prov),
                "interval_sec": max(1, int(interval or 5)),
                "notifications": notif,
            })
            return "✅ Saved"
        except Exception as e:
            return f"❌ {e}"

    @app.callback(
        Output("notif-test-status", "children"),
        Input("notif-test", "n_clicks"),
        prevent_initial_call=True,
    )
    def _send_test(_n):
        ok, msg = NOTIFIER.send_test(cfg)
        return ("✅ " if ok else "❌ ") + msg

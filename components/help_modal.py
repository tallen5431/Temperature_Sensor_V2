import dash_bootstrap_components as dbc
from dash import Input, Output, State, html

from core.version import DOCS_URL, PRODUCT_NAME


def _section(title, children):
    return html.Div([html.H6(title, className="fw-bold text-info mt-3 mb-2"), *children])


def HelpModal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Help & Quick Start")),
        dbc.ModalBody([
            html.P([f"Welcome to {PRODUCT_NAME} — your dashboard for wireless temperature probes. ",
                    "Everything below works from this window; no command line needed."]),

            _section("1 · Get a probe online", [
                html.Ol([
                    html.Li("Power the probe (USB or battery) near the area you want to monitor."),
                    html.Li(["First time? On your phone join the ", html.B("TempSensor-XXXXXX"),
                             " Wi-Fi it broadcasts, then pick your home/office network and save."]),
                    html.Li("Within ~20 seconds it appears on the Devices page and readings start flowing."),
                ]),
                html.Small("No probe yet? You can still try the dashboard — see the demo tip on the Dashboard page.",
                           className="text-muted"),
            ]),

            _section("2 · Name & calibrate", [
                html.P([html.B("Devices → ✏️ Edit"), " lets you give a probe a friendly name "
                        "(e.g. “Walk-in Fridge”), set a read interval, and enter a ",
                        html.B("Calibration Offset"), " if it reads slightly high or low. The offset is "
                        "applied to every reading automatically."], className="mb-1"),
            ]),

            _section("3 · Alerts & notifications", [
                html.P([html.B("Devices → ✏️ Edit"), " sets a min/max threshold per probe. ",
                        html.B("Settings → Notifications"), " turns on email and/or webhook (Slack, Discord, "
                        "Zapier, SMS relays). Alerts run on the hub, so they fire even with no browser open — "
                        "and you’re told when a probe goes ", html.B("offline"), " too."], className="mb-1"),
                html.Small("Use “Send test” to confirm your settings before you rely on them.",
                           className="text-muted"),
            ]),

            _section("4 · Your data", [
                html.P([html.B("Download CSV"), " on the Dashboard exports the selected time range. ",
                        html.B("Settings → Data Management"), " sets how long to keep readings and offers a "
                        "one-click database ", html.B("backup"), "."], className="mb-1"),
            ]),

            _section("Troubleshooting", [
                html.Ul([
                    html.Li("Probe shown but no readings? Give the auto-provisioner ~20 s, or check the probe’s "
                            "own page at http://<probe-ip>/status."),
                    html.Li("No probes at all? A firewall may block mDNS (UDP 5353). Readings still work if the "
                            "probe can reach the hub directly."),
                    html.Li("Times look wrong? The hub stores readings in the PC’s local timezone."),
                ], className="mb-1"),
            ]),

            html.Hr(),
            html.A("📘 Full documentation", href=DOCS_URL, target="_blank"),
        ]),
        dbc.ModalFooter(dbc.Button("Close", id="help-close", className="ms-auto", n_clicks=0)),
    ], id="help-modal", is_open=False, size="lg", scrollable=True)


def register_help_callbacks(app):
    @app.callback(
        Output("help-modal", "is_open"),
        [Input("help-open", "n_clicks"), Input("help-close", "n_clicks")],
        State("help-modal", "is_open"),
    )
    def toggle_help(open_click, close_click, is_open):
        if open_click or close_click:
            return not is_open
        return is_open

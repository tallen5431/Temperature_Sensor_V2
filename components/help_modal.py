import dash_bootstrap_components as dbc
from dash import Input, Output, State, html

from core.version import DOCS_URL


def HelpModal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Help & Quick Start")),
        dbc.ModalBody([
            html.P("Welcome to the Temperature Hub — your central dashboard for ESP32-based probes."),
            html.Ul([
                html.Li("✅  Power your probe and ensure it's on the same Wi-Fi network."),
                html.Li("✅  Open this dashboard on your PC or mobile device."),
                html.Li("✅  Wait ~10 s for the probe to auto-provision and start sending readings."),
            ]),
            html.Hr(),
            html.P("Available API endpoints:"),
            html.Code("/api/health, /api/config, /api/probes, /api/ingest"),
            html.Br(),
            html.Br(),
            html.A("📘 View full documentation", href=DOCS_URL, target="_blank"),
        ]),
        dbc.ModalFooter(dbc.Button("Close", id="help-close", className="ms-auto", n_clicks=0)),
    ], id="help-modal", is_open=False, size="lg")


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

# components/setup_helper.py
from __future__ import annotations
from dash import html, dcc, Input, Output, State, no_update
import dash_bootstrap_components as dbc

from wifi_scan import SSIDWatcher

# Background watcher for "TempSensor" SoftAP
_watcher = SSIDWatcher("TempSensor", interval_sec=5.0)
_watcher.start()

SetupHelper = dbc.Card(
    dbc.CardBody([
        html.Div(className="d-flex justify-content-between align-items-center", children=[
            html.H5("Probe Setup Helper (SoftAP)", className="mb-0"),
            html.Small(id="ap-seen-label", className="text-muted")
        ]),
        html.P(
            "If a probe is unprovisioned, it starts a temporary Wi‑Fi network named "
            "TempSensor. This hub can’t control your computer’s Wi‑Fi, but it will watch "
            "for that SSID and guide you to connect when it’s nearby."
        , className="mt-2"),
        html.Ul([
            html.Li("Put the probe in setup mode (power up without Wi‑Fi)."),
            html.Li("When you see “TempSensor” SSID below, join it from your computer."),
            html.Li("Then open the config page (192.168.4.1) to select your home Wi‑Fi."),
            html.Li("Come back here — the probe should appear in Probes and can be provisioned automatically."),
        ], className="small"),
        dbc.Alert(id="ap-status", color="secondary", className="mt-2"),
        html.Div([
            html.A("Open probe config (http://192.168.4.1)", id="open-ap-link",
                   href="http://192.168.4.1", target="_blank", className="btn btn-outline-primary btn-sm",
                   n_clicks=0, style={"pointerEvents": "none"})
        ], className="mt-2"),
        dcc.Interval(id="ap-poll", interval=4000, n_intervals=0)
    ]),
    className="h-100"
)

def register_setup_helper_callbacks(app):
    @app.callback(
        Output("ap-status", "children"),
        Output("ap-status", "color"),
        Output("ap-seen-label", "children"),
        Output("open-ap-link", "style"),
        Input("ap-poll", "n_intervals"),
        prevent_initial_call=False
    )
    def _update_ap(_n):
        seen = _watcher.seen()
        label = "TempSensor: visible" if seen else "TempSensor: not found"
        if seen:
            msg = "✅ Found TempSensor SoftAP nearby. Connect your computer to Wi‑Fi network “TempSensor”, then click the button below to open the probe’s config page."
            color = "success"
            style = {}  # enable link
        else:
            msg = "Waiting for TempSensor SoftAP… Power the probe with no saved Wi‑Fi so it starts the setup network. This page checks every few seconds."
            color = "secondary"
            style = {"pointerEvents": "none", "opacity": 0.5}
        return msg, color, label, style

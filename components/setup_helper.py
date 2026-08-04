# components/setup_helper.py
"""Probe SoftAP setup helper — the body of the Settings → "Set up a new probe" card.

The Wi-Fi watcher shells out to netsh/nmcli, so it must not run just because
someone opened Settings.  ``ap-poll`` therefore ships **disabled**; the Settings
page enables it only while this section is expanded, and the callback below —
which is where ``start()`` is called — cannot fire until then.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, html

from wifi_scan import SSIDWatcher

# The watcher shells out to netsh/nmcli to look for the probe's setup SoftAP.
# It is created lazily and only started the first time a user actually opens the
# "Set up a new probe" section, so hubs whose owners never use the wizard never
# run Wi-Fi scans in the background.
_watcher = SSIDWatcher("Setpoint", interval_sec=10.0)

_IDLE_MESSAGE = ("Open this section and the hub starts watching for the probe's "
                 "Setpoint-XXXXXX setup network.")

SetupHelperBody = [
    html.Div(className="d-flex justify-content-between align-items-center", children=[
        html.Small("A brand-new probe broadcasts its own Wi-Fi network so you can tell "
                   "it which network to join.", className="text-muted"),
        html.Small(id="ap-seen-label", className="text-muted"),
    ]),
    html.Ol([
        html.Li("Power the probe up with no saved Wi-Fi so it starts setup mode."),
        html.Li("When its “Setpoint-XXXXXX” network (matching the sticker on your "
                "unit) appears below, join it from this computer."),
        html.Li("Open the probe's config page and pick your Wi-Fi network."),
        html.Li("Come back here — the probe appears in Devices and configures itself."),
    ], className="small mt-2"),
    dbc.Alert(_IDLE_MESSAGE, id="ap-status", color="secondary", className="mt-2"),
    html.Div([
        html.A("Open probe config (http://192.168.4.1)", id="open-ap-link",
               href="http://192.168.4.1", target="_blank",
               className="btn btn-outline-primary btn-sm",
               n_clicks=0, style={"pointerEvents": "none", "opacity": 0.5}),
    ], className="mt-2"),
    # Disabled until the section is opened — see the module docstring.
    dcc.Interval(id="ap-poll", interval=5000, n_intervals=0, disabled=True),
]

def register_setup_helper_callbacks(app):
    @app.callback(
        Output("ap-status", "children"),
        Output("ap-status", "color"),
        Output("ap-seen-label", "children"),
        Output("open-ap-link", "style"),
        Input("ap-poll", "n_intervals"),
        # No initial call: the very first scan must be a consequence of someone
        # opening the section, not of the Settings page rendering.
        prevent_initial_call=True,
    )
    def _update_ap(_n):
        _watcher.start()  # idempotent; first call begins scanning
        # matched() returns the CONCRETE SSIDs seen (e.g. "Setpoint-9A3F2C"),
        # so we can tell the user exactly which network to join instead of the
        # generic brand prefix.
        names = _watcher.matched()
        if names:
            shown = ", ".join(names)
            join = ("join that network" if len(names) == 1
                    else "join the one matching the sticker on your unit")
            msg = (f"Found {shown} nearby — {join} from your computer, then click "
                   "the button below to open the probe's config page.")
            return msg, "success", f"Found: {shown}", {}
        label = "Setpoint-XXXXXX: not found"
        msg = ("Waiting for the probe's Setpoint-XXXXXX setup network… Power the probe "
               "with no saved Wi-Fi so it starts the setup network (its name matches "
               "the sticker on your unit). This page checks every few seconds.")
        return msg, "secondary", label, {"pointerEvents": "none", "opacity": 0.5}

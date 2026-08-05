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

from wifi_scan import SSIDWatcher, scanner_available

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

def set_scanning(enabled: bool) -> None:
    """Start or stop the background Wi-Fi scan.

    Gating the poll interval alone is not enough: the watcher runs its own thread
    and would keep shelling out to netsh/nmcli every few seconds for the life of
    the process after the section was opened once. The Settings page calls this
    as the section opens and closes so the scan really does track it.
    """
    if enabled:
        _watcher.start()
    else:
        _watcher.stop()


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
        hidden = {"pointerEvents": "none", "opacity": 0.5}
        if names:
            shown = ", ".join(names)
            join = ("join that network" if len(names) == 1
                    else "join the one matching the sticker on your unit")
            msg = (f"Found {shown} nearby — {join} from your computer, then click "
                   "the button below to open the probe's config page.")
            return msg, "success", f"Found: {shown}", {}

        # "Not found" is a claim about the airwaves, and on a lot of real hubs
        # this machine is in no position to make it: an always-on mini-PC is
        # usually wired, macOS 14.4 removed the `airport` scanner outright, and
        # Raspberry Pi OS Lite ships with neither nmcli nor iwlist. Reporting
        # those as "not found" sent a customer off to power-cycle a probe that
        # may well have been broadcasting the whole time.
        if not scanner_available():
            return (["This computer can't scan for Wi-Fi networks, so the hub "
                     "can't tell you whether the probe's setup network is up. ",
                     html.Strong("Setup still works: "),
                     "look for a network named Setpoint-XXXXXX (matching the "
                     "sticker on your unit) on your phone or laptop, join it, "
                     "and open ", html.Code("http://192.168.4.1"), "."],
                    "warning", "Wi-Fi scanning unavailable", hidden)
        if _watcher.scanned and not _watcher.latest:
            return (["The hub scanned and saw ", html.Strong("no Wi-Fi networks "
                     "at all"), " — not just no Setpoint one. This machine most "
                     "likely has no Wi-Fi adapter (a wired hub) or is not "
                     "permitted to scan. Join the probe's Setpoint-XXXXXX "
                     "network from your phone instead, then open ",
                     html.Code("http://192.168.4.1"), "."],
                    "warning", "No networks visible", hidden)

        label = "Setpoint-XXXXXX: not found"
        msg = ("Waiting for the probe's Setpoint-XXXXXX setup network… Power the probe "
               "with no saved Wi-Fi so it starts the setup network (its name matches "
               "the sticker on your unit). This page checks every few seconds.")
        return msg, "secondary", label, hidden

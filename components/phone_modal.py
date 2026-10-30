"""'Open on your phone' — the hub's own addresses, and a QR code to scan."""
from __future__ import annotations

import os

import dash_bootstrap_components as dbc
from dash import Input, Output, State, html

from core.phone_access import access_urls, qr_data_uri


def PhoneModal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Open on your phone")),
        dbc.ModalBody(id="phone-modal-body"),
        dbc.ModalFooter(dbc.Button("Close", id="phone-close", color="secondary")),
    ], id="phone-modal", is_open=False, centered=True)


def phone_modal_body(urls, qr_uri, login_on=False):
    """The modal's contents. Pure, so the copy can be tested without a browser."""
    if not urls:
        return dbc.Alert("This PC has no network address another device can reach. "
                         "Check that it is connected to your Wi-Fi.", color="warning")
    first = urls[0]
    children = []
    if qr_uri:
        children.append(html.Div([
            html.Img(src=qr_uri, alt=f"QR code for {first['url']}",
                     style={"width": "200px", "height": "200px"}),
            html.Small("Point your phone's camera at the code.",
                       className="text-muted d-block mt-2"),
        ], className="text-center mb-3"))
    for u in urls:
        children.append(html.Div([
            html.Div(u["label"], className="fw-bold small"),
            html.A(u["url"], href=u["url"], className="font-monospace"),
            html.Small(u["note"], className="text-muted d-block"),
        ], className="mb-2"))
    children.append(html.Small(
        "Then use your browser's Add to Home Screen to keep it as an app.",
        className="text-muted d-block mt-2"))
    if login_on:
        children.append(html.Small("Your phone will ask for the dashboard login.",
                                   className="text-muted d-block"))
    return children


def register_phone_callbacks(app, cfg, public_base_func=None):
    @app.callback(
        Output("phone-modal", "is_open"),
        Output("phone-modal-body", "children"),
        Input("phone-open", "n_clicks"),
        Input("phone-close", "n_clicks"),
        State("phone-modal", "is_open"),
        prevent_initial_call=True,
    )
    def _toggle(open_clicks, _close, is_open):
        from dash import ctx, no_update
        if ctx.triggered_id != "phone-open":
            return False, no_update
        base = public_base_func() if public_base_func else ""
        mdns_on = os.getenv("MDNS_ENABLE", "1") not in ("0", "false", "False")
        urls = access_urls(base, mdns_enabled=mdns_on)
        ua = cfg.get("ui_auth", {}) or {}
        login_on = bool(os.getenv("UI_USERNAME") or ua.get("enabled"))
        return True, phone_modal_body(urls, qr_data_uri(urls[0]["url"]) if urls else None,
                                      login_on)

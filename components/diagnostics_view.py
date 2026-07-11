"""Diagnostics page: a customer-readable health snapshot with one-click copy.

The heavy lifting is in core.diagnostics.build_diagnostics (pure, tested); this
module only renders it and wires a refresh + clipboard.
"""
import json
import logging

import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, html

from core.diagnostics import build_diagnostics, human_size
from core.version import HUB_VERSION, PRODUCT_NAME

log = logging.getLogger("hub.diagnostics")


DiagnosticsLayout = html.Div([
    dbc.Row([
        dbc.Col(html.H4("Diagnostics", className="mb-0"), width="auto"),
        dbc.Col(
            dcc.Clipboard(id="diag-copy", title="Copy diagnostics",
                          style={"fontSize": "1.4rem", "cursor": "pointer"}),
            width="auto", className="ms-auto d-flex align-items-center",
        ),
    ], className="align-items-center mb-1"),
    html.Small("A snapshot of hub health you can copy and send to support.",
               className="text-muted d-block mb-3"),
    html.Div(id="diag-body"),
    html.A("Open raw JSON (/api/diagnostics)", href="/api/diagnostics", target="_blank",
           className="small d-block mt-3"),
    dcc.Interval(id="diag-refresh", interval=10000, n_intervals=0),
])


def _kv_table(rows):
    return dbc.Table([html.Tbody([
        html.Tr([html.Td(k, className="fw-bold", style={"width": "40%"}), html.Td(v)])
        for k, v in rows
    ])], bordered=False, hover=False, size="sm", className="mb-0")


def _notif_summary(n):
    if not n.get("enabled"):
        return "Off"
    channels = [name for name, on in
                (("Email", n.get("email")), ("Webhook", n.get("webhook"))) if on]
    extra = " + offline alerts" if n.get("offline_alerts") else ""
    return (", ".join(channels) or "On (no channel selected)") + extra


def _render(d):
    db = d["database"]
    pr = d["probes"]
    summary = _kv_table([
        ("Product", f"{d['product']} v{d['version']}"),
        ("Hub URL", html.Code(d["server"]["base"])),
        ("Readings stored", f"{db['readings']:,}" if isinstance(db["readings"], int) else "—"),
        ("Database size", human_size(db["size_bytes"])),
        ("Newest reading", db["newest_reading"] or "—"),
        ("Retention", f"{d['retention_days']} days" if d["retention_days"] else "Forever"),
        ("Probes", f"{pr['online']} online / {pr['total']} total"),
        ("Notifications", _notif_summary(d["notifications"])),
        ("Generated", d["time"]),
    ])

    children = [dbc.Card(dbc.CardBody([html.H6("Summary", className="text-info"), summary]),
                         className="mb-3")]

    if pr["list"]:
        head = html.Thead(html.Tr([html.Th("Name"), html.Th("Probe ID"),
                                   html.Th("IP"), html.Th("Last seen"), html.Th("Status")]))
        body = html.Tbody([
            html.Tr([
                html.Td(p.get("name") or "—"),
                html.Td(html.Code(p.get("probe_id") or "—")),
                html.Td(p.get("ip") or "—"),
                html.Td(f"{p['age_sec']:.0f} s ago" if isinstance(p.get("age_sec"), (int, float)) else "—"),
                html.Td(html.Span("● online" if p.get("online") else "● offline",
                                  className="text-success" if p.get("online") else "text-danger")),
            ]) for p in pr["list"]
        ])
        children.append(dbc.Card(dbc.CardBody([
            html.H6("Probes", className="text-info"),
            dbc.Table([head, body], bordered=False, hover=True, size="sm", responsive=True, className="mb-0"),
        ])))
    return html.Div(children)


def register_diagnostics_callbacks(app, finder, cfg, db, public_base_func=None):
    @app.callback(
        Output("diag-body", "children"),
        Output("diag-copy", "content"),
        Input("diag-refresh", "n_intervals"),
    )
    def _update(_):
        try:
            base = public_base_func() if public_base_func else ""
            d = build_diagnostics(cfg, db, finder, base, HUB_VERSION, PRODUCT_NAME)
            return _render(d), json.dumps(d, indent=2)
        except Exception:
            log.exception("diagnostics render failed")
            return dbc.Alert("Could not build diagnostics.", color="danger"), ""

"""Diagnostics page: a customer-readable health snapshot with one-click copy.

The heavy lifting is in core.diagnostics.build_diagnostics (tested; it performs
the reads — discovery, DB, disk, health snapshot); this module only renders its
result and wires a refresh + clipboard.
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


def _fmt_uptime(sec):
    if not isinstance(sec, (int, float)) or sec < 0:
        return "—"
    sec = int(sec)
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def _fmt_age(sec):
    if not isinstance(sec, (int, float)):
        return "—"
    if sec < 60:
        return "just now"
    if sec < 3600:
        return f"{int(sec // 60)} min ago"
    return f"{int(sec // 3600)} h ago"


def _health_card(h):
    healthy = h.get("healthy")
    disk = h.get("disk_free_bytes")
    low_disk = isinstance(disk, (int, float)) and disk < 512 * 1024 * 1024  # < 512 MB
    disk_cell = html.Span(human_size(disk),
                          className="text-warning fw-bold" if low_disk else "")
    rows = [
        ("Status", dbc.Badge("● Healthy" if healthy else "● Needs attention",
                             color="success" if healthy else "warning")),
        ("Uptime", _fmt_uptime(h.get("uptime_sec"))),
        ("Readings (last 24 h)",
         f"{h['readings_24h']:,}" if isinstance(h.get("readings_24h"), int) else "—"),
        ("Last write", _fmt_age(h.get("last_write_age_sec"))),
        ("Rows written (this run)", f"{h.get('rows_written', 0):,}"),
        ("Rejected ingests", f"{h.get('ingest_rejected', 0):,}"),
        ("Write failures", f"{h.get('write_failures', 0):,}"),
        ("Disk free", disk_cell),
    ]

    # Background threads. Named individually, because "which one stopped" is the
    # first thing support would ask and the answer changes what to do about it.
    workers = h.get("workers") or {}
    if workers:
        stopped = sorted(n for n, alive in workers.items() if not alive)
        rows.append((
            "Background tasks",
            html.Span(f"{len(workers) - len(stopped)} of {len(workers)} running"
                      + (f" — stopped: {', '.join(stopped)}" if stopped else ""),
                      className="text-warning fw-bold" if stopped else "")))

    body = [html.H6("System health", className="text-info"), _kv_table(rows)]

    # The alert monitor stopping is not one warning among several: readings keep
    # arriving, the dashboard keeps drawing, and nothing else on this page would
    # look wrong — while no alarm is ever raised again. Say what it means and
    # what to do, rather than leaving "1 of 3 running" to be interpreted.
    if h.get("workers_down"):
        body.append(dbc.Alert(
            [html.Strong("Alerting has stopped. "),
             "The task that compares readings against their limits is no longer "
             "running, so ", html.Strong("no alarm will be raised"),
             " even though readings are still being recorded. Restart the hub. "
             "If it happens again, send this page to support — ",
             html.Code("logs/hub.log"), " will say why."],
            color="danger", className="mt-2 mb-0 py-2 small"))
    if low_disk:
        body.append(dbc.Alert("⚠ Low disk space — consider setting a retention limit "
                              "(Settings → Data & storage) or freeing space.",
                              color="warning", className="mt-2 mb-0 py-2 small"))
    return dbc.Card(dbc.CardBody(body), className="mb-3")


def _notif_summary(n):
    if not n.get("enabled"):
        return "Off"
    channels = [name for name, on in
                (("Email", n.get("email")), ("Webhook", n.get("webhook"))) if on]
    extra = " + offline alerts" if n.get("offline_alerts") else ""
    return (", ".join(channels) or "On (no channel selected)") + extra


def _probe_sources(pr) -> str:
    """How the hub knows about these probes, said accurately.

    This read "N discovered (mDNS)" for the whole list, but the list also carries
    probes known only from their ingest posts (build_diagnostics tags those
    source="readings"). A deep-sleeping probe never answers mDNS at all, so on a
    battery fleet the line claimed mDNS discovery for probes mDNS had never seen
    — on the one page support asks a customer to send in.
    """
    items = pr.get("list") or []
    via_readings = sum(1 for p in items if p.get("source") == "readings")
    mdns = len(items) - via_readings
    if not items:
        return "none discovered yet"
    if via_readings and mdns:
        return f"{mdns} found on the network, {via_readings} known from their readings"
    if via_readings:
        return f"{via_readings} known from their readings (not seen on the network)"
    return f"{mdns} found on the network (mDNS)"


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
        ("Probes", (f"{pr['reporting']} reporting" if pr.get("reporting") is not None
                    else f"{pr['online']} online") + " · " + _probe_sources(pr)),
        ("Notifications", _notif_summary(d["notifications"])),
        ("Generated", d["time"]),
    ])

    children = [dbc.Card(dbc.CardBody([html.H6("Summary", className="text-info"), summary]),
                         className="mb-3")]

    if d.get("health"):
        children.append(_health_card(d["health"]))

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

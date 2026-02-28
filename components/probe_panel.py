from dash import html, dcc, Input, Output, State, no_update
import dash_bootstrap_components as dbc
from datetime import datetime

# ---------------- UI ----------------
ProbePanel = dbc.Card(
    dbc.CardBody([
        html.H5("Probes (auto-discovery)"),
        dbc.Row([
            dbc.Col([
                html.Button("Scan now", id="probe-scan", className="btn btn-secondary btn-sm"),
                dcc.Interval(id="probe-refresh", interval=5000, n_intervals=0),
                html.Div(id="probe-scan-status", className="text-info mt-2")
            ], width=4),
            dbc.Col([
                dbc.Label("Auto-provision new probes"),
                dcc.Checklist(
                    id="auto-provision",
                    options=[{"label": " Enabled", "value": "on"}],
                    value=["on"],
                    persistence=True
                ),
                dbc.Label("Push interval (ms)", className="mt-2"),
                dcc.Input(
                    id="push-interval-ms",
                    type="number",
                    min=500,
                    step=100,
                    value=5000,
                    persistence=True
                ),
                dbc.Label("Provision token (optional)", className="mt-2"),
                dcc.Input(
                    id="provision-token",
                    type="text",
                    placeholder="X-Token to send to hub",
                    persistence=True
                ),
                html.Button("Save Provision Settings", id="save-provision", className="btn btn-primary btn-sm mt-2"),
                html.Div(id="provision-save-status", className="text-info mt-2")
            ], width=8)
        ], className="gy-2"),
        html.Hr(),
        html.Div(id="probe-list")
    ])
)


# ---------------- Helpers ----------------
def _decode_txt(props):
    """Zeroconf TXT props can be bytes; normalize to {str: str}."""
    out = {}
    try:
        if isinstance(props, dict):
            for k, v in props.items():
                if isinstance(k, bytes):
                    k = k.decode(errors="ignore")
                if isinstance(v, bytes):
                    v = v.decode(errors="ignore")
                out[str(k)] = str(v)
    except Exception:
        pass
    return out


def _render_probes(items):
    if not items:
        return html.Small("(no probes found yet)", className="text-muted")

    cards = []
    for p in items:
        pid = p.get("probe_id") or "(unknown)"
        name = p.get("name") or ""
        host = p.get("host") or "?"
        port = p.get("port") or 0
        last = p.get("last_seen")

        if isinstance(last, str):
            last_str = last
        else:
            try:
                last_str = last.isoformat(sep=" ") if last else ""
            except Exception:
                last_str = str(last) if last else ""

                # Prefer IP for links when available
        addr = f"{p.get('ip')}:{port}" if p.get("ip") else (f"{host}:{port}" if host not in ("?", None) and port else None)
        whoami_url = f"http://{addr}/whoami" if addr else None

        header_children = [
            dbc.Badge(pid, color="info", className="me-2"),
            html.Code(addr) if addr else html.Code("(unknown)")
        ]
        if whoami_url:
            header_children.append(html.A(" whoami", href=whoami_url, target="_blank", className="ms-2"))
        if name:
            header_children.append(html.Small(name, className="text-muted ms-2"))

        cards.append(
            dbc.Card(
                dbc.CardBody([
                    html.Div(header_children),
                    html.Small(f"Last seen: {last_str}", className="text-muted d-block mt-1")
                ]),
                className="mb-2"
            )
        )
    return html.Div(cards)


# ---------------- Callbacks ----------------
# discovery must expose list_probes() -> dict[str, obj] and scan()
# cfg persistence handled via cfg.lock and cfg.save()

def register_probe_callbacks(app, discovery, cfg):
    # Ensure discovery is running
    try:
        discovery.start()
    except Exception:
        pass

    @app.callback(
        Output("probe-list", "children"),
        Input("probe-refresh", "n_intervals"),
        prevent_initial_call=False
    )
    def _refresh_list(_):
        try:
            entries = []
            for p in (discovery.list_probes() or {}).values():
                props = _decode_txt(getattr(p, "properties", {}) or {})
                entries.append({
                    # Prefer mDNS TXT 'id' as the stable probe id, then fallbacks
                    "probe_id": props.get("id")
                                or getattr(p, "probe_id", None)
                                or getattr(p, "id", None)
                                or getattr(p, "name", None),
                    "name": props.get("name") or getattr(p, "name", None),
                    "host": getattr(p, "host", None),
                    "ip": getattr(p, "ip", None),
                    "port": getattr(p, "port", None),
                    "last_seen": getattr(p, "last_seen", None),
                })
            return _render_probes(entries)
        except Exception:
            return _render_probes([])

    @app.callback(
        Output("probe-scan-status", "children"),
        Input("probe-scan", "n_clicks"),
        prevent_initial_call=True
    )
    def _scan(_n):
        try:
            discovery.scan()
            return "🔎 Scanned"
        except Exception as e:
            return f"❌ {e}"

    @app.callback(
        Output("provision-save-status", "children"),
        Input("save-provision", "n_clicks"),
        State("auto-provision", "value"),
        State("push-interval-ms", "value"),
        State("provision-token", "value"),
        prevent_initial_call=True
    )
    def _save_prov(_, auto_vals, ms, token):
        try:
            auto = bool(auto_vals and "on" in auto_vals)
            with cfg.lock:
                cfg.data["auto_provision"] = auto
                if ms:
                    # UI keeps ms; convert to sec for cfg (server will push to probes)
                    cfg.data["interval_sec"] = max(1, int(int(ms) / 1000))
                cfg.data["provision_token"] = (token or "").strip()
            cfg.save()
            return "✅ Saved"
        except Exception as e:
            return f"❌ {e}"

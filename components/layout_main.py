import datetime

import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, html

from components.dashboard_view import DashboardLayout, _reporting_probe_count
from components.devices_panel import DevicesLayout, register_devices_callbacks
from components.diagnostics_view import DiagnosticsLayout, register_diagnostics_callbacks
from components.setup_helper import register_setup_helper_callbacks
from components.settings_panel import SettingsPanel, register_settings_callbacks
from components.help_modal import HelpModal, HelpPage
from core.status import hub_status
from core.version import HUB_VERSION, PRODUCT_NAME

# Maps a semantic hub state (core.status.hub_status) to footer text + colour.
_STATUS_DISPLAY = {
    "online":  ("text-success", "● {online} probe{s} online"),
    "offline": ("text-warning", "● {total} probe{s} offline"),
    "idle":    ("text-warning", "● Idle — no probe connected"),
    "waiting": ("text-muted",   "Waiting for first probe…"),
}


def footer_status_display(status: dict) -> tuple[str, str]:
    """Return ``(text, css_class)`` for the footer from a hub_status() dict."""
    css, template = _STATUS_DISPLAY.get(status.get("state"), ("text-muted", "Status: unknown"))
    n = status.get("online") if status.get("state") == "online" else status.get("total", 0)
    text = template.format(online=status.get("online", 0), total=status.get("total", 0),
                           s="" if n == 1 else "s")
    return text, f"{css} fw-bold"


# The gauge card's "LIVE" badge (driven from register_dashboard_callbacks,
# NOT from the footer: the footer lives on every page and live-badge only on
# the dashboard, so a footer-owned Output would fail with "a nonexistent
# object was used in an Output" the moment you opened Settings -- taking the
# footer's own status down with it).
# It carried an id but nothing ever wrote to it,
# so it was a hard-coded green LIVE that stayed lit on a hub with no data at all
# and on one whose probes had been silent for hours — a status light wired to
# nothing, on a monitoring product. It now reports the same hub state the footer
# does, so the two can never disagree.
_LIVE_DISPLAY = {
    "online":  ("LIVE",    "ms-2 text-success small fw-bold"),
    "offline": ("NO DATA", "ms-2 text-warning small fw-bold"),
    "idle":    ("NO DATA", "ms-2 text-warning small fw-bold"),
    "waiting": ("",        "ms-2 text-muted small fw-bold"),
}


def live_badge_display(status: dict) -> tuple[str, str]:
    """Return ``(text, css_class)`` for the gauge's LIVE badge."""
    return _LIVE_DISPLAY.get(status.get("state"), ("", "ms-2 text-muted small fw-bold"))


def serve_page(pathname):
    if pathname == "/devices":
        return DevicesLayout
    elif pathname == "/settings":
        return html.Div([
            html.H4("Settings", className="mb-1"),
            html.Small("Open a section to change it — the badge on the right shows "
                       "what it is set to now.", className="text-muted d-block mb-3"),
            SettingsPanel,
        ])
    elif pathname == "/diagnostics":
        return DiagnosticsLayout
    elif pathname == "/help":
        return HelpPage()
    else:
        return DashboardLayout


NAVBAR = dbc.Navbar(
    dbc.Container([
        html.A(
            dbc.Row([
                dbc.Col(html.Img(src="/assets/logo.svg", height="30", alt="",
                                 className="d-block"), width="auto"),
                dbc.Col(dbc.NavbarBrand(PRODUCT_NAME, className="ms-2 fw-bold mb-0"),
                        width="auto"),
            ], align="center", className="g-0"),
            href="/", style={"textDecoration": "none"},
        ),
        dbc.Nav([
            dbc.NavItem(dbc.NavLink("Dashboard", href="/", active="exact")),
            dbc.NavItem(dbc.NavLink("Devices", href="/devices", active="exact")),
            dbc.NavItem(dbc.NavLink("Settings", href="/settings", active="exact")),
            dbc.NavItem(dbc.NavLink("Diagnostics", href="/diagnostics", active="exact")),
            dbc.NavItem(dbc.Button("Help", id="help-open", color="info", size="sm", className="ms-2")),
        ], className="ms-auto", navbar=True),
    ]), color="dark", dark=True, sticky="top",
)

FOOTER = html.Footer(
    dbc.Container([
        html.Hr(className="mb-3 mt-4"),
        html.Small(f"© {datetime.datetime.now().year} {PRODUCT_NAME} · v{HUB_VERSION}  ·  "),
        html.Small("Status: starting…", id="footer-status", className="text-muted fw-bold"),
        dcc.Interval(id="footer-refresh", interval=5000, n_intervals=0),
    ], className="text-center text-muted py-2"),
    className="footer",
)

# app-shell is a full-height flex column so the footer sits at the BOTTOM of the
# viewport on short pages (Devices, Settings, Diagnostics) instead of floating
# directly under the content with several hundred px of empty page beneath it,
# which read as a half-loaded screen.
LAYOUT = html.Div([
    dcc.Location(id="url", refresh=False),
    # App-wide display preferences. No default: an empty store means "this
    # browser has never chosen", which is what lets the clientside locale probe
    # fill in °F / 12-hour for the people who expect them. They live here rather
    # than in DashboardLayout so every page can read them — Devices renders
    # temperatures too, and used to have no way to know the unit.
    dcc.Store(id="temp-unit-store", storage_type="local"),
    dcc.Store(id="clock-format-store", storage_type="local"),
    NAVBAR,
    html.Div(id="page-content", className="p-4"),
    HelpModal(),
    FOOTER,
], className="app-shell")


def register_footer_callbacks(app, finder, cfg, db):
    @app.callback(
        Output("footer-status", "children"),
        Output("footer-status", "className"),
        Input("footer-refresh", "n_intervals"),
    )
    def _update_footer(_):
        try:
            probes = (finder.list_probes() or {}).values()
            timeout = int(cfg.get("probe_online_timeout_sec", 60) or 60)
            # Use the same DB-based freshness count the dashboard shows, so the
            # footer agrees with "Connected Probes" (deep-sleep / demo probes
            # report to the DB but are never mDNS-visible).
            reporting = _reporting_probe_count(db, cfg, finder)
            status = hub_status(probes, timeout, db.count(), reporting_online=reporting)
            return footer_status_display(status)
        except Exception:
            return "Status: unknown", "text-muted fw-bold"


def register_all_callbacks(app, finder, cfg, db, public_base_func=None, token=""):
    from components.dashboard_view import register_dashboard_callbacks
    register_dashboard_callbacks(app, finder, cfg, db,
                                 public_base_func=public_base_func, token=token)
    register_devices_callbacks(app, finder, cfg, db, public_base_func=public_base_func, token=token)
    register_diagnostics_callbacks(app, finder, cfg, db, public_base_func=public_base_func)
    register_setup_helper_callbacks(app)
    register_settings_callbacks(app, cfg, public_base_func=public_base_func)
    register_footer_callbacks(app, finder, cfg, db)

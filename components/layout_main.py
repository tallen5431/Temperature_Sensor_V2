import datetime

import dash_bootstrap_components as dbc
from dash import dcc, html

from components.dashboard_view import DashboardLayout
from components.devices_panel import DevicesLayout, register_devices_callbacks
from components.setup_helper import SetupHelper, register_setup_helper_callbacks
from components.settings_panel import SettingsPanel, register_settings_callbacks
from components.help_modal import HelpModal
from core.version import HUB_VERSION, PRODUCT_NAME


def serve_page(pathname):
    if pathname == "/devices":
        return DevicesLayout
    elif pathname == "/settings":
        return html.Div([html.H4("Settings & Configuration", className="mb-3"),
                         SettingsPanel, SetupHelper])
    elif pathname == "/help":
        return html.Div([HelpModal()])
    else:
        return DashboardLayout


NAVBAR = dbc.Navbar(
    dbc.Container([
        html.A(
            dbc.Row([
                dbc.Col(html.Span("🌡️", className="fs-4")),
                dbc.Col(dbc.NavbarBrand(PRODUCT_NAME, className="ms-2 fw-bold")),
            ], align="center", className="g-0"),
            href="/", style={"textDecoration": "none"},
        ),
        dbc.Nav([
            dbc.NavItem(dbc.NavLink("Dashboard", href="/", active="exact")),
            dbc.NavItem(dbc.NavLink("Devices", href="/devices", active="exact")),
            dbc.NavItem(dbc.NavLink("Settings", href="/settings", active="exact")),
            dbc.NavItem(dbc.Button("Help", id="help-open", color="info", size="sm", className="ms-2")),
        ], className="ms-auto", navbar=True),
    ]), color="dark", dark=True, sticky="top",
)

FOOTER = html.Footer(
    dbc.Container([
        html.Hr(className="mb-3 mt-4"),
        html.Small(f"© {datetime.datetime.now().year} {PRODUCT_NAME} · v{HUB_VERSION} "),
        html.Small(" Status: Ready", className="text-success fw-bold"),
    ], className="text-center text-muted py-2"),
    className="footer",
)

LAYOUT = html.Div([
    dcc.Location(id="url", refresh=False),
    NAVBAR,
    html.Div(id="page-content", className="p-4"),
    HelpModal(),
    FOOTER,
])


def register_all_callbacks(app, finder, cfg, db, public_base_func=None, token=""):
    from components.dashboard_view import register_dashboard_callbacks
    register_dashboard_callbacks(app, finder, cfg, db)
    register_devices_callbacks(app, finder, cfg, public_base_func=public_base_func, token=token)
    register_setup_helper_callbacks(app)
    register_settings_callbacks(app, cfg)

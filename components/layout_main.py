from dash import html, dcc
import dash_bootstrap_components as dbc

from core.version import __version__
from components.dashboard_view import build_dashboard_layout
from components.devices_panel import DevicesLayout, register_devices_callbacks
from components.setup_helper import build_settings_page, register_settings_callbacks
from components.help_modal import HelpModal


def serve_page(pathname, cfg):
    branding = cfg.get("branding", {}) or {}
    settings = cfg.get("settings", {}) or {}
    default_unit = settings.get("default_unit", "celsius")
    if pathname == "/devices":
        return DevicesLayout
    elif pathname == "/settings":
        return build_settings_page(cfg)
    else:
        return build_dashboard_layout(default_unit)


def build_navbar(branding: dict):
    product = branding.get("product_name", "ThermaHub")
    logo = branding.get("logo_path", "/assets/logo.svg")
    return dbc.Navbar(
        dbc.Container([
            html.A(
                dbc.Row([
                    dbc.Col(html.Img(src=logo, height="30px", className="d-inline-block")),
                    dbc.Col(dbc.NavbarBrand(product, className="ms-2 fw-bold")),
                ], align="center", className="g-0"), href="/",
                style={"textDecoration": "none"},
            ),
            dbc.Nav([
                dbc.NavItem(dbc.NavLink("Dashboard", href="/", active="exact")),
                dbc.NavItem(dbc.NavLink("Devices", href="/devices", active="exact")),
                dbc.NavItem(dbc.NavLink("Settings", href="/settings", active="exact")),
                dbc.NavItem(dbc.Button("Help", id="help-open", color="info", size="sm", className="ms-2")),
            ], className="ms-auto", navbar=True),
        ]), color="dark", dark=True, sticky="top",
    )


def build_footer(branding: dict):
    holder = branding.get("copyright", branding.get("brand_name", "ThermaHub"))
    product = branding.get("product_name", "ThermaHub")
    return html.Footer(
        dbc.Container([
            html.Hr(className="mb-3 mt-4"),
            html.Small(f"© {holder} · {product} v{__version__} · "),
            html.Small("All readings stay on this PC — no cloud, no account.",
                       className="text-success"),
        ], className="text-center text-muted py-2"),
        className="footer",
    )


def build_layout(cfg):
    branding = cfg.get("branding", {}) or {}
    return html.Div([
        dcc.Location(id="url", refresh=False),
        build_navbar(branding),
        html.Div(id="page-content", className="p-4"),
        HelpModal(cfg),
        build_footer(branding),
    ])


def register_all_callbacks(app, finder, cfg):
    from components.dashboard_view import register_dashboard_callbacks
    register_dashboard_callbacks(app, finder, cfg)
    register_devices_callbacks(app, finder, cfg)
    register_settings_callbacks(app, cfg)

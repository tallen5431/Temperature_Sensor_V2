from dash import html, Input, Output, State
import dash_bootstrap_components as dbc


def HelpModal(cfg=None):
    branding = (cfg.get("branding", {}) if cfg else {}) or {}
    product = branding.get("product_name", "ThermaHub")
    probe_name = branding.get("brand_name", "ThermaHub") + " probe"
    support_url = branding.get("support_url", "https://example.com/support")
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Help & Quick Start")),
        dbc.ModalBody([
            html.P(f"Welcome to {product} — your private dashboard for wireless temperature probes."),
            html.P("Getting started takes about two minutes:"),
            html.Ol([
                html.Li("Plug in your probe (USB power)."),
                html.Li(f"On your phone or PC, join the temporary Wi-Fi network named like “{probe_name}”."),
                html.Li("A setup page opens automatically — pick your home Wi-Fi and enter its password."),
                html.Li("Come back to this dashboard. Your probe appears within ~15 seconds and readings begin."),
                html.Li("Open Devices to give each probe a friendly name (e.g. “Kitchen Fridge”)."),
            ]),
            html.Hr(),
            html.P("Your data never leaves this computer — there is no cloud account and no telemetry. "
                   "Use Download CSV on the dashboard to export to Excel or Google Sheets."),
            html.A("📘 Support & documentation", href=support_url, target="_blank"),
        ]),
        dbc.ModalFooter(dbc.Button("Close", id="help-close", className="ms-auto", n_clicks=0)),
    ], id="help-modal", is_open=False, size="lg")


def register_help_callbacks(app):
    @app.callback(
        Output("help-modal", "is_open"),
        [Input("help-open", "n_clicks"), Input("help-close", "n_clicks")],
        State("help-modal", "is_open"),
    )
    def toggle_help(open_click, close_click, is_open):
        if open_click or close_click:
            return not is_open
        return is_open

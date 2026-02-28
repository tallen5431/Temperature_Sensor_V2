from dash import html, dcc
import dash_bootstrap_components as dbc

from components.dashboard_view import DashboardLayout
from components.devices_panel import DevicesLayout, register_devices_callbacks
from components.setup_helper import SetupHelper
from components.help_modal import HelpModal

def serve_page(pathname):
    if pathname == '/devices':
        return DevicesLayout
    elif pathname == '/settings':
        return html.Div([html.H4('Settings & Configuration'), SetupHelper])
    elif pathname == '/help':
        return html.Div([HelpModal()])
    else:
        return DashboardLayout

NAVBAR = dbc.Navbar(
    dbc.Container([
        html.A(
            dbc.Row([
                dbc.Col(html.Img(src='/assets/logo.png', height='32px')),
                dbc.Col(dbc.NavbarBrand('Temperature Hub', className='ms-2 fw-bold'))
            ], align='center', className='g-0'), href='/'
        ),
        dbc.Nav([
            dbc.NavItem(dbc.NavLink('Dashboard', href='/', active='exact')),
            dbc.NavItem(dbc.NavLink('Devices', href='/devices', active='exact')),
            dbc.NavItem(dbc.NavLink('Settings', href='/settings', active='exact')),
            dbc.NavItem(dbc.Button('Help', id='help-open', color='info', size='sm', className='ms-2'))
        ], className='ms-auto', navbar=True)
    ]), color='dark', dark=True, sticky='top'
)

FOOTER = html.Footer(
    dbc.Container([
        html.Hr(className='mb-3 mt-4'),
        html.Small('© 2025 YourBrand | Temperature Hub v1.0 '),
        html.Small(' Status: Ready', className='text-success fw-bold')
    ], className='text-center text-muted py-2'),
    className='footer'
)

LAYOUT = html.Div([
    dcc.Location(id='url', refresh=False),
    NAVBAR,
    html.Div(id='page-content', className='p-4'),
    HelpModal(),
    FOOTER
])

def register_all_callbacks(app, finder, cfg):
    from components.dashboard_view import register_dashboard_callbacks
    register_dashboard_callbacks(app, finder, cfg)
    register_devices_callbacks(app, finder, cfg)

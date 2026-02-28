import os
import socket
from pathlib import Path
import dash
from dash import Dash, html, Input, Output
import dash_bootstrap_components as dbc
from flask import Flask

from core.config import Config
from core.storage import ensure_csv
from core.mdns_advert import MdnsAdvert
from probe_discovery import ProbeDiscovery
from api.routes import create_api
from components.layout_main import LAYOUT, serve_page, register_all_callbacks
from components.help_modal import register_help_callbacks

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = Path(os.getenv('CSV_FILE', str(BASE_DIR / 'temperature_log.csv')))
CONFIG_FILE = BASE_DIR / 'config.json'

ensure_csv(CSV_FILE)
cfg = Config(CONFIG_FILE)
finder = ProbeDiscovery()
try: finder.start()
except Exception: pass

server = Flask(__name__)
def _detect_lan_ip() -> str:
    """Best-effort LAN IP detection (no extra deps)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No packets actually sent; picks outbound interface.
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return "127.0.0.1"


def _public_base() -> str:
    base = (os.getenv("PUBLIC_BASE", "") or "").strip()
    if base:
        return base.rstrip("/")
    port = int(os.getenv("PORT", "8080"))
    return f"http://{_detect_lan_ip()}:{port}"

api_bp = create_api(cfg, str(CSV_FILE), finder, _public_base, os.getenv('SERVER_TOKEN', ''))
server.register_blueprint(api_bp)

app = Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], server=server, suppress_callback_exceptions=True)
app.title = 'Temperature Hub'
app.layout = LAYOUT

# --- CSV Download Route ---
from flask import send_file
from werkzeug.utils import safe_join

@server.route('/download/<path:filename>')
def download_csv(filename):
    try:
        full_path = safe_join(BASE_DIR, filename)
        return send_file(full_path, as_attachment=True)
    except Exception as e:
        return f'Error: {e}', 404


@app.callback(Output('page-content', 'children'), Input('url', 'pathname'))
def display_page(pathname):
    return serve_page(pathname)

register_all_callbacks(app, finder, cfg)
register_help_callbacks(app)

if __name__ == '__main__':
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '8080'))
    mdns = MdnsAdvert() if (os.getenv('MDNS_ENABLE', '1') not in ('0','false','False')) else None

    # Start auto-provisioner if enabled
    provisioner = None
    if cfg.get('auto_provision', True):
        from auto_provisioner import AutoProvisioner
        provisioner = AutoProvisioner(
            discovery=finder,
            public_base_func=_public_base,
            token=cfg.get('provision_token', ''),
            interval_ms=cfg.get('interval_sec', 5) * 1000,
            period_sec=10
        )
        provisioner.start()
        print(f'[auto-provisioner] Started (will provision probes every 10 seconds)')

    try:
        if mdns:
            ip = mdns.start(port)
            print(f'[mDNS] Advertising http://temps-hub.local:{port} (ip {ip})')
        app.run(host=host, port=port, debug=False)
    finally:
        if provisioner:
            provisioner.stop()
        if mdns: mdns.stop()
        try: finder.stop()
        except Exception: pass

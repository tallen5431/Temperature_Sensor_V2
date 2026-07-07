import os
import socket
import secrets
import hmac
from pathlib import Path

import dash
from dash import Dash, html, Input, Output
import dash_bootstrap_components as dbc
from flask import Flask, send_file, request, Response
from werkzeug.utils import safe_join

from core.paths import BASE_DIR, get_csv_path, get_log_dir
from core.applog import setup_logging, HEALTH
from core.audit import AUDIT
from core.config import Config, ensure_config_file
from core.storage import ensure_csv
from core.mdns_advert import MdnsAdvert
from core.metrics import LATEST, render_prometheus
from core.mqtt_publish import MQTT
from core.version import __version__
from probe_discovery import ProbeDiscovery
from api.routes import create_api
from components.layout_main import build_layout, serve_page, register_all_callbacks
from components.help_modal import register_help_callbacks

CSV_FILE = get_csv_path()
CONFIG_FILE = Path(os.getenv("CONFIG_FILE") or (BASE_DIR / "config.json"))
EXAMPLE_CONFIG = BASE_DIR / "config.example.json"

log = setup_logging(get_log_dir())
AUDIT.configure(get_log_dir() / "audit.log")

# First run: seed config.json from the shipped example so a customer never sees
# someone else's data, then load layered config (+ config.local.json overrides).
ensure_config_file(CONFIG_FILE, EXAMPLE_CONFIG)
ensure_csv(CSV_FILE)
cfg = Config(CONFIG_FILE)

finder = ProbeDiscovery()
try:
    finder.start()
except Exception as e:
    log.warning("Probe discovery failed to start: %s", e)

server = Flask(__name__)


def _detect_lan_ip() -> str:
    """Best-effort LAN IP detection (no extra deps)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
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


def _resolve_token() -> str:
    """Unify the single device token used for BOTH ingest auth and provisioning.

    Precedence: SERVER_TOKEN env → existing config token → freshly generated.
    A generated token is persisted (config.local.json) and shown at startup so
    the maker can note it; because the provisioner pushes this same value to
    every probe, plug-and-play still works while the LAN is secure-by-default.
    """
    tok = (os.getenv("SERVER_TOKEN") or "").strip()
    if not tok:
        tok = (cfg.get("provision_token") or "").strip()
    if not tok:
        tok = secrets.token_urlsafe(18)
        cfg.set("provision_token", tok)
        log.info("Generated a new device token (saved to config.local.json).")
    else:
        # Keep the in-memory config in sync so the provisioner pushes this value.
        with cfg.lock:
            cfg.data["provision_token"] = tok
    return tok


DEVICE_TOKEN = _resolve_token()


def _resolve_ui_auth():
    """Optional HTTP Basic auth for the dashboard on a shared LAN.

    Credentials come from env (UI_USERNAME/UI_PASSWORD) or the `ui_auth` config
    block. Off unless enabled AND both a username and password are set.
    """
    ua = cfg.get("ui_auth", {}) or {}
    user = (os.getenv("UI_USERNAME") or ua.get("username") or "").strip()
    pw = os.getenv("UI_PASSWORD") or ua.get("password") or ""
    enabled = bool((ua.get("enabled") or os.getenv("UI_USERNAME")) and user and pw)
    return enabled, user, pw


UI_AUTH_ENABLED, UI_AUTH_USER, UI_AUTH_PW = _resolve_ui_auth()


@server.before_request
def _ui_auth_gate():
    """Guard the dashboard (and CSV download) when ui_auth is on.

    Exempts the machine-facing surfaces: /api/* (its own device-token auth),
    /metrics (Prometheus scraping), and static /assets so the login page styles.
    """
    if not UI_AUTH_ENABLED:
        return None
    p = request.path or "/"
    if p.startswith("/api/") or p == "/metrics" or p.startswith("/assets/"):
        return None
    auth = request.authorization
    if auth and hmac.compare_digest(auth.username or "", UI_AUTH_USER) \
            and hmac.compare_digest(auth.password or "", UI_AUTH_PW):
        return None
    return Response("Authentication required", 401,
                    {"WWW-Authenticate": 'Basic realm="ThermaHub"'})


api_bp = create_api(cfg, str(CSV_FILE), finder, _public_base, DEVICE_TOKEN)
server.register_blueprint(api_bp)

_branding = cfg.get("branding", {}) or {}
_primary = _branding.get("primary_color", "#00bcd4")

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG],
    server=server,
    suppress_callback_exceptions=True,
)
app.title = _branding.get("product_name", "ThermaHub")

# Inject the configurable brand color as a CSS variable (theme.css consumes it).
app.index_string = """<!DOCTYPE html>
<html>
  <head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <style>:root { --brand-color: __BRAND_COLOR__; }</style>
  </head>
  <body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
  </body>
</html>""".replace("__BRAND_COLOR__", _primary)

app.layout = build_layout(cfg)


# --- CSV Download Route (restricted to the log file only) ---
@server.route("/download/<path:filename>")
def download_csv(filename):
    """Serve ONLY the temperature log. The previous version served any file
    under the project directory (config.json with the token, all source)."""
    try:
        candidate = safe_join(str(BASE_DIR), filename)
        if not candidate:
            return "Not found", 404
        candidate = Path(candidate).resolve()
        if candidate != CSV_FILE.resolve() or not candidate.exists():
            return "Not found", 404
        AUDIT.record("data.export", detail="temperature_log.csv", actor=request.remote_addr or "?")
        return send_file(str(candidate), as_attachment=True, download_name="temperature_log.csv")
    except Exception:
        return "Not found", 404


# --- Prometheus metrics (homelab / Grafana integration) ---
@server.route("/metrics")
def metrics():
    if not (cfg.get("metrics", {}) or {}).get("enabled", True):
        return "metrics disabled", 404
    try:
        probes = len(finder.list_probes() or {})
    except Exception:
        probes = 0
    body = render_prometheus(HEALTH.snapshot(), LATEST.snapshot(), probes, __version__)
    return body, 200, {"Content-Type": "text/plain; version=0.0.4; charset=utf-8"}


@app.callback(Output("page-content", "children"), Input("url", "pathname"))
def display_page(pathname):
    return serve_page(pathname, cfg)


register_all_callbacks(app, finder, cfg)
register_help_callbacks(app)


def main():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    mdns = MdnsAdvert() if (os.getenv("MDNS_ENABLE", "1") not in ("0", "false", "False")) else None

    provisioner = None
    if cfg.get("auto_provision", True):
        from auto_provisioner import AutoProvisioner

        provisioner = AutoProvisioner(
            discovery=finder,
            public_base_func=_public_base,
            token=cfg.get("provision_token", ""),
            interval_ms=cfg.get("interval_sec", 5) * 1000,
            period_sec=10,
        )
        provisioner.start()
        log.info("Auto-provisioner started (provisioning discovered probes every 10s).")

    # Optional MQTT publishing (Home Assistant auto-discovery) — off by default.
    try:
        MQTT.start(cfg)
    except Exception as e:
        log.warning("MQTT start failed: %s", e)

    # Keep the log bounded (retention + downsampling) for 24/7 operation.
    retention = None
    if (cfg.get("retention", {}) or {}).get("enabled", True):
        from core.retention import RetentionManager
        retention = RetentionManager(CSV_FILE, cfg)
        retention.start()
        log.info("Retention manager started.")

    AUDIT.record("hub.start", detail=f"v{__version__} port={port}")
    lan_ip = _detect_lan_ip()
    try:
        if mdns:
            ip = mdns.start(port, instance_name=f"{app.title} Hub")
            log.info("mDNS advertising http://thermahub.local:%s (ip %s)", port, ip)

        product = _branding.get("product_name", "ThermaHub")
        print("\n" + "=" * 58)
        print(f"  {product} v{__version__} is running")
        print(f"  Open the dashboard:  http://localhost:{port}")
        print(f"  On your network:     http://{lan_ip}:{port}")
        print("=" * 58 + "\n")

        # Production WSGI server (waitress) instead of the Flask dev server,
        # which is single-threaded and not meant for 24/7 operation.
        try:
            from waitress import serve

            serve(server, host=host, port=port, threads=8)
        except ImportError:
            log.warning("waitress not installed; falling back to the Flask dev server.")
            app.run(host=host, port=port, debug=False)
    finally:
        if provisioner:
            provisioner.stop()
        if retention:
            retention.stop()
        try:
            MQTT.stop()
        except Exception:
            pass
        if mdns:
            mdns.stop()
        try:
            finder.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()

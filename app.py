import io
import logging
import os
import socket
import tempfile
from pathlib import Path

import dash_bootstrap_components as dbc
from dash import Dash, Input, Output
from flask import Flask, Response, request, send_file

from core.config import Config
from core.db import Database, migrate_csv_if_present
from core.logging_setup import configure_logging
from core.mdns_advert import MdnsAdvert
from probe_discovery import ProbeDiscovery
from api.routes import create_api
from components.layout_main import LAYOUT, serve_page, register_all_callbacks
from components.help_modal import register_help_callbacks

BASE_DIR = Path(__file__).resolve().parent
configure_logging(log_dir=str(BASE_DIR / "logs"))
log = logging.getLogger("hub.app")

DB_FILE = Path(os.getenv("DB_FILE", str(BASE_DIR / "temperature_log.db")))
LEGACY_CSV = Path(os.getenv("CSV_FILE", str(BASE_DIR / "temperature_log.csv")))
CONFIG_FILE = BASE_DIR / "config.json"
CONFIG_EXAMPLE = BASE_DIR / "config.example.json"

# Seed a fresh config from the shipped example on first run so customers never
# start from a file containing someone else's probe names / thresholds.
if not CONFIG_FILE.exists() and CONFIG_EXAMPLE.exists():
    try:
        CONFIG_FILE.write_text(CONFIG_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception as _e:
        log.warning("Could not seed config.json from example: %s", _e)

db = Database(DB_FILE)
_migrated = migrate_csv_if_present(db, LEGACY_CSV)
if _migrated:
    log.info("Imported %d reading(s) from legacy CSV into %s", _migrated, DB_FILE.name)

cfg = Config(CONFIG_FILE)
finder = ProbeDiscovery()
try:
    finder.start()
except Exception as _e:
    log.warning("Probe discovery failed to start: %s. Devices tab will be empty.", _e)

server = Flask(__name__)


def _detect_lan_ip() -> str:
    """Best-effort LAN IP detection (no extra deps)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No packets actually sent; picks the outbound interface.
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
    port = int(os.getenv("PORT", "8088"))
    return f"http://{_detect_lan_ip()}:{port}"


SERVER_TOKEN = os.getenv("SERVER_TOKEN", "") or cfg.get("provision_token", "")
api_bp = create_api(cfg, db, finder, _public_base, SERVER_TOKEN)
server.register_blueprint(api_bp)

app = Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], server=server,
           suppress_callback_exceptions=True)
app.title = "Temperature Hub"
app.layout = LAYOUT


WINDOW_SECONDS = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800, "30d": 2592000}


@server.route("/download/temperature_log.csv")
def download_csv():
    """Stream the log as CSV, optionally limited to a time window (?window=24h)."""
    window = WINDOW_SECONDS.get((request.args.get("window") or "all").strip())
    buf = io.StringIO()
    try:
        db.export_csv(buf, window_seconds=window)
    except Exception:
        log.exception("CSV export failed")
        return "Export failed", 500
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=temperature_log.csv"},
    )


@server.route("/download/backup.db")
def download_backup():
    """Download a consistent SQLite snapshot of the entire database."""
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        db.backup(tmp_path)
        return send_file(tmp_path, as_attachment=True, download_name="temperature_hub_backup.db")
    except Exception:
        log.exception("Backup failed")
        return "Backup failed", 500
    finally:
        # send_file streams before this runs; on most platforms the temp file can
        # be unlinked immediately after the response is built.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.callback(Output("page-content", "children"), Input("url", "pathname"))
def display_page(pathname):
    return serve_page(pathname)


register_all_callbacks(app, finder, cfg, db, public_base_func=_public_base, token=SERVER_TOKEN)
register_help_callbacks(app)


def _start_background_services(port: int):
    """Start mDNS, the auto-provisioner, and the alert monitor. Returns cleanup fn."""
    mdns = None
    if os.getenv("MDNS_ENABLE", "1") not in ("0", "false", "False"):
        mdns = MdnsAdvert()
        try:
            ip = mdns.start(port)
            log.info("mDNS advertising http://temps-hub.local:%s (ip %s)", port, ip)
        except Exception as e:
            log.warning("mDNS advertisement failed: %s", e)
            mdns = None

    provisioner = None
    if cfg.get("auto_provision", True):
        from provisioner import AutoProvisioner
        provisioner = AutoProvisioner(
            discovery=finder,
            public_base_func=_public_base,
            token=cfg.get("provision_token", ""),
            interval_ms=cfg.get("interval_sec", 5) * 1000,
            period_sec=10,
            cfg=cfg,
        )
        provisioner.start()
        log.info("Auto-provisioner started (every 10 s)")

    from alert_monitor import AlertMonitor
    monitor = AlertMonitor(db, cfg, period_sec=int(os.getenv("ALERT_CHECK_SEC", "30")))
    monitor.start()

    def _cleanup():
        monitor.stop()
        if provisioner:
            provisioner.stop()
        if mdns:
            mdns.stop()
        try:
            finder.stop()
        except Exception:
            pass

    return _cleanup


def main():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8088"))

    cleanup = _start_background_services(port)

    if os.getenv("OPEN_BROWSER", "0") == "1":
        import threading
        import webbrowser
        threading.Timer(2.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    try:
        try:
            from waitress import serve
            log.info("Serving on http://%s:%s (waitress)", host, port)
            serve(server, host=host, port=port, threads=8)
        except ImportError:
            log.warning("waitress not installed — using Flask dev server on %s:%s", host, port)
            app.run(host=host, port=port, debug=False)
    finally:
        cleanup()


if __name__ == "__main__":
    main()

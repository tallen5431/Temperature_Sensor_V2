import datetime
import hmac
import io
import logging
import os
import re
import socket
import sys
import tempfile
from pathlib import Path

import dash_bootstrap_components as dbc
from dash import Dash, Input, Output
from flask import Flask, Response, request

from core.config import Config
from core.db import Database, migrate_csv_if_present
from core.logging_setup import configure_logging
from core.mdns_advert import MdnsAdvert
from core.metrics import LATEST, render_prometheus
from core.applog import HEALTH
from core.audit import AUDIT
from core.mqtt_publish import MQTT
from core.version import HUB_VERSION, PRODUCT_NAME
from probe_discovery import ProbeDiscovery
from api.routes import create_api
from components.layout_main import LAYOUT, serve_page, register_all_callbacks
from components.help_modal import register_help_callbacks

_FROZEN = getattr(sys, "frozen", False)
# Read-only bundled resources (assets, config.example.json) live in the
# PyInstaller temp dir when frozen, or alongside the source in development.
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) if _FROZEN \
    else Path(__file__).resolve().parent


def _default_data_dir() -> Path:
    """Where the app keeps writable data (config.json, database, logs).

    In development: alongside the source.  When frozen: a per-user, writable
    location so a copy installed in a read-only place (Program Files,
    /Applications) works without admin rights.  A pre-existing "portable" install
    that already keeps its data next to the executable is honoured so updates
    don't strand old data.  ``DATA_DIR`` env always overrides.
    """
    if not _FROZEN:
        return Path(__file__).resolve().parent
    exe_dir = Path(sys.executable).resolve().parent
    if (exe_dir / "config.json").exists() or (exe_dir / "temperature_log.db").exists():
        return exe_dir  # existing portable install — keep using it
    app_name = "TempSensor"
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / app_name
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name
    base = os.getenv("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return Path(base) / app_name


DATA_DIR = Path(os.getenv("DATA_DIR", str(_default_data_dir())))
DATA_DIR.mkdir(parents=True, exist_ok=True)

configure_logging(log_dir=str(DATA_DIR / "logs"))
log = logging.getLogger("hub.app")

# Tamper-evident audit trail (config changes + data exports) — a B2B/procurement
# differentiator and a foundation for any future regulated (Part 11) path.
AUDIT.configure(DATA_DIR / "logs" / "audit.log")

DB_FILE = Path(os.getenv("DB_FILE", str(DATA_DIR / "temperature_log.db")))
LEGACY_CSV = Path(os.getenv("CSV_FILE", str(DATA_DIR / "temperature_log.csv")))
CONFIG_FILE = DATA_DIR / "config.json"
CONFIG_EXAMPLE = RESOURCE_DIR / "config.example.json"

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


def _resolve_ui_auth():
    """Optional HTTP Basic auth for the dashboard on a shared LAN.

    Credentials come from env (UI_USERNAME/UI_PASSWORD) or the ``ui_auth`` config
    block. Off unless enabled AND both a username and password are set.
    """
    ua = cfg.get("ui_auth", {}) or {}
    # str() guards against a numeric username/password in config.json (e.g. a PIN
    # entered as a bare number) — without it .strip()/hmac would crash at import.
    user = str(os.getenv("UI_USERNAME") or ua.get("username") or "").strip()
    pw = str(os.getenv("UI_PASSWORD") or ua.get("password") or "")
    enabled = bool((ua.get("enabled") or os.getenv("UI_USERNAME")) and user and pw)
    return enabled, user, pw


UI_AUTH_ENABLED, UI_AUTH_USER, UI_AUTH_PW = _resolve_ui_auth()


@server.before_request
def _ui_auth_gate():
    """Guard the dashboard (and downloads) when ui_auth is on.

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
                    {"WWW-Authenticate": f'Basic realm="{PRODUCT_NAME}"'})


# The Bootstrap/CYBORG theme is VENDORED locally at assets/bootstrap-cyborg.min.css
# (Dash auto-loads assets alphabetically, so it lands before theme.css) instead of
# pulling dbc.themes.CYBORG from a CDN — the hub is local-first and must render
# correctly with no internet (offline homelabs, air-gapped networks).
app = Dash(__name__, external_stylesheets=[], server=server,
           suppress_callback_exceptions=True, assets_folder=str(RESOURCE_DIR / "assets"))
app.title = PRODUCT_NAME
app.layout = LAYOUT


WINDOW_SECONDS = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800, "30d": 2592000}


@server.route("/metrics")
def metrics():
    """Prometheus text exposition for a homelab Prometheus + Grafana stack."""
    if not (cfg.get("metrics", {}) or {}).get("enabled", True):
        return "metrics disabled", 404
    try:
        probes = len(finder.list_probes() or {})
    except Exception:
        probes = 0
    body = render_prometheus(HEALTH.snapshot(), LATEST.snapshot(), probes, HUB_VERSION)
    return body, 200, {"Content-Type": "text/plain; version=0.0.4; charset=utf-8"}


def _parse_date_epoch(s, end_of_day=False):
    """Parse a hub-local ``YYYY-MM-DD`` (or full ISO) string to a unix epoch.
    A bare date maps to the start (or, for ``end_of_day``, the last second) of
    that day. Returns None for blank/invalid input so the filter is skipped."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = datetime.datetime.fromisoformat(s.replace("Z", ""))
        if len(s) == 10 and end_of_day:  # bare date -> inclusive end of day
            d = d.replace(hour=23, minute=59, second=59)
        return int(d.timestamp())
    except (ValueError, TypeError):
        return None


@server.route("/download/temperature_log.csv")
def download_csv():
    """Stream the log as CSV. Optional filters: ?window=24h, ?probe=<id>, and an
    absolute ?from=YYYY-MM-DD&to=YYYY-MM-DD range (inclusive, hub-local dates)."""
    args = request.args
    window = WINDOW_SECONDS.get((args.get("window") or "all").strip())
    probe = (args.get("probe") or "").strip() or None
    start_epoch = _parse_date_epoch(args.get("from"), end_of_day=False)
    end_epoch = _parse_date_epoch(args.get("to"), end_of_day=True)
    buf = io.StringIO()
    try:
        db.export_csv(buf, window_seconds=window, probe_id=probe,
                      start_epoch=start_epoch, end_epoch=end_epoch)
    except Exception:
        log.exception("CSV export failed")
        return "Export failed", 500
    fname = "temperature_log.csv"
    if probe:
        fname = "temperature_" + re.sub(r"[^A-Za-z0-9_.-]", "_", probe) + ".csv"
    AUDIT.record("data.export", detail=fname, actor=request.remote_addr or "?")
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


def _safe_unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _stream_file_then_delete(path, chunk_size=65536):
    """Yield a file's bytes, then delete it — the ``finally`` runs after the WSGI
    server has finished streaming (and closes the generator), so the temp file is
    always cleaned up, on every platform."""
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk
    finally:
        _safe_unlink(path)


@server.route("/download/backup.db")
def download_backup():
    """Download a consistent SQLite snapshot of the entire database."""
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        db.backup(tmp_path)
    except Exception:
        log.exception("Backup failed")
        _safe_unlink(tmp_path)
        return "Backup failed", 500
    AUDIT.record("data.export", detail="backup.db", actor=request.remote_addr or "?")
    return Response(
        _stream_file_then_delete(tmp_path),
        mimetype="application/x-sqlite3",
        headers={"Content-Disposition": "attachment; filename=temperature_hub_backup.db"},
    )


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
    monitor = AlertMonitor(db, cfg, period_sec=int(os.getenv("ALERT_CHECK_SEC", "30")),
                           discovery=finder)
    monitor.start()

    # Optional MQTT publishing (Home Assistant auto-discovery) — off unless the
    # `mqtt` config block enables it.
    try:
        MQTT.start(cfg)
    except Exception as e:
        log.warning("MQTT start failed: %s", e)

    AUDIT.record("hub.start", detail=f"v{HUB_VERSION} port={port}")

    def _cleanup():
        monitor.stop()
        try:
            MQTT.stop()
        except Exception:
            pass
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

    # Turn a SIGTERM (systemctl stop / docker stop / Windows service stop) into a
    # clean SystemExit so waitress returns and the `finally: cleanup()` below runs
    # — otherwise the default SIGTERM disposition kills the process instantly and
    # mDNS/MQTT/discovery threads never shut down cleanly. SIGINT already works.
    import signal
    try:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    except (ValueError, OSError):
        pass  # not the main thread (shouldn't happen) — best effort

    cleanup = _start_background_services(port)

    # A double-clicked desktop install should open the dashboard on its own; a
    # headless/service install can set OPEN_BROWSER=0. Dev default stays off.
    if os.getenv("OPEN_BROWSER", "1" if _FROZEN else "0") == "1":
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

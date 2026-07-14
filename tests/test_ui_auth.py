"""Tests for the optional dashboard Basic-auth gate. Mirrors the before_request
logic wired in app.py (kept isolated to avoid app import side effects)."""
import base64
import hmac

import pytest
from flask import Flask, request, Response


def _build(enabled, user="admin", pw="s3cret"):
    app = Flask(__name__)

    @app.before_request
    def gate():
        if not enabled:
            return None
        p = request.path or "/"
        if p.startswith("/api/") or p == "/metrics" or p.startswith("/assets/"):
            return None
        auth = request.authorization
        if auth and hmac.compare_digest(auth.username or "", user) \
                and hmac.compare_digest(auth.password or "", pw):
            return None
        return Response("Authentication required", 401,
                        {"WWW-Authenticate": 'Basic realm="Setpoint"'})

    @app.route("/")
    def home():
        return "dashboard"

    @app.route("/api/health")
    def health():
        return "ok"

    @app.route("/metrics")
    def metrics():
        return "metrics"

    @app.route("/download/temperature_log.csv")
    def dl():
        return "csv"

    return app.test_client()


def _basic(user, pw):
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_disabled_is_open():
    c = _build(enabled=False)
    assert c.get("/").status_code == 200


def test_enabled_blocks_dashboard_without_creds():
    c = _build(enabled=True)
    r = c.get("/")
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate", "").startswith("Basic")


def test_enabled_allows_with_correct_creds():
    c = _build(enabled=True)
    assert c.get("/", headers=_basic("admin", "s3cret")).status_code == 200
    assert c.get("/", headers=_basic("admin", "wrong")).status_code == 401


def test_download_is_protected_but_api_and_metrics_exempt():
    c = _build(enabled=True)
    assert c.get("/download/temperature_log.csv").status_code == 401  # sensitive data → gated
    assert c.get("/api/health").status_code == 200                    # own token auth
    assert c.get("/metrics").status_code == 200                       # Prometheus scrape

"""The Multi-site Settings card: the form -> config translation.

The card is the only way most operators will ever configure forwarding, so the
rules that keep a half-configured hub from looking like a working one live here.
"""
from components.settings_panel import build_upstream_config


def test_site_name_is_slugged_not_rejected():
    """"Atlanta Store #2" is what someone types. The wire protocol takes
    [A-Za-z0-9_-] only, so slug it rather than bouncing the operator."""
    out = build_upstream_config(True, "http://hq:8088", "Atlanta Store #2", "T", 30)
    assert out["site"] == "atlanta-store-2"


def test_blank_token_keeps_the_saved_one():
    """Same rule as the SMTP and MQTT passwords: the field renders empty, so a
    blank submit must not wipe the credential."""
    out = build_upstream_config(True, "http://hq:8088", "atl", "", 30,
                                existing={"token": "already-set"})
    assert out["token"] == "already-set"
    out2 = build_upstream_config(True, "http://hq:8088", "atl", "new-token", 30,
                                 existing={"token": "already-set"})
    assert out2["token"] == "new-token"


def test_keys_the_form_does_not_expose_survive():
    out = build_upstream_config(True, "http://hq:8088", "atl", "T", 30,
                                existing={"batch": 250, "token": "x"})
    assert out["batch"] == 250


def test_interval_is_floored_and_survives_junk():
    assert build_upstream_config(True, "http://h", "a", "T", 1)["interval_sec"] == 5
    assert build_upstream_config(True, "http://h", "a", "T", "")["interval_sec"] == 30
    assert build_upstream_config(True, "http://h", "a", "T", "abc")["interval_sec"] == 30


def test_trailing_slash_is_trimmed():
    """`ingest_url` appends /api/ingest_csv; a trailing slash would double it."""
    out = build_upstream_config(True, "http://hq:8088/", "atl", "T", 30)
    assert out["url"] == "http://hq:8088"


def test_disabling_keeps_the_settings_for_next_time():
    out = build_upstream_config(False, "http://hq:8088", "atl", "", 30,
                                existing={"token": "keep-me"})
    assert out["enabled"] is False
    assert out["url"] == "http://hq:8088" and out["site"] == "atl"
    assert out["token"] == "keep-me"


def test_diagnostics_reports_forwarding_without_leaking_the_token(tmp_path):
    """"Head office can't see my store" is the support ticket this answers, and
    the blob is meant to be pasted into an email — so state yes, secrets no."""
    import json
    from core.config import Config
    from core.db import Database
    from core.diagnostics import build_diagnostics

    cfg = Config(tmp_path / "c.json")
    db = Database(tmp_path / "t.db")
    cfg.update({"provision_token": "HUB-SECRET",
                "upstream": {"enabled": True, "url": "http://hq:8088",
                             "token": "HQ-SECRET", "site": "atlanta",
                             "interval_sec": 30}})

    class _F:
        def list_probes(self):
            return {}

    blob = build_diagnostics(cfg, db, _F(), "http://hub:8088", "0", "Setpoint")
    up = blob["upstream"]
    assert up["enabled"] is True and up["site"] == "atlanta"
    assert up["url"] == "http://hq:8088"
    assert "pending" in up and "last_error" in up
    text = json.dumps(blob)
    assert "HQ-SECRET" not in text and "HUB-SECRET" not in text


def test_diagnostics_stays_quiet_when_forwarding_is_off(tmp_path):
    from core.config import Config
    from core.db import Database
    from core.diagnostics import build_diagnostics

    cfg = Config(tmp_path / "c.json")
    db = Database(tmp_path / "t.db")

    class _F:
        def list_probes(self):
            return {}

    up = build_diagnostics(cfg, db, _F(), "http://hub:8088", "0", "Setpoint")["upstream"]
    assert up["enabled"] is False
    assert "pending" not in up      # no backlog line on a hub that forwards nothing


def test_site_report_is_read_only_and_never_creates_a_database(tmp_path):
    """The obvious one-liner (sqlite3.connect) CREATES an empty database when run
    from the wrong directory, so a mistyped path reports "no such table:
    readings" and leaves a junk file behind. The helper must refuse instead."""
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "scripts" / "site_report.py"
    missing = tmp_path / "nothing-here"
    missing.mkdir()
    r = subprocess.run([sys.executable, str(script), str(missing / "temperature_log.db")],
                       capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "DATA_DIR": str(missing)})
    assert r.returncode != 0
    assert not (missing / "temperature_log.db").exists(), "it created a database"


def test_site_report_separates_forwarded_from_local(tmp_path):
    import datetime
    import subprocess
    import sys
    from pathlib import Path
    from core.db import Database

    db = Database(tmp_path / "temperature_log.db")
    now = datetime.datetime.now()
    for pid, site in (("ATL-Walkin", "atlanta"), ("Direct-Probe", "")):
        for i in range(3):
            db.append((now - datetime.timedelta(seconds=3 - i)).isoformat(
                timespec="milliseconds"), 4.0, 39.2, pid, site=site)

    script = Path(__file__).resolve().parent.parent / "scripts" / "site_report.py"
    r = subprocess.run([sys.executable, str(script), str(tmp_path / "temperature_log.db")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "atlanta" in r.stdout and "(local)" in r.stdout
    # The line that diagnoses two hubs fighting over one probe.
    assert "posting directly to THIS hub" in r.stdout


def test_auto_provision_off_stops_the_provisioner_without_a_restart(tmp_path):
    """Two hubs on one LAN take turns claiming the same probes. Turning the
    switch off in Settings has to actually stop it — a flag only read at boot
    would save, change nothing, and read as a broken control."""
    from core.config import Config
    from provisioner import AutoProvisioner

    seen = []

    class _Discovery:
        def list_probes(self):
            seen.append(1)
            return {}

    cfg = Config(tmp_path / "c.json")
    p = AutoProvisioner(discovery=_Discovery(), public_base_func=lambda: "http://hub:8088",
                        token="T", cfg=cfg)

    p._run_cycle()
    assert seen, "a cycle with auto_provision defaulted on must scan"

    seen.clear()
    cfg.update({"auto_provision": False})
    p._run_cycle()
    assert seen == [], "auto_provision:false must stop the cycle, no restart needed"

    seen.clear()
    cfg.update({"auto_provision": True})
    p._run_cycle()
    assert seen, "turning it back on must resume, also without a restart"


# --- cleartext to head office ----------------------------------------------
# Multi-site exists so head office can see six stores, which usually means the
# traffic leaves the building. Over plain http that sends head office's DEVICE
# TOKEN — the credential that lets a caller write into its reading log — and
# every reading, in the clear. docs/MULTI_SITE.md says "use HTTPS in production,
# or a VPN"; the form where a store manager actually types the address said
# nothing, and they have no reason to have read that file.

from components.settings_panel import _upstream_is_cleartext_offsite as _cleartext


def test_plain_http_to_a_public_address_is_flagged():
    assert _cleartext("http://93.184.216.34/api/ingest_csv") is True


def test_plain_http_on_the_local_network_is_not_flagged():
    """The ordinary deployment, and exactly what the field's placeholder shows.
    Warning here would be noise, and noise trains people to ignore the warning
    that matters."""
    for url in ("http://192.168.1.50:8088", "http://10.0.0.5/api/ingest_csv",
                "http://172.16.4.4", "http://127.0.0.1:8088"):
        assert _cleartext(url) is False, url


def test_a_tailscale_address_is_not_flagged():
    """100.64/10 is an encrypted overlay the operator set up on purpose."""
    assert _cleartext("http://100.64.0.3:8088") is False


def test_https_is_never_flagged_wherever_it_points():
    assert _cleartext("https://hq.example.com") is False
    assert _cleartext("HTTPS://HQ.EXAMPLE.COM") is False


def test_an_unusable_address_produces_no_verdict():
    """Blank, junk, or a name that does not resolve: say nothing rather than
    guess. The URL-shape error above already covers genuinely invalid input."""
    for url in ("", None, "not a url", "ftp://hq.example.com"):
        assert _cleartext(url) is False, url


def test_the_warning_reaches_the_operator_on_save(tmp_path, monkeypatch):
    """The rule is only worth having if the save actually surfaces it."""
    import components.settings_panel as sp

    monkeypatch.setattr(sp, "_upstream_is_cleartext_offsite", lambda url: True)

    class _Fwd:
        def sync_now_detailed(self):
            return 3, "", True

        def status(self):
            return {"pending": 0}

    monkeypatch.setattr(sp, "FORWARDER", _Fwd())

    import dash
    from core.config import Config
    app = dash.Dash(__name__)
    app.layout = dash.html.Div()
    app.config.suppress_callback_exceptions = True
    cfg = Config(tmp_path / "c.json")
    sp.register_settings_callbacks(app, cfg)
    key, = [k for k in app.callback_map if "upstream-status.children" in k]
    fn = app.callback_map[key]["callback"].__wrapped__
    out, _site = fn(1, True, "http://hq.example.com", "atlanta", "tok", 60)
    assert out.color == "warning"
    text = str(out.children)
    assert "not encrypted" in text and "https" in text

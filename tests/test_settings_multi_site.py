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

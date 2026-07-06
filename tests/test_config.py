import json

from core.config import Config, redact_secrets, ensure_config_file, DEFAULTS


def test_defaults_present(tmp_path):
    cfg = Config(tmp_path / "config.json")
    assert cfg.get("interval_sec") == DEFAULTS["interval_sec"]
    assert "branding" in cfg.data
    assert cfg.get("branding")["product_name"] == "ThermaHub"


def test_deep_merge_keeps_nested_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"branding": {"product_name": "Acme Temp"}}), encoding="utf-8")
    cfg = Config(p)
    # Overridden key wins…
    assert cfg.get("branding")["product_name"] == "Acme Temp"
    # …but sibling defaults are preserved (not wiped by a shallow update).
    assert "support_url" in cfg.get("branding")


def test_corrupt_file_falls_back(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{not valid json", encoding="utf-8")
    cfg = Config(p)  # must not raise
    assert cfg.get("interval_sec") == DEFAULTS["interval_sec"]


def test_save_roundtrip_atomic(tmp_path):
    p = tmp_path / "config.json"
    cfg = Config(p)
    cfg.set("interval_sec", 42)
    # Persisted to the sidecar; a fresh load reflects it.
    cfg2 = Config(p)
    assert cfg2.get("interval_sec") == 42


def test_local_override_wins(tmp_path):
    base = tmp_path / "config.json"
    base.write_text(json.dumps({"interval_sec": 5}), encoding="utf-8")
    (tmp_path / "config.local.json").write_text(json.dumps({"interval_sec": 9}), encoding="utf-8")
    cfg = Config(base)
    assert cfg.get("interval_sec") == 9


def test_redact_secrets():
    red = redact_secrets({"provision_token": "abc", "nested": {"smtp_password": "p"}, "ok": 1})
    assert red["provision_token"] == "***set***"
    assert red["nested"]["smtp_password"] == "***set***"
    assert red["ok"] == 1


def test_ensure_config_file_seeds_from_example(tmp_path):
    example = tmp_path / "config.example.json"
    example.write_text(json.dumps({"interval_sec": 7}), encoding="utf-8")
    target = tmp_path / "config.json"
    ensure_config_file(target, example)
    assert target.exists()
    assert json.loads(target.read_text())["interval_sec"] == 7
    # Second call must not overwrite an existing config.
    target.write_text(json.dumps({"interval_sec": 99}), encoding="utf-8")
    ensure_config_file(target, example)
    assert json.loads(target.read_text())["interval_sec"] == 99

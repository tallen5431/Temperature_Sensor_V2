"""Tests for the Config store: atomic writes, corrupt-file recovery, and the
re-normalisation of programmatic writes (core.config)."""
import json

from core.config import Config


def test_roundtrip_persists_and_reloads(tmp_path):
    p = tmp_path / "config.json"
    c = Config(p)
    c.update({"probe_names": {"p1": "Fridge"}})
    # A fresh instance reads back the persisted value.
    assert Config(p).get("probe_names") == {"p1": "Fridge"}


def test_save_is_atomic_no_tmp_left_behind(tmp_path):
    p = tmp_path / "config.json"
    c = Config(p)
    c.set("retention_days", 7)
    # The temp file used for the atomic rename must not linger.
    assert not (tmp_path / "config.json.tmp").exists()
    assert json.loads(p.read_text())["retention_days"] == 7


def test_corrupt_config_is_preserved_not_silently_discarded(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ this is not valid json", encoding="utf-8")
    c = Config(p)  # must not raise
    # The unparseable file is moved aside for recovery rather than overwritten.
    assert (tmp_path / "config.json.corrupt").exists()
    # The hub still comes up on defaults.
    assert c.get("interval_sec") == 5


def test_programmatic_write_is_renormalised(tmp_path):
    # A POST /api/config-style write with a numeric ui_auth username must be
    # coerced on the way in, so it can't brick the next startup.
    c = Config(tmp_path / "config.json")
    c.update({"ui_auth": {"enabled": True, "username": 7, "password": 7}})
    assert c.get("ui_auth")["username"] == "7"


def test_secret_file_permissions(tmp_path):
    import os
    import stat
    import sys
    if sys.platform == "win32":
        return  # POSIX mode bits don't apply
    p = tmp_path / "config.json"
    Config(p).set("provision_token", "s3cret")
    mode = stat.S_IMODE(os.stat(p).st_mode)
    assert mode == 0o600

"""Tests for the Config store: atomic writes, corrupt-file recovery, and the
re-normalisation of programmatic writes (core.config)."""
import json
import os
import stat

import pytest

from core.config import Config


def test_roundtrip_persists_and_reloads(tmp_path):
    p = tmp_path / "config.json"
    c = Config(p)
    c.update({"probe_names": {"p1": "Fridge"}})
    # A fresh instance reads back the persisted value.
    assert Config(p).get("probe_names") == {"p1": "Fridge"}


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
def test_config_file_is_owner_only(tmp_path):
    # Regression: config.json holds provisioning/SMTP/webhook secrets, so it must
    # be owner-only (0o600) after a save, and an already-loose file must be
    # re-secured on load (not left world-readable across restarts).
    p = tmp_path / "config.json"
    Config(p).update({"provision_token": "sekret"})
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    os.chmod(p, 0o644)
    Config(p)
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


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


def test_get_returns_copy_not_live_reference(tmp_path):
    # Mutating a get() result must not leak into stored config without update().
    c = Config(tmp_path / "config.json")
    c.update({"probe_names": {"p1": "Fridge"}})
    d = c.get("probe_names")
    d["p1"] = "TAMPERED"
    d["p2"] = "Injected"
    assert c.get("probe_names") == {"p1": "Fridge"}  # unchanged


def test_to_dict_returns_deep_snapshot_without_changing_live_or_persisted_data(tmp_path):
    p = tmp_path / "config.json"
    c = Config(p)
    original = {
        "nested_snapshot_test": {
            "metadata": {"location": "walk-in"},
            "channels": ["email", {"name": "webhook", "enabled": True}],
        }
    }
    c.update(original)

    snapshot = c.to_dict()
    snapshot["nested_snapshot_test"]["metadata"]["location"] = "TAMPERED"
    snapshot["nested_snapshot_test"]["channels"].append("injected")
    snapshot["nested_snapshot_test"]["channels"][1]["enabled"] = False

    assert c.to_dict()["nested_snapshot_test"] == original["nested_snapshot_test"]
    assert json.loads(p.read_text(encoding="utf-8"))["nested_snapshot_test"] == original["nested_snapshot_test"]


def test_concurrent_mutate_and_save_does_not_race(tmp_path):
    # Reproduces the get()->mutate->update() vs save()->json.dumps race: with the
    # live-reference bug this raised "dict changed size during iteration".
    import threading
    c = Config(tmp_path / "config.json")
    c.update({"probe_names": {f"p{i}": str(i) for i in range(50)}})
    errors = []

    def writer(n):
        try:
            for i in range(40):
                names = c.get("probe_names")
                names[f"w{n}_{i}"] = "x"
                c.update({"probe_names": names})
        except Exception as e:  # pragma: no cover - failure path
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors


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

"""Tests for demo data seeding/clearing (core.demo)."""
import datetime

from core.config import Config
from core.db import Database
from core.demo import load_demo_data, clear_demo_data, has_demo_data, DEMO_PREFIX


def test_demo_load_and_clear(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    assert has_demo_data(db) is False
    rows = load_demo_data(db, cfg, hours=6, step_min=5)
    assert rows == 2 * (6 * 60 // 5)          # two demo probes
    assert db.count() == rows
    assert has_demo_data(db) is True
    assert any(k.startswith(DEMO_PREFIX) for k in cfg.get("probe_names", {}))
    assert all(k.startswith(DEMO_PREFIX) for k in db.stats_per_probe())

    removed = clear_demo_data(db, cfg)
    assert removed == rows
    assert db.count() == 0
    assert has_demo_data(db) is False
    assert not any(k.startswith(DEMO_PREFIX) for k in cfg.get("probe_names", {}))


def test_has_demo_data_falls_back_without_fast_helper(tmp_path):
    # has_demo_data prefers the O(log N) Database.has_probe_prefix probe, but an
    # older Database without it (or one that errors) must still answer via the
    # legacy per-probe scan rather than reporting "no demo data" incorrectly.
    class _LegacyDB(Database):
        def has_probe_prefix(self, prefix):
            raise RuntimeError("helper unavailable")

    db = _LegacyDB(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    assert has_demo_data(db) is False
    load_demo_data(db, cfg, hours=1, step_min=30)
    assert has_demo_data(db) is True


def test_clear_demo_preserves_real_probes(tmp_path):
    db = Database(tmp_path / "d.db")
    cfg = Config(tmp_path / "c.json")
    db.append(datetime.datetime.now().isoformat(timespec="seconds"), 20.0, 68.0, "REAL-1")
    cfg.update({"probe_names": {"REAL-1": "Kitchen"}})
    load_demo_data(db, cfg, hours=2)
    clear_demo_data(db, cfg)
    assert db.count() == 1                      # the real probe's reading survives
    assert cfg.get("probe_names", {}).get("REAL-1") == "Kitchen"
    assert has_demo_data(db) is False

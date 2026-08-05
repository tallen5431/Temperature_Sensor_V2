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


def test_demo_probes_arrive_with_the_alarm_range_their_role_implies(tmp_path):
    """The demo is what a prospect is shown first. It used to seed two probes
    reading normally with no limits on either, so the Devices cards said "Alarm
    range: not set" and — once the hub stopped calling an unwatched probe OK —
    the dashboard opened on two grey "no alarm set" badges. The demo showed a
    thermometer, not the product."""
    from core.db import Database
    from core.config import Config
    from core.demo import load_demo_data, _DEMO_PROBES

    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    load_demo_data(db, cfg)
    thresholds = cfg.get("alert_thresholds", {}) or {}
    for pid in _DEMO_PROBES:
        band = thresholds.get(pid) or {}
        assert band.get("min") is not None and band.get("max") is not None, \
            f"{pid} has no alarm range, so the demo shows nothing being checked"


def test_the_demo_data_stays_inside_the_demo_limits(tmp_path):
    """A sine wave wider than its own band poked over the limit twice a cycle.
    The chart drew the crossing, and no event was recorded against it — the alert
    monitor only ever evaluates the newest reading — so the demo's most visible
    moment was the product appearing to miss an excursion."""
    from core.db import Database
    from core.config import Config
    from core.demo import load_demo_data, _DEMO_PROBES

    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    load_demo_data(db, cfg)
    thresholds = cfg.get("alert_thresholds", {})
    for pid in _DEMO_PROBES:
        temps = [r[0] for r in db._conn().execute(
            "SELECT temperature_c FROM readings WHERE probe_id=?", (pid,))]
        band = thresholds[pid]
        assert band["min"] < min(temps) and max(temps) < band["max"], (
            f"{pid} swings {min(temps):.2f}..{max(temps):.2f} outside its own "
            f"demo band [{band['min']}, {band['max']}]")


def test_clearing_the_demo_takes_the_demo_thresholds_with_it(tmp_path):
    from core.db import Database
    from core.config import Config
    from core.demo import load_demo_data, clear_demo_data

    db, cfg = Database(tmp_path / "d.db"), Config(tmp_path / "c.json")
    cfg.update({"alert_thresholds": {"real-probe": {"min": -22.0, "max": -15.0}}})
    load_demo_data(db, cfg)
    clear_demo_data(db, cfg)
    left = cfg.get("alert_thresholds", {}) or {}
    assert not [p for p in left if str(p).startswith("DEMO-")]
    assert "real-probe" in left, "clearing the demo removed a real probe's limits"

import json

from core.audit import AuditLog, GENESIS, _hash_entry


def test_chain_appends_and_verifies(tmp_path):
    a = AuditLog()
    a.configure(tmp_path / "audit.log")
    a.record("hub.start", "v2.0.0")
    a.record("config.update", "calibration")
    a.record("data.export", "temperature_log.csv", actor="192.168.1.5")
    res = a.verify()
    assert res["ok"] and res["intact"]
    assert res["entries"] == 3


def test_first_entry_links_to_genesis(tmp_path):
    p = tmp_path / "audit.log"
    a = AuditLog()
    a.configure(p)
    a.record("hub.start")
    first = json.loads(p.read_text().splitlines()[0])
    assert first["prev"] == GENESIS
    assert first["hash"] == _hash_entry(first)


def test_tampering_is_detected(tmp_path):
    p = tmp_path / "audit.log"
    a = AuditLog()
    a.configure(p)
    a.record("config.update", "settings")
    a.record("config.update", "notifications")
    a.record("data.export", "log.csv")

    # Silently edit a past entry's detail (leaving its hash) — chain must break.
    lines = p.read_text().splitlines()
    e = json.loads(lines[1])
    e["detail"] = "calibration"  # forged
    lines[1] = json.dumps(e)
    p.write_text("\n".join(lines) + "\n")

    res = a.verify()
    assert res["intact"] is False
    assert res["broken_at"] == 1


def test_configure_resumes_chain(tmp_path):
    p = tmp_path / "audit.log"
    a1 = AuditLog()
    a1.configure(p)
    a1.record("hub.start")
    # A fresh instance pointed at the same file continues the chain intact.
    a2 = AuditLog()
    a2.configure(p)
    a2.record("config.update", "settings")
    assert a2.verify()["intact"] is True


def test_tail_truncation_is_detected(tmp_path):
    # Deleting trailing entries leaves an internally-consistent (shorter) chain
    # that linkage-only verification can't catch — the anchor must flag it.
    p = tmp_path / "audit.log"
    a = AuditLog()
    a.configure(p)
    a.record("hub.start")
    a.record("config.update", "settings")
    a.record("data.export", "log.csv")
    assert a.verify()["intact"] is True

    # Chop the last line (simulate `head -n -1 audit.log`).
    lines = p.read_text().splitlines()
    p.write_text("\n".join(lines[:-1]) + "\n")

    res = a.verify()
    assert res["intact"] is False
    assert "anchor" in res.get("reason", "").lower()


def test_truncation_detected_across_restart(tmp_path):
    p = tmp_path / "audit.log"
    a = AuditLog()
    a.configure(p)
    a.record("hub.start")
    a.record("config.update", "settings")
    # Truncate while "down", then a fresh instance configures against the anchor.
    lines = p.read_text().splitlines()
    p.write_text(lines[0] + "\n")
    a2 = AuditLog()
    a2.configure(p)
    assert a2.verify()["intact"] is False


def test_record_is_noop_before_configure():
    a = AuditLog()
    a.record("x")  # no path set → must not raise
    assert a.verify()["entries"] == 0


def test_detail_never_contains_values(tmp_path):
    # config.update logs only key names, never values (which may be secrets).
    from core.config import Config
    from core.audit import AUDIT
    AUDIT.configure(tmp_path / "audit.log")
    cfg = Config(tmp_path / "config.json")
    cfg.update({"provision_token": "supersecret", "interval_sec": 9})
    text = (tmp_path / "audit.log").read_text()
    assert "supersecret" not in text
    assert "provision_token" in text  # the key name is recorded

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


def test_an_entry_is_durable_before_the_anchor_advances(tmp_path, monkeypatch):
    """The truncation check rests on "the log is at least as far along as the
    anchor". Both writes land in the page cache, and the kernel may write them
    back in either order — so without an fsync between them, a power cut that
    landed the anchor and lost the entry would make the hub report its own audit
    trail as possibly truncated, permanently, over an unclean shutdown that
    tampered with nothing. This record exists to be believed; crying wolf here
    is the expensive failure."""
    import core.audit as audit_mod

    order = []
    real_fsync = audit_mod.os.fsync
    monkeypatch.setattr(audit_mod.os, "fsync",
                        lambda fd: order.append("fsync") or real_fsync(fd))

    log = audit_mod.AuditLog()
    real_write_tip = log._write_tip
    monkeypatch.setattr(log, "_write_tip",
                        lambda: order.append("tip") or real_write_tip())

    log.configure(tmp_path / "audit.log")
    log.record("config.update", detail="interval_sec")

    assert order, "the entry was written without ever reaching the disk"
    assert order.index("fsync") < order.index("tip"), (
        f"the anchor advanced before the entry was durable: {order}")


def test_an_unclean_shutdown_that_lost_nothing_verifies_clean(tmp_path):
    """The end-to-end shape of the same guarantee: write entries, drop the
    in-memory state as a restart would, and re-read. No tamper report."""
    import core.audit as audit_mod

    path = tmp_path / "audit.log"
    first = audit_mod.AuditLog()
    first.configure(path)
    for i in range(3):
        first.record("data.export", detail=f"export-{i}.csv")

    reopened = audit_mod.AuditLog()
    reopened.configure(path)
    result = reopened.verify()
    assert result["intact"] is True, result
    assert result["entries"] == 3
    assert result.get("anchored") is True

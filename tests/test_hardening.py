"""Regression tests for ingest/export hardening (probe-id bounding + CSV
formula-injection safety) restored after the branch reconciliation."""
import io

from conftest import make_client
from core.storage import sanitize_probe_id
from core.db import Database, _csv_safe
from core.metrics import LATEST


def test_sanitize_probe_id_keeps_valid_and_strips_junk():
    assert sanitize_probe_id("ThermaProbe-9A3F2C") == "ThermaProbe-9A3F2C"
    assert sanitize_probe_id("=cmd|' /C calc'!A0") == "cmdCcalcA0"  # =|'/! and space stripped
    assert sanitize_probe_id("a" * 100) == "a" * 32               # length capped
    assert sanitize_probe_id("") == ""
    assert sanitize_probe_id(None) == ""
    junk = sanitize_probe_id("bad id!<script>")
    assert all(c.isalnum() or c in "_-" for c in junk)


def test_ingest_sanitizes_probe_id(tmp_db):
    client, _ = make_client(tmp_db, token="")
    r = client.post("/api/ingest", json={"temperature_c": 20, "probe_id": "=bad id!"})
    assert r.status_code == 200
    snap = LATEST.snapshot()
    assert "=bad id!" not in snap          # raw malicious id never stored
    assert snap.get("badid", {}).get("temp_c") == 20.0  # sanitized token kept


def test_csv_safe_neutralises_formulas():
    assert _csv_safe("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert _csv_safe("+1") == "'+1"
    assert _csv_safe("-1") == "'-1"
    assert _csv_safe("@x") == "'@x"
    assert _csv_safe("ThermaProbe-9A3F2C") == "ThermaProbe-9A3F2C"  # normal untouched
    assert _csv_safe(None) == ""


def test_export_csv_is_formula_injection_safe(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    # A formula-like value that somehow reached the store must export as text.
    db.append("=2+2", 20.0, 68.0, probe_id="=cmd")
    buf = io.StringIO()
    db.export_csv(buf)
    row = buf.getvalue().splitlines()[1]
    assert row.startswith("'=2+2")
    assert "'=cmd" in row

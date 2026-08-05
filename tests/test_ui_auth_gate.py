"""The optional dashboard login (`ui_auth`), which had no test at all.

app.py is the one production module the suite never imported — 280 statements
at 0% — and the `before_request` gate inside it is the only thing standing
between a shared office LAN and a full SQLite snapshot of every reading.
Whatever else is untested there, this part should not be.

Run in a subprocess: `UI_AUTH_ENABLED` is resolved at import time, and importing
app.py builds a Database and registers every Dash callback, so importing it into
the main test session would both fix the credentials for every later test and
leave that state behind.
"""
import json
import subprocess
import sys
import textwrap

# Paths that must stay reachable without credentials even when the gate is on.
# SECURITY.md calls these "operational endpoints (unauthenticated by design)":
# Prometheus has to scrape, and support has to be able to read a health snapshot.
EXEMPT = ["/metrics", "/api/health", "/api/diagnostics", "/api/probes"]
# Everything a browser reaches, including the FULL database snapshot.
GATED = ["/", "/download/temperature_log.csv", "/download/backup.db"]

_PROBE = textwrap.dedent("""
    import json, os, sys
    os.environ["MDNS_ENABLE"] = "0"
    os.environ["DATA_DIR"] = sys.argv[1]
    os.environ["UI_USERNAME"] = "op"
    os.environ["UI_PASSWORD"] = "s3cr3t"
    sys.path.insert(0, sys.argv[2])
    import app
    c = app.server.test_client()
    out = {"enabled": app.UI_AUTH_ENABLED, "anon": {}, "good": {}, "bad": {}}
    import base64
    def hdr(u, p):
        raw = base64.b64encode(f"{u}:{p}".encode()).decode()
        return {"Authorization": "Basic " + raw}
    for path in json.loads(sys.argv[3]):
        out["anon"][path] = c.get(path).status_code
        out["good"][path] = c.get(path, headers=hdr("op", "s3cr3t")).status_code
        out["bad"][path] = c.get(path, headers=hdr("op", "wrong")).status_code
    print("@@" + json.dumps(out))
""")


def _probe(tmp_path, paths):
    script = tmp_path / "probe.py"
    script.write_text(_PROBE, encoding="utf-8")
    repo = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
    res = subprocess.run(
        [sys.executable, str(script), str(tmp_path), repo, json.dumps(paths)],
        capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, res.stderr[-3000:]
    line = [ln for ln in res.stdout.splitlines() if ln.startswith("@@")]
    assert line, res.stdout[-2000:] + res.stderr[-2000:]
    return json.loads(line[0][2:])


def test_gate_challenges_the_browser_surfaces_including_the_db_backup(tmp_path):
    got = _probe(tmp_path, GATED)
    assert got["enabled"] is True
    for path in GATED:
        assert got["anon"][path] == 401, f"{path} served without credentials"
        assert got["bad"][path] == 401, f"{path} accepted a wrong password"
        assert got["good"][path] == 200, f"{path} rejected valid credentials"


def test_operational_endpoints_stay_open_by_design(tmp_path):
    """Not an oversight — SECURITY.md documents these as deliberately open so
    Prometheus can scrape and support tools can read a health snapshot. Pinned
    so the trade-off has to be changed on purpose, not drifted into."""
    got = _probe(tmp_path, EXEMPT)
    for path in EXEMPT:
        assert got["anon"][path] == 200, f"{path} now requires auth — intended?"

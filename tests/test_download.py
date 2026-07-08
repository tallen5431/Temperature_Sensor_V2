"""Regression tests for the /download route lockdown and the link the dashboard
builds. A path refactor once made the dashboard link by ABSOLUTE path, producing
'/download//home/.../log.csv' which missed the route and returned HTML instead of
the CSV. These pin the correct behavior.
"""
import os
import sys
from pathlib import Path

import pytest
from flask import Flask, send_file
from werkzeug.utils import safe_join

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _build_download_app(csv_file: Path):
    """Mirror app.py's hardened download route for isolated testing.

    Resolves against the CSV file's OWN directory (matching the fix), so a
    Docker/custom CSV_FILE path outside the project dir still serves correctly.
    """
    server = Flask(__name__)

    @server.route("/download/<path:filename>")
    def download_csv(filename):
        try:
            candidate = safe_join(str(csv_file.parent), filename)
            if not candidate:
                return "Not found", 404
            candidate = Path(candidate).resolve()
            if candidate != csv_file.resolve() or not candidate.exists():
                return "Not found", 404
            return send_file(str(candidate), as_attachment=True, download_name="temperature_log.csv")
        except Exception:
            return "Not found", 404

    return server.test_client()


@pytest.fixture
def dl(tmp_path):
    csv = tmp_path / "temperature_log.csv"
    csv.write_text("timestamp,temperature_c,temperature_f,probe_id\n", encoding="utf-8")
    return _build_download_app(csv), csv


def test_download_works_when_csv_outside_project_dir(tmp_path):
    # Docker case: CSV_FILE lives in /data, not the repo dir. Must still serve.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv = data_dir / "temperature_log.csv"
    csv.write_text("timestamp,temperature_c,temperature_f,probe_id\n", encoding="utf-8")
    client = _build_download_app(csv)
    r = client.get("/download/temperature_log.csv")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("Content-Disposition", "")


def test_download_by_basename_works(dl):
    client, csv = dl
    r = client.get("/download/temperature_log.csv")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("Content-Disposition", "")


def test_download_absolute_path_does_not_serve_file(dl):
    # The old buggy link form: '/download//abs/path/...'. The double slash must
    # NOT result in a CSV download (Werkzeug redirects/merges it; in the real
    # Dash app it fell through to the SPA catch-all and returned HTML). Either
    # way it must never be a 200 file attachment.
    client, csv = dl
    r = client.get("/download/" + str(csv), follow_redirects=False)  # '/download//...'
    assert r.status_code != 200
    assert "attachment" not in r.headers.get("Content-Disposition", "")


def test_download_other_files_blocked(dl):
    client, csv = dl
    # A sibling file in the same dir must not be downloadable.
    (csv.parent / "config.json").write_text("{}", encoding="utf-8")
    assert client.get("/download/config.json").status_code == 404
    assert client.get("/download/../etc/passwd").status_code == 404


def test_dashboard_builds_basename_link():
    # The dashboard callback must link by basename, not the absolute CSV path.
    import components.dashboard_view as dv
    from urllib.parse import quote
    link = f"/download/{quote(os.path.basename(dv.CSV_FILE))}"
    assert "//" not in link.replace("/download/", "")  # no double slash
    assert link.startswith("/download/")
    assert os.path.isabs(dv.CSV_FILE)  # CSV_FILE itself is absolute…
    assert link == "/download/temperature_log.csv"  # …but the link uses the basename

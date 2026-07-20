"""Regression guard for the Dash callback graph.

Two callbacks that write the SAME ``Output`` without ``allow_duplicate=True``
make the Dash browser renderer reject the *entire* callback graph on page load:
the dashboard renders its static shell (navbar + footer) but no callback ever
fires — ``page-content`` stays empty and the footer is frozen on
"Status: starting…". Crucially, the Flask/Dash server still *registers* both
callbacks without raising, so every server-side and ``build_dashboard`` unit
test passes; only loading the full graph in a browser surfaces it.

That is exactly the bug that shipped in the v2.4.0 dashboard (a duplicated
clock-format callback block). This test reconstructs the app's real callback
graph and fails if any output is claimed by more than one callback without
opting into duplicates — catching the whole class without needing a browser.
"""
from collections import Counter

from dash import Dash, Input, Output

from components.layout_main import LAYOUT, serve_page, register_all_callbacks
from components.help_modal import register_help_callbacks
from core.config import Config
from core.db import Database


class _FakeFinder:
    def list_probes(self):
        return {}


def _build_app(tmp_path):
    """Build the app and register callbacks exactly as ``app.py`` does."""
    app = Dash(__name__, suppress_callback_exceptions=True)
    app.layout = LAYOUT
    cfg = Config(tmp_path / "config.json")
    db = Database(tmp_path / "temperature_log.db")
    finder = _FakeFinder()

    @app.callback(Output("page-content", "children"), Input("url", "pathname"))
    def _display_page(pathname):
        return serve_page(pathname)

    register_all_callbacks(app, finder, cfg, db,
                           public_base_func=lambda: "http://hub:8088", token="")
    register_help_callbacks(app)
    return app


def _iter_outputs(callback_list):
    """Yield ``(base_output, allows_duplicate)`` for every output in the graph.

    Dash serialises a multi-output callback as ``..a.x...b.y..`` and a single
    output as ``a.x``; an ``allow_duplicate`` output carries an ``@<hash>``
    suffix. Mirrors how the renderer reads ``/_dash-dependencies``.
    """
    for cb in callback_list:
        out = cb.get("output", "") or ""
        parts = out.split("...") if out.startswith("..") else [out]
        for part in parts:
            part = part.strip(".")
            if not part:
                continue
            base = part.split("@")[0]
            yield base, ("@" in part)


def test_no_duplicate_callback_outputs(tmp_path):
    app = _build_app(tmp_path)
    claimed = Counter()
    for base, allows_dup in _iter_outputs(app._callback_list):
        if not allows_dup:
            claimed[base] += 1
    dupes = {out: n for out, n in claimed.items() if n > 1}
    assert not dupes, (
        "Duplicate Dash callback outputs (without allow_duplicate) freeze the "
        f"whole dashboard on load — each of these is claimed by >1 callback: {dupes}"
    )

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


# --- Every callback must point at a component that exists --------------------
_ROUTES = ["/", "/devices", "/settings", "/diagnostics", "/help"]


def _walk(node):
    """Yield every component in a Dash tree, following children and lists."""
    if isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk(item)
        return
    if not hasattr(node, "_prop_names"):
        return  # a plain string / number leaf
    yield node
    yield from _walk(getattr(node, "children", None))


def _layout_ids():
    """Every string id rendered by the app shell plus any page it can serve.

    Includes the two fragments a callback (not the layout) puts on the page —
    the first-run onboarding card and the demo-data banner — since their buttons
    are wired to real callbacks and would otherwise read as dangling.
    """
    from components.dashboard_view import _onboarding_card, _demo_alert

    ids = set()
    trees = [LAYOUT] + [serve_page(r) for r in _ROUTES]
    trees += [_onboarding_card(), _demo_alert()]
    for tree in trees:
        for comp in _walk(tree):
            cid = getattr(comp, "id", None)
            if isinstance(cid, str):
                ids.add(cid)
    return ids


def test_every_callback_target_exists_in_a_page(tmp_path):
    """A callback wired to an id no page renders is silently dead.

    ``suppress_callback_exceptions=True`` is required here — the pages are served
    per route, so Dash cannot validate them at startup — and its cost is that
    renaming or removing a component id breaks the callback that reads it with no
    error anywhere: the control simply stops doing anything. This walks every
    route's real component tree and fails on the first dangling reference, which
    is what makes a Settings/Dashboard re-layout safe to do.

    Pattern-matching (dict) ids are skipped: they match by shape at runtime and
    have no single literal id to look for.
    """
    app = _build_app(tmp_path)
    known = _layout_ids()
    dangling = set()
    for cb in app._callback_list:
        refs = [dep["id"] for dep in (cb.get("inputs", []) + cb.get("state", []))]
        refs += [part.strip(".").split("@")[0].rsplit(".", 1)[0]
                 for part in ((cb.get("output", "") or "").split("...")
                              if (cb.get("output") or "").startswith("..")
                              else [cb.get("output", "") or ""])
                 if part.strip(".")]
        for ref in refs:
            # Dict ids serialise to a JSON object string ({"index":...}); they
            # match by shape at runtime, so there is nothing literal to look up.
            if not isinstance(ref, str) or not ref or ref.startswith("{"):
                continue
            if ref not in known:
                dangling.add(ref)
    assert not dangling, (
        "These callback ids are not rendered by any page, so those callbacks can "
        f"never fire (or can never write anywhere): {sorted(dangling)}"
    )

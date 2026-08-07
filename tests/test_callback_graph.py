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


def _ids_in(tree):
    """The string ids a single tree renders, in order (duplicates kept)."""
    return [comp.id for comp in _walk(tree) if isinstance(getattr(comp, "id", None), str)]


def test_no_page_repeats_an_id_the_app_shell_already_mounts():
    """Two live components with the same id blank the dashboard on Back.

    Dash validates ``app.layout`` for duplicate ids at startup, but the shell's
    ``page-content`` is empty there — the pages arrive later from a callback, so
    nothing ever checks the *combination*. That gap shipped: ``DevicesLayout``
    carried its own ``dcc.Store(id='temp-unit-store')`` from back when the store
    lived in ``DashboardLayout`` and only one page mounted it at a time. The store
    was later moved to the app shell, which mounts it on EVERY page, and the copy
    on Devices quietly became a second component with the same id.

    The renderer keys components by id, so opening Devices pointed that id at the
    copy inside ``page-content``. Navigating away tore the subtree down and took
    the entry with it — leaving the shell's store, still mounted, unreachable:
    "a nonexistent object was used in an `Input`". ``update_dashboard`` takes
    ``temp-unit-store`` as an Input, so it stopped firing and the dashboard
    rendered blank until the reader hit reload by hand.

    Nothing else caught it. Every server-side test passes (the callbacks are fine,
    they just never fire), ``test_every_callback_target_exists_in_a_page`` unions
    all the routes into one set so a duplicate reads as present, and the page
    still looked correct while Devices was open, because both stores were
    ``storage_type='local'`` and read the same browser value.
    """
    shell = _ids_in(LAYOUT)
    assert "page-content" in shell, "the shell no longer hosts pages — update this test"
    for route in _ROUTES:
        page = _ids_in(serve_page(route))
        clashes = sorted(set(shell) & set(page))
        assert not clashes, (
            f"{route} re-declares {clashes}, which the app shell already mounts on "
            f"every page. Two live components with one id make that id unreachable "
            f"once the page unmounts — delete the copy on the page and read the "
            f"shell's.")
        repeats = sorted({i for i in page if page.count(i) > 1})
        assert not repeats, f"{route} renders {repeats} more than once"


# --- callbacks that mount with a page, and callbacks that don't --------------

def _shell_ids():
    return {c.id for c in _walk(LAYOUT) if isinstance(getattr(c, "id", None), str)}


def _page_ids(route):
    return {c.id for c in _walk(serve_page(route)) if isinstance(getattr(c, "id", None), str)}


def _output_ids(cb):
    out = cb.get("output", "") or ""
    parts = out.split("...") if out.startswith("..") else [out]
    return {p.strip(".").split("@")[0].rsplit(".", 1)[0] for p in parts if p.strip(".")}


def test_a_callback_that_draws_on_a_page_has_an_input_on_that_page(tmp_path):
    """Otherwise it never runs when the page mounts, and the page shows a stale default.

    dash-renderer queues a newly-mounted subtree's callbacks by INPUT. A callback
    whose every Input lives in the app shell — which never remounts — is therefore
    never queued when a page appears, no matter what it outputs. It fires only if
    one of those shell Inputs later changes.

    Both unit/clock button rows were in exactly that state: their only Input was
    the preference store in the shell. On a reload, ``dcc.Store`` restored the
    saved value silently (no change, so no callback), and the buttons kept the
    layout's hard-coded °C / 24h while the gauge, chart, probe cards and stats all
    showed the saved unit. °F everywhere with °C lit up reads as "it didn't keep
    my setting". Both now also take the dashboard's own 5 s tick as an Input,
    purely so they mount with the page.

    A pure-shell callback (the router, the help modal) is fine — it draws in the
    shell too, and the shell is always there. Only mixing the two is a bug.
    """
    app = _build_app(tmp_path)
    shell = _shell_ids()
    stranded = []
    for cb in app._callback_list:
        inputs = {i["id"] for i in cb.get("inputs", []) if isinstance(i.get("id"), str)}
        if not inputs or not inputs <= shell:
            continue  # has an on-page Input, so it mounts with the page
        outputs = _output_ids(cb)
        for route in _ROUTES:
            on_page = outputs & _page_ids(route)
            if on_page:
                stranded.append(f"{route}: {sorted(on_page)} <- inputs {sorted(inputs)}")
    assert not stranded, (
        "These callbacks draw on a page but every Input they have lives in the app "
        "shell, so they are never queued when that page mounts and whatever they "
        "draw keeps the layout's hard-coded default:\n  " + "\n  ".join(stranded))


def test_clicked_id_ignores_a_button_nobody_pressed():
    """``prevent_initial_call=True`` does not cover a button inserted by a callback.

    Every page here arrives via the ``page-content`` callback, so its buttons are
    added to the layout after the initial render — and Dash fires the callbacks of
    a newly-added subtree with every ``n_clicks`` still None. Reading
    ``triggered[0]["prop_id"]`` there names the first button in the Input list as
    though it had been pressed.

    That is not hypothetical: it shipped on both preference toggles. Every single
    page load fired them and wrote "celsius" and "24h" over whatever the reader had
    chosen, so picking °F lasted until the next navigation. It also disabled the
    locale defaults completely — those only write while the stores are still empty,
    and by the time they ran the toggles had already filled them in, so a US
    customer never got °F or a 12-hour clock either.
    """
    from components.dashboard_view import clicked_id

    mount = [{"prop_id": "unit-celsius.n_clicks", "value": None},
             {"prop_id": "unit-fahrenheit.n_clicks", "value": None},
             {"prop_id": "unit-kelvin.n_clicks", "value": None}]
    assert clicked_id(mount) == "", "a mount-time fire must not read as a click"
    assert clicked_id([]) == "" and clicked_id(None) == ""
    assert clicked_id([{"prop_id": "unit-kelvin.n_clicks", "value": 0}]) == "", \
        "n_clicks 0 is 'rendered, never pressed'"

    assert clicked_id([{"prop_id": "unit-fahrenheit.n_clicks", "value": 1}]) == "unit-fahrenheit"
    assert clicked_id([{"prop_id": "unit-kelvin.n_clicks", "value": 7}]) == "unit-kelvin"
    # A real click arriving in the same batch as the mount fire still wins.
    assert clicked_id(mount + [{"prop_id": "unit-fahrenheit.n_clicks", "value": 1}]) \
        == "unit-fahrenheit"


def test_the_preference_toggles_use_it(tmp_path):
    """Both toggles write a store that persists to the browser, so a spurious fire
    does not just misdraw a frame — it overwrites a saved choice. Neither may go
    back to reading triggered[0] directly."""
    import re
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "components" / "dashboard_view.py").read_text(encoding="utf-8")
    for name in ("toggle_unit", "toggle_clock_format"):
        body = src[src.index(f"def {name}("):]
        body = body[:body.index("@app.callback", 1) if "@app.callback" in body[1:] else 400]
        assert "clicked_id(" in body, f"{name} must go through clicked_id()"
        assert not re.search(r'triggered\[0\]\["prop_id"\]', body), \
            f"{name} reads triggered[0] directly again — that is the bug"


def test_dashboard_callback_outputs_match_what_it_returns():
    """update_dashboard composes build_dashboard's tuple with two extra values,
    and short-circuits an unchanged tick with a HARD-CODED ``(no_update,) * N``.
    Both numbers have to track the Output list, and neither is checked by Python:
    adding an Output 500s the whole callback at runtime with a
    SchemaLengthValidationError, which is how the stat-colour change first
    shipped. Dash also matches Outputs to the returned tuple POSITIONALLY, so an
    Output inserted in the middle silently receives a neighbour's value."""
    import re, pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "components" / "dashboard_view.py").read_text(encoding="utf-8")

    block = src[src.index('Output("temp-gauge", "figure")'):]
    block = block[:block.index("def update_dashboard")]
    n_outputs = len(re.findall(r"Output\(", block))

    m = re.search(r"return \(no_update,\) \* (\d+)", src)
    assert m, "the no_update short-circuit changed shape — update this test"
    assert int(m.group(1)) == n_outputs, (
        f"update_dashboard declares {n_outputs} Outputs but its unchanged-tick "
        f"path returns {m.group(1)} no_updates — every 5 s tick would 500.")

    # build_dashboard supplies all but the final two (logging class + render sig).
    assert "(*out, logging_class, sig)" in src
    from core.db import Database
    from core.config import Config
    import tempfile, pathlib as pl
    with tempfile.TemporaryDirectory() as d:
        from components.dashboard_view import build_dashboard

        class _F:
            def list_probes(self): return {}
        out = build_dashboard(Database(pl.Path(d) / "t.db"), Config(pl.Path(d) / "c.json"),
                              _F(), "24h", "celsius")
    assert len(out) + 2 == n_outputs, (
        f"build_dashboard returns {len(out)} values; the callback needs "
        f"{n_outputs - 2} before it appends logging_class and sig.")


def test_no_callback_returns_the_wrong_number_of_no_updates():
    """A `(no_update,) * N` literal has to track its callback's Output count, and
    nothing in Python checks it: the mismatch surfaces only at runtime, as a Dash
    SchemaLengthValidationError that 500s the whole callback. It shipped once on
    update_dashboard when three Outputs were added and the literal stayed at 16,
    so every 5 s tick failed. This checks every multi-output callback, not just
    that one."""
    import re, pathlib
    root = pathlib.Path(__file__).resolve().parent.parent / "components"
    problems = []
    checked = 0
    for f in sorted(root.glob("*.py")):
        src = f.read_text(encoding="utf-8")
        for m in re.finditer(r"@app\.callback\((.*?)\)\s*\n\s*def (\w+)\(", src, re.S):
            head, fname = m.group(1), m.group(2)
            n_out = len(re.findall(r"Output\(", head))
            if n_out < 2:
                continue
            checked += 1
            nxt = src.find("@app.callback", m.end())
            body = src[m.end(): nxt if nxt > 0 else len(src)]
            for lit in re.finditer(r"\(no_update,\)\s*\*\s*(\d+)", body):
                if int(lit.group(1)) != n_out:
                    problems.append(
                        f"{f.name}:{fname} declares {n_out} Outputs but returns "
                        f"{lit.group(1)} no_updates")
    assert checked > 10, f"only inspected {checked} callbacks — did the regex rot?"
    assert not problems, "\n".join(problems)

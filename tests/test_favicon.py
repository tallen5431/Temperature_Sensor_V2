"""The browser tab was showing Dash's own bundled favicon — a Plotly logo — on
every page of the hub, because ``assets/favicon.ico`` did not exist.

Dash's asset pipeline resolves ``{%favicon%}`` in ``index_string`` by looking for
``favicon.ico`` in the app's assets folder FIRST and falling back to the copy it
ships with the library (``dash/favicon.ico``) only when that lookup fails. Nobody
had ever added one, so every visitor's browser tab — and every bookmark, and every
"Add to Home Screen" — carried a competitor's logo instead of Setpoint's.

Parsed by hand rather than with an image library: Pillow (used to *build* the
file) is not a project dependency, and importing it here would make this test
skip or fail on any environment that lacks it. The ICO container format is six
bytes of header plus a fixed-size directory, cheap enough to read without one.
"""
import pathlib
import struct

import dash

REPO = pathlib.Path(__file__).resolve().parent.parent
FAVICON = REPO / "assets" / "favicon.ico"


def _ico_sizes(data: bytes):
    """``[(width, height), ...]`` declared in an ICO's directory.

    A directory entry stores width/height as single bytes where ``0`` means 256
    (the format predates needing anything larger), per the ICONDIR/ICONDIRENTRY
    layout Windows has used since 3.0 and every browser still reads.
    """
    assert data[:4] == b"\x00\x00\x01\x00", "not an ICO file (bad magic)"
    (count,) = struct.unpack_from("<H", data, 4)
    sizes = []
    for i in range(count):
        w, h = data[6 + i * 16], data[7 + i * 16]
        sizes.append((w or 256, h or 256))
    return sizes


def test_favicon_ico_exists():
    assert FAVICON.exists(), (
        "assets/favicon.ico is missing, so Dash falls back to its own bundled "
        "favicon.ico (a Plotly logo) — every browser tab shows the wrong brand.")


def test_favicon_ico_is_well_formed_and_has_the_tab_size():
    data = FAVICON.read_bytes()
    sizes = _ico_sizes(data)
    assert sizes, "the ICO directory is empty"
    assert (16, 16) in sizes, (
        "no 16x16 entry — that is the size a browser tab actually renders, and "
        "the one most likely to look wrong or blank if it is missing")


def test_favicon_ico_is_not_the_plotly_default():
    """The literal regression this file exists to catch: the app falling silently
    back to Dash's own icon because ours went missing or got reverted."""
    dash_default = pathlib.Path(dash.__file__).resolve().parent / "favicon.ico"
    assert dash_default.exists(), "Dash's bundled favicon moved — update this test"
    assert FAVICON.read_bytes() != dash_default.read_bytes(), (
        "assets/favicon.ico is byte-identical to Dash's bundled Plotly icon")


def test_the_index_template_still_asks_dash_for_a_favicon():
    """{%favicon%} is the token Dash's index-string templating replaces with the
    <link rel="icon"> tag, and is what makes assets/favicon.ico reachable at all.
    Removing it silently reverts to Dash's own <link>, pointed at its own file."""
    src = (REPO / "app.py").read_text(encoding="utf-8")
    assert "{%favicon%}" in src

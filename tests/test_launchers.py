"""Start.bat and Start.sh — the first thing a customer ever runs.

Nothing in the suite touched them, and all three of these had shipped:

1. ``%errorlevel%`` inside a parenthesised block. cmd.exe substitutes it when it
   PARSES the block, so the test reads the exit code from before the block ran.
   Start.bat probed for the ``py`` launcher, then used two fallback blocks for
   ``python3`` and ``python`` — both testing ``py``'s already-failed exit code.
   On any Windows machine without the py launcher (a Microsoft Store or Anaconda
   install), the launcher reported "Python 3.9 or newer is required but was not
   found" on a machine with Python installed, and quit.

2. Box-drawing characters in a UTF-8 .bat, with no ``chcp``. A default Windows
   console is on code page 437 or 1252, so the welcome banner rendered as
   mojibake — the customer's first impression of the product.

3. LF line endings in a .bat. cmd parses parenthesised blocks and ``for /f``
   inconsistently without CRLF, which is most of that file.

Plus the shell side: ``set -e`` aborted Start.sh the instant app.py exited
non-zero, so the "Press Enter to exit" that was there to keep a crash on screen
never ran — the window closed on the error message it existed to show.
"""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
BATS = sorted(p for p in REPO.rglob("*.bat") if ".git" not in p.parts)


@pytest.mark.parametrize("path", BATS, ids=lambda p: p.name)
def test_no_parse_time_errorlevel_inside_a_block(path):
    """``%errorlevel%`` is only safe at statement level. Inside ``( ... )`` use
    ``if errorlevel N`` or ``!errorlevel!`` — both evaluate at run time."""
    text = path.read_text(encoding="utf-8", errors="replace")
    depth, bad = 0, []
    for lineno, line in enumerate(text.splitlines(), 1):
        if depth > 0 and "%errorlevel%" in line.lower():
            bad.append(f"{path.name}:{lineno}: {line.strip()}")
        depth = max(0, depth + line.count("(") - line.count(")"))
    assert not bad, (
        "%errorlevel% is expanded when cmd parses the enclosing block, so it "
        "holds the exit code from BEFORE the block ran:\n  " + "\n  ".join(bad))


@pytest.mark.parametrize("path", BATS, ids=lambda p: p.name)
def test_a_batch_file_is_ascii_or_sets_a_code_page(path):
    """Either stay inside ASCII (renders on every console) or switch the code
    page explicitly. Silently emitting UTF-8 to a code-page-437 console is what
    turned the welcome banner into mojibake."""
    text = path.read_text(encoding="utf-8", errors="replace")
    non_ascii = sorted({c for c in text if ord(c) > 127})
    if non_ascii and not re.search(r"^\s*chcp\s+65001", text, re.M | re.I):
        pytest.fail(
            f"{path.name} prints non-ASCII {non_ascii!r} with no `chcp 65001`. "
            f"A default Windows console renders those as mojibake.")


@pytest.mark.parametrize("path", BATS, ids=lambda p: p.name)
def test_a_batch_file_uses_crlf(path):
    raw = path.read_bytes()
    lf = raw.count(b"\n")
    crlf = raw.count(b"\r\n")
    assert lf and crlf == lf, (
        f"{path.name} has {lf - crlf} LF-only line(s). cmd.exe parses "
        f"parenthesised blocks and `for /f` inconsistently without CRLF — see "
        f".gitattributes, which pins this so a checkout cannot undo it.")


@pytest.mark.parametrize("path", BATS, ids=lambda p: p.name)
def test_every_parenthesis_in_a_batch_file_closes(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    depth = 0
    for line in text.splitlines():
        depth = max(0, depth + line.count("(") - line.count(")"))
    assert depth == 0, f"{path.name} ends inside an unclosed ( block"


# --- the shell side --------------------------------------------------------

def test_start_sh_keeps_a_crash_on_screen():
    """`set -e` + a trailing pause is a contradiction: the pause is unreachable
    in exactly the case it exists for."""
    text = (REPO / "Start.sh").read_text(encoding="utf-8")
    assert "set -e" in text, "the strict-mode preamble went away — update this test"
    launch = re.search(r'^\s*"\$PYTHON_EXE"\s+"\$APP_DIR/app\.py".*$', text, re.M)
    assert launch, "could not find the line that starts the hub"
    assert "|| exit_code=" in launch.group(0), (
        "app.py is launched bare under `set -e`, so a non-zero exit aborts the "
        "script and the error handling below it never runs")


def test_start_sh_exports_the_port_it_advertises():
    """The banner printed $PORT while app.py read its own default from the
    environment — two independent 8088s that agreed only by coincidence."""
    text = (REPO / "Start.sh").read_text(encoding="utf-8")
    assert re.search(r"^\s*export PORT=", text, re.M), \
        "PORT is set as a shell variable, so app.py never receives it"
    assert re.search(r"^\s*export HOST=", text, re.M)


def test_the_advertised_port_is_the_one_app_py_defaults_to():
    """Both launchers print a URL before the hub has bound anything. If that
    number and app.py's default ever diverge, the browser opens on nothing."""
    app = (REPO / "app.py").read_text(encoding="utf-8")
    default = re.search(r'os\.getenv\("PORT",\s*"(\d+)"\)', app)
    assert default, "app.py's PORT default changed shape — update this test"
    port = default.group(1)
    for name in ("Start.sh", "Start.bat"):
        text = (REPO / name).read_text(encoding="utf-8")
        assert re.search(rf"(?:PORT[:=]-?|PORT=)\"?{port}\"?", text), \
            f"{name} does not default to app.py's port ({port})"


def test_gitattributes_pins_the_line_endings_that_matter():
    """A .bat needs CRLF and a .sh needs LF, on every developer's machine
    regardless of their core.autocrlf. Only .gitattributes can guarantee that."""
    ga = (REPO / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"^\*\.bat\s+text\s+eol=crlf", ga, re.M)
    assert re.search(r"^\*\.sh\s+text\s+eol=lf", ga, re.M)

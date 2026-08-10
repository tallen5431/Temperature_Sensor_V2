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


def _discovery_probe(tmp_path, good_candidate=None):
    """Run only Start.sh's interpreter hunt, against a PATH we control.

    PATH holds nothing but our shims plus the handful of externals the script's
    own preamble needs — otherwise the machine's real python3.x is found and the
    scenario never arises.
    """
    import shutil
    import subprocess
    import sys

    shim = tmp_path / "bin"
    shim.mkdir()
    for tool in ("dirname", "env", "cat", "awk"):
        found = shutil.which(tool)
        if found:
            (shim / tool).symlink_to(found)
    (shim / "python3").write_text("#!/bin/sh\nexit 127\n", encoding="utf-8")
    (shim / "python3").chmod(0o755)
    if good_candidate:
        (shim / good_candidate).write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
        (shim / good_candidate).chmod(0o755)

    # Stop before the venv build: this is about discovery, not the install.
    script = (REPO / "Start.sh").read_text(encoding="utf-8")
    head = script.split("# \u2500\u2500 2. Create / reuse virtual environment")[0]
    probe = tmp_path / "probe.sh"
    probe.write_text(head + '\necho "PICKED=$PYTHON_BIN"\n', encoding="utf-8")
    probe.chmod(0o755)

    bash = shutil.which("bash")
    assert bash, "bash is required to run Start.sh"
    return subprocess.run([bash, str(probe)], capture_output=True, text=True,
                          timeout=120, cwd=str(tmp_path), input="",
                          env={"PATH": str(shim), "HOME": str(tmp_path)})


def test_start_sh_survives_a_broken_python3_on_path(tmp_path):
    """`set -e` + a bare `VAR=$(cmd)` assignment aborts on a non-zero exit.

    The hunt tries `python3` first, so ONE broken candidate on PATH -- a
    Microsoft Store stub, a dangling pyenv shim, a half-removed install --
    killed the launcher inside the loop, before it could try python3.12 and
    before the "Python 3.9 or newer is required" banner that exists to explain
    exactly this. The customer double-clicks and the window closes.
    """
    res = _discovery_probe(tmp_path, good_candidate="python3.12")
    assert "PICKED=python3.12" in res.stdout, (
        f"discovery aborted instead of falling through.\n"
        f"rc={res.returncode}\nstdout={res.stdout}\nstderr={res.stderr}")


def test_start_sh_still_reports_when_no_python_is_usable(tmp_path):
    """The other half: with nothing usable it must reach the banner, not die."""
    res = _discovery_probe(tmp_path)
    assert "Python 3.9 or newer is required" in res.stdout, (
        f"the launcher died silently instead of explaining itself.\n"
        f"rc={res.returncode}\nstdout={res.stdout}\nstderr={res.stderr}")


def test_start_sh_does_not_cache_an_uncomputable_requirements_hash(tmp_path):
    """The `|| REQ_HASH=""` that stops `set -e` aborting must not then be
    written to the stamp file: caching an empty hash makes the next comparison
    succeed against itself, so the dependency check is disabled for the life of
    the venv — the exact opposite of the fallback's intent.

    Runs the real requirements block with sha256sum/shasum/awk absent, twice,
    and asserts it installs both times.
    """
    import shutil
    import subprocess

    shim = tmp_path / "bin"
    shim.mkdir()
    for tool in ("dirname", "cat", "env", "mkdir", "ln"):
        found = shutil.which(tool)
        if found:
            (shim / tool).symlink_to(found)
    # A python that answers the version probe and no-ops `-m pip install`.
    (shim / "python3").write_text(
        '#!/bin/sh\n'
        'case "$*" in\n'
        '  *"version_info >= (3,9)"*) echo True ;;\n'
        '  *"sys.version_info[:2]"*)  echo 3.12 ;;\n'
        '  *venv*) mkdir -p "$3/bin" && ln -sf "$0" "$3/bin/python" ;;\n'
        '  *"pip install"*) echo "PIP-INSTALL" ;;\n'
        'esac\n', encoding="utf-8")
    (shim / "python3").chmod(0o755)

    app = tmp_path / "app"
    app.mkdir()
    (app / "requirements.txt").write_text("dash\n", encoding="utf-8")
    script = (REPO / "Start.sh").read_text(encoding="utf-8")
    head = script.split("# ── 3. Resolve host / port")[0]
    (app / "probe.sh").write_text(head, encoding="utf-8")
    (app / "probe.sh").chmod(0o755)

    bash = shutil.which("bash")
    env = {"PATH": str(shim), "HOME": str(tmp_path)}
    runs = [subprocess.run([bash, str(app / "probe.sh")], capture_output=True,
                           text=True, timeout=120, cwd=str(app), input="", env=env)
            for _ in range(2)]
    assert "PIP-INSTALL" in runs[0].stdout, runs[0].stdout + runs[0].stderr
    assert "PIP-INSTALL" in runs[1].stdout, (
        "the second launch skipped the install — an empty hash was cached as a "
        f"match, so dependencies can never be refreshed:\n{runs[1].stdout}")

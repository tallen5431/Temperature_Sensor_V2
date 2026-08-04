"""Runs the Cloudflare Pages Functions test suite (tests/functions_test.mjs).

The Functions are JavaScript running on Cloudflare's edge, so pytest cannot
exercise them directly and there is no JS test runner in this repo — adding one
for three files is not worth the dependency. Instead the JS suite is a plain
Node script that exits non-zero on failure, and this test shells out to it so a
regression shows up in the normal `pytest` run rather than in production.

Skipped (not failed) when Node is unavailable, so the Python suite still passes
on a machine without it.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FUNCTIONS = sorted((REPO / "functions" / "api").glob("*.js"))

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed; JS Functions suite skipped")


@pytest.mark.parametrize("js", FUNCTIONS, ids=lambda p: p.name)
def test_function_parses(js):
    """A syntax error in a Function is a hard 500 on the live site."""
    r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, f"{js.name} failed to parse:\n{r.stderr}"


def test_functions_behaviour_suite():
    r = subprocess.run(["node", str(REPO / "tests" / "functions_test.mjs")],
                       capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, "Pages Functions suite failed:\n" + r.stdout + r.stderr
    assert "ALL PASS" in r.stdout

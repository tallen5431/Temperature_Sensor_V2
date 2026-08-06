"""Everything here must still run on the oldest Python this project supports.

`pyproject.toml` says `requires-python = ">=3.9"`, `Start.sh`/`Start.bat` hunt
for 3.9 or newer, and CI runs a 3.9 matrix leg. But development happens on a
newer interpreter, so anything the newer one accepts looks fine locally and only
fails on that leg — which is exactly what happened: a version-drift guard that
did `import tomllib` (stdlib from 3.11) passed here and turned CI red, with the
failure 700 tests deep in the log.

These catch both halves of that locally:

  * **syntax** newer than the floor, via `ast.parse(..., feature_version=...)` —
    a `match` statement, `except*`, and so on;
  * **stdlib modules** that did not exist at the floor.

The floor is read from `pyproject.toml` rather than written here, so raising the
supported version relaxes these automatically instead of leaving them lying.
"""
import ast
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

# Stdlib modules newer than 3.9, with the version that introduced them. Short and
# curated on purpose: this is the list of things a contributor on a modern
# interpreter plausibly reaches for without noticing, not a census of the stdlib.
NEWER_THAN_3_9 = {
    "tomllib": (3, 11),        # the one that actually broke CI
    "graphlib": (3, 9),        # 3.9 — listed so nobody re-adds it as a mistake
    "zoneinfo": (3, 9),
    "asyncio.taskgroups": (3, 11),
}

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"}


def python_floor():
    """The minimum interpreter this project claims to support."""
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'requires-python\s*=\s*">=\s*(\d+)\.(\d+)"', text)
    assert m, "requires-python is not declared in pyproject.toml — update this test"
    return int(m.group(1)), int(m.group(2))


def source_files():
    for path in REPO.rglob("*.py"):
        if SKIP_DIRS & set(path.parts):
            continue
        yield path


def test_the_floor_is_declared_and_matches_what_ci_runs():
    """Three places name it — pyproject, the CI matrix, and the launchers. A
    floor that only one of them believes in is not a floor."""
    floor = python_floor()
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    versions = re.findall(r'"(\d+\.\d+)"', ci)
    assert f"{floor[0]}.{floor[1]}" in versions, (
        f"pyproject requires-python >={floor[0]}.{floor[1]} but the CI matrix "
        f"tests {versions} — nothing is checking the version customers may run")


@pytest.mark.parametrize(
    "path", sorted(source_files(), key=str),
    ids=lambda p: str(p.relative_to(REPO)))
def test_every_module_parses_on_the_oldest_supported_python(path):
    floor = python_floor()
    source = path.read_text(encoding="utf-8")
    try:
        ast.parse(source, filename=str(path), feature_version=floor)
    except SyntaxError as e:
        pytest.fail(
            f"{path.relative_to(REPO)}:{e.lineno} uses syntax newer than Python "
            f"{floor[0]}.{floor[1]}, which pyproject.toml says this project "
            f"supports and CI tests: {e.msg}")


def test_no_module_imports_a_stdlib_module_newer_than_the_floor():
    floor = python_floor()
    offenders = []
    for path in source_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue                       # the parametrised test above owns this
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module]
            for name in names:
                added = NEWER_THAN_3_9.get(name)
                if added and added > floor:
                    offenders.append(
                        f"{path.relative_to(REPO)}:{node.lineno}: `{name}` is "
                        f"Python {added[0]}.{added[1]}+, floor is "
                        f"{floor[0]}.{floor[1]}")
    assert not offenders, (
        "these import stdlib modules that do not exist on the oldest supported "
        "Python, so they pass locally and fail on the CI matrix leg:\n  "
        + "\n  ".join(sorted(offenders)))

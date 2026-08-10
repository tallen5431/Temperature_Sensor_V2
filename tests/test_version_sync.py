"""Version strings that must agree, enforced rather than remembered.

`flash/README.md` and `flash/build_merged_bin.sh` both instruct "keep
manifest.json's version in sync with FW_VERSION". Prose does not enforce
anything: CHANGELOG records this exact drift being fixed once already, and it
had drifted again (manifest 2.8.2 against firmware 2.9.0) by the time this test
was written.

It matters because ESP Web Tools reads `manifest.json` to decide whether an
already-flashed probe needs updating. A stale version means a probe running old
firmware is told it is current, and the browser installer's own page advertises
a version nobody is shipping.
"""
import json
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


def firmware_version() -> str:
    ino = (REPO / "esp32_temp_probe" / "esp32_temp_probe.ino").read_text(encoding="utf-8")
    m = re.search(r'FW_VERSION\s*=\s*"([^"]+)"', ino)
    assert m, "FW_VERSION not found in the .ino — did the declaration change shape?"
    return m.group(1)


def test_flash_manifest_matches_firmware_version():
    manifest = json.loads((REPO / "flash" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == firmware_version(), (
        "flash/manifest.json is what ESP Web Tools compares against a probe's "
        "installed version; stale means 'no update needed' for a probe that "
        "needs one.")


def test_installer_page_matches_firmware_version():
    html = (REPO / "flash" / "index.html").read_text(encoding="utf-8")
    shown = re.findall(r'<span class="ver">firmware v([^<]+)</span>', html)
    assert shown, "the installer page no longer advertises a version — update this test"
    assert set(shown) == {firmware_version()}, f"page advertises {shown}"


def test_hub_version_is_a_plain_release_number():
    """The hub versions independently of the firmware — they are separate
    artifacts on separate release cadences, so they are NOT compared here. This
    only pins the shape, so a stray suffix or an accidental edit is caught."""
    from core.version import HUB_VERSION, PRODUCT_NAME, __version__
    assert re.fullmatch(r"\d+\.\d+\.\d+", HUB_VERSION), HUB_VERSION
    assert __version__ == HUB_VERSION
    assert PRODUCT_NAME == "Setpoint"


def _project_version_by_hand(text: str) -> str:
    """Read `version` out of pyproject.toml's ``[project]`` table, without a TOML
    parser.

    `tomllib` is stdlib only from Python 3.11, and this project supports 3.9
    (`requires-python = ">=3.9"`, and CI runs a 3.9 leg). Importing it
    unconditionally turned a version-drift guard into a hard failure on the older
    matrix leg. Adding `tomli` as a dev dependency for one lookup is more than
    this needs — pyproject.toml is read as plain text elsewhere in this file
    too — and :func:`test_the_hand_parser_agrees_with_a_real_toml_parser` checks
    this against `tomllib` wherever one is available, so the shortcut is verified
    rather than assumed.
    """
    table = re.split(r"^\[", text, flags=re.M)
    for chunk in table:
        if chunk.startswith("project]"):
            m = re.search(r'^\s*version\s*=\s*"([^"]+)"', chunk, re.M)
            if m:
                return m.group(1)
    raise AssertionError("no version found in pyproject.toml's [project] table")


def test_packaging_version_matches_the_hub_version():
    """pyproject.toml declares the version a second time, for the wheel. Same
    shape as the flash manifest, which drifted twice while a note asked people
    to keep it in sync -- so this is enforced instead of asked for."""
    from core.version import HUB_VERSION
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert _project_version_by_hand(text) == HUB_VERSION, \
        "bump pyproject.toml's version alongside core/version.py"


def test_the_hand_parser_agrees_with_a_real_toml_parser():
    """Runs wherever tomllib exists (3.11+), which on CI is the newer matrix leg.
    Keeps the 3.9-compatible shortcut above honest instead of hoping it is."""
    tomllib = pytest.importorskip("tomllib", reason="stdlib TOML is 3.11+")
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert _project_version_by_hand(text) == tomllib.loads(text)["project"]["version"]


def test_pytest_is_configured_in_exactly_one_place():
    """pytest.ini takes precedence over pyproject.toml, so a
    [tool.pytest.ini_options] block there applies to nothing. One existed, with a
    filterwarnings setting that had never taken effect."""
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.pytest.ini_options]" not in pyproject, \
        "pytest.ini wins — put pytest settings there, not in pyproject.toml"
    assert (REPO / "pytest.ini").exists()


def test_the_developer_file_map_covers_every_core_module():
    """docs/DEVELOPING.md's file map is what a contributor navigates by, so a
    module missing from it is invisible. It had silently rotted: six core
    modules were absent (including the whole multi-site forwarder), and three
    listed files -- auto_provision.py, auto_provisioner.py, core/retention.py --
    did not exist under those names, or at all."""
    doc = (REPO / "docs" / "DEVELOPING.md").read_text(encoding="utf-8")
    listed = set()
    for m in re.finditer(r"^\|\s*`([^`]+)`(?:\s*/\s*`([^`]+)`)?\s*\|", doc, re.M):
        listed.update(g for g in m.groups() if g)

    on_disk = {p.relative_to(REPO).as_posix() for p in (REPO / "core").glob("*.py")
               if not p.name.startswith("__")}
    assert not (on_disk - listed), \
        f"add to the file map in docs/DEVELOPING.md: {sorted(on_disk - listed)}"

    # ...and nothing in the map may name a file that isn't there.
    ghosts = [p for p in listed
              if (p.endswith((".py", ".sh")) and "*" not in p and not (REPO / p).exists())]
    assert not ghosts, f"file map names missing files: {ghosts}"


def test_the_firmware_header_matches_the_ino():
    """`firmware/src/protocol.h` declares the firmware version a SECOND time, and
    its own comment says "== FW_VERSION in the .ino". It was 2.8.2 against an .ino
    on 2.9.2 — drifted silently, because nothing compared them.

    That is the third copy of this number to drift (the flash manifest twice, now
    this), and the pattern is always the same: a comment asks a human to keep two
    files in step. RELEASE.md's bump list named this file and NOT the two the
    tests already enforce, so following the runbook exactly moved the one nothing
    checked and left the two that are checked behind."""
    header = (REPO / "firmware" / "src" / "protocol.h").read_text(encoding="utf-8")
    m = re.search(r'#define\s+TEMPSENSOR_FW_VERSION\s+"([^"]+)"', header)
    assert m, "TEMPSENSOR_FW_VERSION not found — did the declaration change shape?"
    assert m.group(1) == firmware_version(), (
        f"protocol.h says {m.group(1)}, the .ino says {firmware_version()}")


def test_the_release_runbook_names_every_file_that_must_move():
    """RELEASE.md step 1 is what a person follows at 11pm on release day. It has
    to name every file carrying a version, or the ones it omits drift — which is
    exactly how the flash manifest got stale twice."""
    runbook = (REPO / "RELEASE.md").read_text(encoding="utf-8")
    must_name = ["core/version.py", "pyproject.toml", "firmware/src/protocol.h",
                 "flash/manifest.json", "flash/index.html",
                 "esp32_temp_probe.ino"]
    missing = [f for f in must_name if f not in runbook]
    assert not missing, (
        f"RELEASE.md does not mention {missing}. Every one of these carries a "
        f"version string the test suite enforces; a runbook that omits them "
        f"produces exactly the drift those tests exist to catch.")


def test_the_qc_gate_checks_units_against_the_firmware_they_are_flashed_with():
    """The factory label and the `/whoami` line an operator compares against.

    These are not documentation. `firmware/factory_flash.py` prints FW_VERSION
    on the physical label and puts it in the QC gate line, and the checklist
    repeats it — so a stale copy means every unit built either fails its own
    check or passes it by the operator trusting the wrong number. The literal
    in factory_flash.py had drifted a whole release behind; it is derived from
    the sketch now, and this pins the two documents that still spell it out.
    """
    import sys
    sys.path.insert(0, str(REPO / "firmware"))
    try:
        import factory_flash
    finally:
        sys.path.pop(0)
    assert factory_flash.FW_VERSION == firmware_version(), (
        "the manufacturing script names a different firmware version than the "
        "sketch it flashes")

    qc = (REPO / "docs" / "QC_CHECKLIST.md").read_text(encoding="utf-8")
    assert f"**v{firmware_version()}**" in qc, (
        "docs/QC_CHECKLIST.md advertises a different firmware version than the "
        f"sketch ({firmware_version()})")
    assert f"`{firmware_version()}`" in qc, (
        "the QC gate's fw_version comparison is against a stale version")

    guide = (REPO / "web" / "guide.html").read_text(encoding="utf-8")
    assert f"v{firmware_version()} image" in guide, (
        "web/guide.html advertises a different firmware image than the flasher "
        "on the same site ships")


def test_the_release_runbook_does_not_teach_a_build_that_breaks_the_lgpl_promise():
    """THIRD-PARTY-LICENSES.md promises `zeroconf` ships as replaceable files
    under `_internal/`. `--onefile` bundles it into the executable, so a
    runbook that says to build that way makes every shipped copy break a
    licence term — and drops the spec's datas and hiddenimports besides."""
    runbook = (REPO / "RELEASE.md").read_text(encoding="utf-8")
    # In the COMMANDS, not the prose — the runbook is allowed to say "never
    # --onefile", and should.
    blocks = runbook.split("```")[1::2]
    offenders = [b for b in blocks if "--onefile" in b]
    assert not offenders, (
        "RELEASE.md still gives a --onefile build as a command; the shipped "
        f"licence notice promises an onedir bundle:\n{offenders}")
    assert "packaging/temperature_hub.spec" in runbook, (
        "RELEASE.md should point at the spec, which is what carries the data "
        "files and hidden imports the app needs at runtime")


def test_the_badges_and_docs_name_the_version_the_code_reports():
    """README's badges and DEVELOPING.md's header, against the two sources of
    truth. Both had drifted — the hub badge sat on 2.6.2 while core/version.py
    said 2.7.2, and the firmware badge on 2.8.2 while the sketch said 2.9.3 —
    so the first thing a visitor reads about this project was wrong about both
    halves of it. Everything else carrying a version is already enforced here;
    these two were the gap.
    """
    from core.version import HUB_VERSION
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert f"hub-v{HUB_VERSION}-" in readme, (
        f"README's hub badge disagrees with core/version.py ({HUB_VERSION})")
    assert f"firmware-v{firmware_version()}-" in readme, (
        f"README's firmware badge disagrees with the sketch ({firmware_version()})")

    developing = (REPO / "docs" / "DEVELOPING.md").read_text(encoding="utf-8")
    assert f"version **{HUB_VERSION}**" in developing, (
        "docs/DEVELOPING.md names a hub version core/version.py does not")

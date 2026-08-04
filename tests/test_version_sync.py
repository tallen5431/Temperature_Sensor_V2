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


def test_packaging_version_matches_the_hub_version():
    """pyproject.toml declares the version a second time, for the wheel. Same
    shape as the flash manifest, which drifted twice while a note asked people
    to keep it in sync -- so this is enforced instead of asked for."""
    import tomllib
    from core.version import HUB_VERSION
    meta = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert meta["project"]["version"] == HUB_VERSION, \
        "bump pyproject.toml's version alongside core/version.py"


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

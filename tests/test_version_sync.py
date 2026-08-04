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

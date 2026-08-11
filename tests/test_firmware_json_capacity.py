"""Every StaticJsonDocument in the firmware, against what it actually holds.

ArduinoJson v6 fails QUIETLY in both directions, which is why these were wrong
and nobody noticed. A parse that outgrows its pool returns ``NoMemory`` —
``handleProvision`` answers that as ``400 "bad json"``, so the probe is simply
never provisioned. A document being BUILT past its pool does not error at all:
it omits members, so ``/status`` and ``/whoami`` just stop reporting whichever
field did not fit. Neither shows up in a compile, and neither shows up on a
bench unless you happen to test with a long hub URL.

The numbers below are MEASURED, not reasoned about. They come from compiling
against ArduinoJson 6.21.6, parsing or building the real documents, reading
``memoryUsage()``, and composing the ESP32 figure from the slot count (the same
on any platform) and the copied-string bytes (just chars) at the 16-byte
``VariantSlot`` of a 32-bit target. Two hand-derived estimates were wrong before
this was done — one too low, one too high — so the model is not repeated here.

    handler            members   typical URL   128-char URL   declared
    handleProvision       7         260 B         385 B         512
    handleStatus         19         381 B         474 B         640
    handleWhoAmI          9         256 B         349 B         512
    applyHubConfig     7/10         184 B         327 B         512
    postWithTimestamp     4         105 B         122 B         256

"128-char URL" is not a hypothetical: ``P_SERVER_LEN`` is what the captive
portal accepts in the Server URL field. At the sizes these documents shipped
with, ``handleProvision`` overflowed by four bytes on an ORDINARY hub, and
``handleWhoAmI`` overflowed on a long-URL one — the endpoint
``docs/QC_CHECKLIST.md`` has the factory read ``fw_version`` from before a unit
ships.

This test cannot re-measure without the library, so it pins two things that
together catch the realistic regression: the declared size of each document,
and the number of fields it carries. Adding a field changes the count and fails
here, which is the prompt to re-measure rather than guess.
"""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
INO = (REPO / "esp32_temp_probe" / "esp32_temp_probe.ino").read_text(encoding="utf-8")

# handler -> (kind, keys the code names, measured worst-case bytes, declared size).
# "parse" reads keys out of a body somebody else built, so its pool is bounded by
# that body rather than by the keys it happens to look at; "build" assigns them,
# so the key count IS the member count. Worst case throughout is the 128-char
# server_url the captive portal accepts.
MEASURED = {
    "handleProvision":   ("parse", 7,  385, 512),
    "applyHubConfig":    ("parse", 6,  327, 512),
    "handleStatus":      ("build", 19, 474, 640),
    "handleWhoAmI":      ("build", 9,  349, 512),
    "postWithTimestamp": ("build", 4,  122, 256),
}


def _function_body(name: str) -> str:
    """One firmware function's body, by brace matching."""
    start = INO.index(name + "(")
    start = INO.rindex("\n", 0, start) + 1
    depth, out = 0, []
    for j in range(INO.index("{", start), len(INO)):
        out.append(INO[j])
        if INO[j] == "{":
            depth += 1
        elif INO[j] == "}":
            depth -= 1
            if depth == 0:
                break
    return "".join(out)


def _declared(name: str) -> int:
    sizes = [int(n) for n in
             re.findall(r"StaticJsonDocument<(\d+)> doc;", _function_body(name))]
    assert sizes, f"{name} no longer declares a `doc` StaticJsonDocument"
    return max(sizes)


@pytest.mark.parametrize("name", sorted(MEASURED))
def test_the_document_is_big_enough_for_what_it_carries(name):
    _kind, _keys, needs, required = MEASURED[name]
    declared = _declared(name)
    assert declared >= needs, (
        f"{name} declares {declared} B; it needs {needs} B at the longest hub "
        f"URL the captive portal accepts. ArduinoJson v6 does not raise on "
        f"overflow — a parse returns NoMemory and a build silently omits "
        f"members.")
    assert declared == required, (
        f"{name} declares {declared} B, not the {required} B this file "
        f"records as measured. If the size changed on purpose, re-measure and "
        f"update MEASURED; do not just move the number.")


@pytest.mark.parametrize("name", sorted(MEASURED))
def test_the_field_count_has_not_changed_without_a_remeasure(name):
    """The realistic regression is a field being added, not a size being edited.

    A new member costs a slot plus its key, and on these documents that is tens
    of bytes — enough to cross a cap that has no runtime symptom. When this
    fails, re-measure against ArduinoJson 6.x rather than nudging the number.
    """
    kind, expected, needs, _required = MEASURED[name]
    body = _function_body(name)
    if kind == "parse":
        # Reads keys rather than assigning them, so count every key it names.
        found = len(set(re.findall(r'(?:doc|c)\["(\w+)"\]', body)))
    else:
        # Assignments, deduplicated: `buffered_bytes` is written in both arms of
        # an if/else in handleStatus, so it costs one slot, not two.
        found = len(set(re.findall(r'doc\["(\w+)"\]\s*=', body)))
    assert found == expected, (
        f"{name} now names {found} keys, not the {expected} the measured "
        f"{needs} B figure was taken against — re-measure it")


def test_the_library_major_version_is_pinned():
    """v6 and v7 disagree about whether these sizes mean anything.

    Under v6 a StaticJsonDocument is a fixed pool and every number above is
    load-bearing. Under v7 the parameter is ignored and the document grows on
    the heap, so a v7 build hides exactly the mistakes a v6 build ships. An
    unpinned `lib install` follows the latest release, so which one the
    published firmware was built against would be decided by the calendar.
    """
    workflow = (REPO / ".github" / "workflows" / "deploy-flasher.yml").read_text(encoding="utf-8")
    assert re.search(r'"ArduinoJson@6\.[\d.]+"', workflow), (
        "the flasher workflow installs ArduinoJson unpinned; the buffer sizes "
        "in this file only mean something under v6")
    readme = (REPO / "firmware" / "README.md").read_text(encoding="utf-8")
    assert re.search(r"ArduinoJson@6\.[\d.]+", readme), (
        "firmware/README.md tells a builder to install ArduinoJson unpinned")

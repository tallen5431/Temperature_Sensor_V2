"""PROTOCOL.md is a contract, and it had drifted three fields behind the wire.

It said the `/api/ingest` config reply was "deliberately limited to `interval_ms`
and `resolution_bits`". The hub has sent `alert_min_c`, `alert_max_c` and
`sample_ms` in it since 2.6.2, and those three are the entire threshold watch —
the thing that lets a probe on a 15-minute report notice a thawing freezer in a
minute. Anyone writing a second firmware against that paragraph would have
dropped them and produced a probe that looked correct and watched nothing.

This is the fourth doc/code pair in this repo to drift while a comment asked a
human to keep them in step (the flash manifest twice, `protocol.h`, now this), and
the pattern is always the same: prose nobody executes. So the field list is
checked against `desired_probe_config` — the one function both delivery paths
derive from — rather than proofread.
"""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
DOC = (REPO / "PROTOCOL.md").read_text(encoding="utf-8")


def _section(heading: str) -> str:
    """The text of one `### n.n Title` section, up to the next heading."""
    start = DOC.index(heading)
    rest = DOC[start + len(heading):]
    end = re.search(r"^#{2,3} ", rest, re.M)
    return rest[:end.start()] if end else rest


def _config_reply_fields():
    """Exactly what the hub puts in the ingest reply's ``config`` object."""
    from provisioning import desired_probe_config
    return set(desired_probe_config(
        {"interval_sec": 900, "probe_sample_sec": 60,
         "alert_thresholds": {"default": {"min": 1.0, "max": 5.0}}}, "P"))


def test_the_ingest_config_reply_documents_every_field_it_sends():
    section = _section("### 5.2") if "### 5.2 Config" in DOC else _section("## 5. Ingest")
    missing = [f for f in sorted(_config_reply_fields()) if f not in section]
    assert not missing, (
        f"PROTOCOL.md §5 does not mention {missing}, which the hub sends in every "
        f"/api/ingest reply. A field the spec omits is a field a second "
        f"implementation drops.")


def test_the_provision_push_documents_every_field_it_sends():
    """§4.1 is the push half of the same settings. Both paths derive from
    desired_probe_config, so the two lists cannot legitimately differ."""
    section = _section("### 4.1 `POST /provision`")
    for field in sorted(_config_reply_fields() | {"server_url", "token"}):
        assert field in section, f"§4.1 does not document {field}"


def test_status_documents_what_the_hub_compares_against():
    """The auto-provisioner reads watch_armed/sample_ms/the limits off /status to
    decide whether a probe needs re-provisioning. A spec that omits them lets a
    second firmware ship without them, and that hub would then re-push every
    cycle — or, worse, never notice a probe holding a deleted limit."""
    section = _section("### 4.3 `GET /status`")
    for field in ("watch_armed", "sample_ms", "alert_min_c", "alert_max_c", "in_breach"):
        assert field in section, f"§4.3 does not document /status.{field}"


def test_the_status_fields_are_the_ones_the_firmware_actually_emits():
    ino = (REPO / "esp32_temp_probe" / "esp32_temp_probe.ino").read_text(encoding="utf-8")
    for field in ("watch_armed", "sample_ms", "alert_min_c", "alert_max_c", "in_breach"):
        assert f'doc["{field}"]' in ino, f"the firmware no longer emits {field}"


def test_the_provisioner_reads_the_fields_the_spec_promises():
    src = (REPO / "provisioner.py").read_text(encoding="utf-8")
    for field in ("sample_ms", "alert_min_c", "alert_max_c"):
        assert f'status.get("{field}")' in src or f'"{field}" in status' in src, \
            f"the provisioner no longer compares {field}"


def test_the_watch_has_its_own_section():
    """It is a protocol behaviour, not an implementation detail: the sample /
    buffer / flush cycle and the never-late rule are what a second firmware has to
    reproduce."""
    assert "### 5.3 Threshold watch" in DOC
    section = _section("### 5.3 Threshold watch")
    assert "radio" in section and "buffer" in section.lower()
    assert "MUST NOT report late" in section


def test_the_floor_in_the_spec_is_the_floor_in_the_firmware():
    """5000 ms appears in the spec as a MUST. If WATCH_SAMPLE_MIN_MS moves, the
    spec becomes wrong about the one number a second implementation would hard-code."""
    ino = (REPO / "esp32_temp_probe" / "esp32_temp_probe.ino").read_text(encoding="utf-8")
    m = re.search(r"WATCH_SAMPLE_MIN_MS = (\d+)UL", ino)
    assert m, "WATCH_SAMPLE_MIN_MS changed shape"
    assert f"{m.group(1)} ms" in DOC or m.group(1) in DOC, \
        f"PROTOCOL.md does not state the {m.group(1)} ms sample floor the firmware enforces"


def test_the_hub_clamps_to_that_same_floor():
    """The spec says a probe MUST ignore a sample_ms below the floor. A hub that
    sends one anyway would be configuring a watch that silently does not run, so
    the hub clamps rather than relies on the probe to refuse."""
    from provisioning import desired_probe_config
    out = desired_probe_config(
        {"interval_sec": 900, "probe_sample_sec": 1,
         "alert_thresholds": {"default": {"max": 5.0}}}, "P")
    assert out["sample_ms"] == 5000


@pytest.mark.parametrize("limit", ["alert_min_c", "alert_max_c"])
def test_a_deleted_limit_is_sent_as_null_not_omitted(limit):
    """§4.1 promises explicit nulls, because an omitted key leaves a probe
    watching a threshold nobody holds."""
    from provisioning import desired_probe_config
    out = desired_probe_config({"interval_sec": 900}, "P")
    assert limit in out and out[limit] is None


# --- the firmware's own half of §4.1 ---------------------------------------
# The tests above check that the HUB sends what the spec promises. Nothing
# checked that the probe stores it, and it did not: handleProvision() parsed
# server_url, token, interval_ms and resolution_bits, and silently dropped the
# three watch fields §4.1 requires it to persist. The push path therefore
# reported the watch as delivered, the Devices dialog reported it as armed, and
# only the PULL path (the /api/ingest reply) ever actually armed it — a setting
# that reads as applied and is not.
#
# The firmware half normally needs a probe on a bench. These are source
# assertions instead, in the style this file already uses for doc/code drift:
# they cannot prove the probe behaves, but they can prove the handler at least
# reads each field, which is the part that was missing.

INO = (REPO / "esp32_temp_probe" / "esp32_temp_probe.ino").read_text(encoding="utf-8")


def _ino_function(name: str) -> str:
    """The body of one top-level firmware function, by brace matching."""
    start = INO.index(f"void {name}()")
    depth, i = 0, INO.index("{", start)
    for j in range(i, len(INO)):
        if INO[j] == "{":
            depth += 1
        elif INO[j] == "}":
            depth -= 1
            if depth == 0:
                return INO[start:j + 1]
    raise AssertionError(f"could not find the end of {name}()")


@pytest.mark.parametrize("field", ["server_url", "token", "interval_ms",
                                   "resolution_bits", "alert_min_c", "alert_max_c",
                                   "sample_ms"])
def test_the_firmware_provision_handler_reads_every_field_the_spec_sends(field):
    body = _ino_function("handleProvision")
    assert f'"{field}"' in body, (
        f"POST /provision drops `{field}`. PROTOCOL.md §4.1 says the probe "
        f"persists it, and the hub's push path sends it and records the push as "
        f"delivered — so the setting reads as applied and is not.")


def test_the_provision_handler_clears_a_limit_the_hub_removed():
    """§4.1's explicit-null-clears rule, the same one applyHubConfig implements.

    A limit deleted on the dashboard arrives as JSON null. Ignoring it leaves
    the probe waking every minute to check a limit nobody holds any more.
    """
    body = _ino_function("handleProvision")
    for field in ("alert_min_c", "alert_max_c"):
        assert f'doc["{field}"] | WATCH_UNSET_C' in body, (
            f"{field} must default to WATCH_UNSET_C so an explicit null clears it")
    assert 'doc.containsKey("sample_ms")' in body


def test_the_provision_handler_can_hold_the_body_the_hub_sends():
    """ArduinoJson v6 StaticJsonDocument is a hard pool cap, and deserializeJson
    parses the whole body regardless of which keys are read after. The
    documented 7-field push costs roughly 260 bytes with a real hub URL and the
    32-char token app.py generates; at 256 it returned NoMemory and the handler
    answered 400 "bad json", so the probe was never provisioned at all."""
    body = _ino_function("handleProvision")
    sizes = [int(n) for n in re.findall(r"StaticJsonDocument<(\d+)> doc;", body)]
    assert sizes, "handleProvision no longer declares a parse document"
    assert min(sizes) >= 512, (
        f"the /provision parse buffer is {min(sizes)} bytes; the documented "
        f"7-field body needs ~260 and a longer hub URL or token needs more")

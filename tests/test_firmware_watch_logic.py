"""Run the extracted threshold-watch logic from the probe firmware.

A firmware change is mostly unverifiable without a probe on a bench — radio
behaviour, current draw, NVS wear. The decision logic is the exception: it is
pure arithmetic and a two-state machine, and getting the hysteresis wrong is
both easy and expensive (a probe parked on its limit that transmits every
sample flattens a battery in days).

So the watch predicates are duplicated verbatim into
``tests/firmware/watch_logic_test.cpp`` and compiled on the host. The copy is
the cost; the alternative is shipping this logic entirely untested.

Skipped when no C++ compiler is available.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).parent / "firmware" / "watch_logic_test.cpp"
INO = Path(__file__).parent.parent / "esp32_temp_probe" / "esp32_temp_probe.ino"


@pytest.mark.skipif(not shutil.which("g++"), reason="no C++ compiler")
def test_watch_logic(tmp_path):
    exe = tmp_path / "watch_test"
    build = subprocess.run(["g++", "-Wall", "-Wextra", "-O2", "-o", str(exe), str(SRC)],
                           capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    run = subprocess.run([str(exe)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "all watch-logic checks passed" in run.stdout


def test_the_copy_still_matches_the_firmware():
    """The .cpp holds a verbatim copy of two functions and three constants. If
    the firmware's version drifts, the test above is validating code that no
    probe runs — worse than no test, because it reads like coverage."""
    ino = INO.read_text()
    cpp = SRC.read_text()
    for fragment in (
        "static const float    WATCH_UNSET_C       = -999.0f;",
        "static const float    WATCH_HYSTERESIS_C  = 0.5f;",
        "static const uint32_t WATCH_SAMPLE_MIN_MS = 5000UL;",
        "  bool haveLimit = (cfg_alert_min_c > WATCH_UNSET_C) || (cfg_alert_max_c > WATCH_UNSET_C);",
        "  return haveLimit && cfg_sample_ms >= WATCH_SAMPLE_MIN_MS && cfg_sample_ms < cfg_interval;",
        "  const float slack = rtc_inBreach ? WATCH_HYSTERESIS_C : 0.0f;",
        "  if (cfg_alert_max_c > WATCH_UNSET_C && tC > cfg_alert_max_c - slack) return true;",
        "  if (cfg_alert_min_c > WATCH_UNSET_C && tC < cfg_alert_min_c + slack) return true;",
    ):
        assert fragment in ino, f"firmware no longer contains: {fragment}"
        assert fragment in cpp, f"host copy no longer contains: {fragment}"

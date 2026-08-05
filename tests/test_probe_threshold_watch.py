"""What the hub tells a probe about its own limits.

A probe on a long report interval can sit on a thawing freezer until its next
scheduled POST. The firmware's disturbance burst does not cover it — that fires
on a sudden CHANGE, and a slow thaw has none — so the hub hands the probe its
limits and a sample cadence, and the probe transmits early when a reading
crosses one. Reading the sensor is cheap; the radio is the expensive part.

These cover the hub half. The firmware half needs a probe on a bench.
"""
from provisioning import desired_probe_config


def test_limits_reach_the_probe():
    cfg = {"interval_sec": 900,
           "alert_thresholds": {"default": {"min": -20.0, "max": -15.0}}}
    out = desired_probe_config(cfg, "Setpoint-9A3F2C")
    assert out["alert_min_c"] == -20.0
    assert out["alert_max_c"] == -15.0
    assert out["sample_ms"] == 60_000          # sample every minute, report every 15


def test_a_per_probe_limit_beats_the_default():
    cfg = {"interval_sec": 900, "alert_thresholds": {
        "default": {"min": 0.0, "max": 8.0},
        "Freezer": {"min": -25.0, "max": -15.0}}}
    assert desired_probe_config(cfg, "Freezer")["alert_max_c"] == -15.0
    assert desired_probe_config(cfg, "Cooler")["alert_max_c"] == 8.0


def test_no_thresholds_means_no_watch():
    """The feature must be inert on a hub that has set no limits — which is the
    default. A probe that gets no limits keeps waking exactly as it does now."""
    out = desired_probe_config({"interval_sec": 900}, "P")
    assert out["alert_min_c"] is None
    assert out["alert_max_c"] is None
    assert out["sample_ms"] == 0


def test_deleting_a_threshold_disarms_rather_than_going_quiet():
    """The keys are present-and-null, not absent. An absent key would leave a
    probe watching a limit the hub no longer holds, waking every minute for it."""
    out = desired_probe_config({"interval_sec": 900, "alert_thresholds": {}}, "P")
    assert "alert_min_c" in out and out["alert_min_c"] is None
    assert "alert_max_c" in out and out["alert_max_c"] is None


def test_sampling_faster_than_reporting_is_the_only_case_worth_it():
    """A 30 s report interval already beats a 60 s sample: sending 0 tells the
    firmware to read and report together, exactly as before."""
    cfg = {"interval_sec": 30, "alert_thresholds": {"default": {"max": 8.0}}}
    assert desired_probe_config(cfg, "P")["sample_ms"] == 0


def test_one_sided_limits_are_allowed():
    cfg = {"interval_sec": 900, "alert_thresholds": {"default": {"max": 8.0}}}
    out = desired_probe_config(cfg, "P")
    assert out["alert_min_c"] is None and out["alert_max_c"] == 8.0
    assert out["sample_ms"] == 60_000


def test_junk_limits_cannot_break_ingest():
    """desired_probe_config runs on the live ingest path — a bad config value
    must not 500 every reading from every probe."""
    for bad in ("nonsense", None, float("inf"), float("nan"), [1, 2]):
        cfg = {"interval_sec": 900, "alert_thresholds": {"default": {"max": bad}}}
        out = desired_probe_config(cfg, "P")
        assert out["alert_max_c"] is None, bad
        assert out["sample_ms"] == 0


def test_sample_cadence_is_configurable_and_floored():
    base = {"interval_sec": 900, "alert_thresholds": {"default": {"max": 8.0}}}
    assert desired_probe_config({**base, "probe_sample_sec": 300}, "P")["sample_ms"] == 300_000
    # Below the firmware's floor: clamped, not honoured.
    assert desired_probe_config({**base, "probe_sample_sec": 1}, "P")["sample_ms"] == 5_000


def test_a_threshold_change_reprovisions_the_probe(monkeypatch):
    """The watch is part of "what should this probe be running", so it has to be
    in the provisioner's change-detection tuple — otherwise editing a limit on
    the dashboard would never reach a probe already provisioned this session,
    and it would keep watching the old one until the hub restarted."""
    import time
    from tests.test_provisioner import _make_ap, _patch_net, _probe

    provisions = []
    # A probe running the watch firmware reports back what it holds, which is
    # what lets the hub tell "already correct" from "needs the new limit".
    _patch_net(monkeypatch, provisions=provisions,
               status_result={"server_url": "http://hub/api/ingest",
                              "interval_ms": 900000, "resolution_bits": 11,
                              "alert_min_c": None, "alert_max_c": 8.0,
                              "sample_ms": 60000})
    cfg = {"interval_sec": 900, "alert_thresholds": {"default": {"max": 8.0}}}
    ap = _make_ap({"P": _probe("P", last_seen=time.time())}, cfg=cfg)

    ap._run_cycle()
    assert len(provisions) == 1
    assert provisions[0]["watch"] == (None, 8.0, 60_000)

    ap._run_cycle()                      # nothing changed -> no re-push
    assert len(provisions) == 1

    cfg["alert_thresholds"]["default"]["max"] = 4.0
    ap._run_cycle()
    assert len(provisions) == 2, "a threshold change must reach the probe"
    assert provisions[1]["watch"] == (None, 4.0, 60_000)

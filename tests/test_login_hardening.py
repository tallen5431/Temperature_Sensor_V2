"""The dashboard login: throttled guessing, and on/off from Settings.

Three gaps on the networks Setpoint is sold into: the login could only be
switched on by hand-editing config.json (or env vars) and a restart; once on, a
guesser on the LAN could try passwords as fast as the hub answered; and nothing
on the Settings page said the dashboard — alert limits, email credentials and
all — was open to anyone on a shared Wi-Fi.
"""
import json
import subprocess
import sys
import textwrap

import pytest

from components.settings_panel import build_reliability_config, reliability_badge
from core.login_throttle import LoginThrottle


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


# --- throttle -------------------------------------------------------------------

def test_locks_out_after_the_limit_and_lifts_after_the_lockout():
    clock = _Clock()
    t = LoginThrottle(limit=3, window=60, lockout=120, clock=clock)
    for _ in range(2):
        t.failure("10.0.0.9")
    assert t.retry_after("10.0.0.9") == 0
    t.failure("10.0.0.9")
    assert t.retry_after("10.0.0.9") > 0
    assert t.retry_after("10.0.0.10") == 0       # per client, not hub-wide
    clock.t += 121
    assert t.retry_after("10.0.0.9") == 0


def test_failures_outside_the_window_do_not_add_up():
    clock = _Clock()
    t = LoginThrottle(limit=3, window=60, lockout=120, clock=clock)
    for _ in range(5):
        t.failure("c")
        clock.t += 31                             # never 3 inside any 60 s
    assert t.retry_after("c") == 0


def test_a_success_clears_the_count():
    t = LoginThrottle(limit=3, window=60, lockout=120, clock=_Clock())
    t.failure("c")
    t.failure("c")
    t.success("c")
    t.failure("c")
    assert t.retry_after("c") == 0


def test_memory_is_bounded_on_a_noisy_network():
    t = LoginThrottle(limit=100, clock=_Clock(), max_clients=10)
    for i in range(50):
        t.failure(f"10.0.0.{i}")
    assert len(t._fails) <= 10


# --- the real gate, booted (see test_ui_auth_gate.py for why a subprocess) ------

_PROBE = textwrap.dedent("""
    import base64, json, os, sys
    os.environ["MDNS_ENABLE"] = "0"
    os.environ["DATA_DIR"] = sys.argv[1]
    os.environ.pop("UI_USERNAME", None); os.environ.pop("UI_PASSWORD", None)
    sys.path.insert(0, sys.argv[2])
    import app
    c = app.server.test_client()
    def hdr(u, p):
        return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}
    out = {"startup_enabled": app.UI_AUTH_ENABLED}
    out["open_before"] = c.get("/").status_code
    # Turned on the way Settings does it: a config update, no restart.
    app.cfg.update({"ui_auth": {"enabled": True, "username": "op", "password": "s3cr3t-pw"}})
    out["anon_after"] = c.get("/").status_code
    out["good_after"] = c.get("/", headers=hdr("op", "s3cr3t-pw")).status_code
    out["no_creds_many"] = [c.get("/").status_code for _ in range(15)][-1]
    out["good_still"] = c.get("/", headers=hdr("op", "s3cr3t-pw")).status_code
    wrong = [c.get("/", headers=hdr("op", "guess%d" % i)).status_code for i in range(10)]
    out["wrong"] = wrong
    locked = c.get("/", headers=hdr("op", "s3cr3t-pw"))
    out["locked"] = locked.status_code
    out["retry_after"] = locked.headers.get("Retry-After")
    out["metrics_locked"] = c.get("/metrics").status_code
    app.cfg.update({"ui_auth": {"enabled": False, "username": "op", "password": "s3cr3t-pw"}})
    app.LOGIN_THROTTLE.success("127.0.0.1")
    out["open_again"] = c.get("/").status_code
    print("@@" + json.dumps(out))
""")


@pytest.fixture(scope="module")
def gate(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("gate")
    script = tmp / "probe.py"
    script.write_text(_PROBE, encoding="utf-8")
    repo = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
    res = subprocess.run([sys.executable, str(script), str(tmp), repo],
                         capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, res.stderr[-3000:]
    line = [ln for ln in res.stdout.splitlines() if ln.startswith("@@")]
    assert line, res.stdout[-2000:] + res.stderr[-2000:]
    return json.loads(line[0][2:])


def test_turning_the_login_on_in_settings_applies_without_a_restart(gate):
    assert gate["startup_enabled"] is False and gate["open_before"] == 200
    assert gate["anon_after"] == 401
    assert gate["good_after"] == 200


def test_a_browser_asking_for_the_prompt_is_not_counted_as_guessing(gate):
    assert gate["no_creds_many"] == 401
    assert gate["good_still"] == 200


def test_ten_wrong_passwords_lock_the_client_out_even_with_the_right_one(gate):
    assert gate["wrong"][:9] == [401] * 9
    assert gate["locked"] == 429 and int(gate["retry_after"]) > 0


def test_the_lockout_leaves_the_operational_endpoints_alone(gate):
    """Prometheus scraping from the same box must not go dark because someone
    fat-fingered the dashboard password."""
    assert gate["metrics_locked"] == 200


def test_turning_it_off_again_opens_the_dashboard(gate):
    assert gate["open_again"] == 200


# --- the Settings form ----------------------------------------------------------

def _form(**kw):
    args = dict(hb_enabled=False, hb_url="", hb_interval_min=5, keep_awake=True,
                ua_enabled=False, ua_user="", ua_pass="", existing={})
    args.update(kw)
    return build_reliability_config(**args)


def test_a_login_needs_a_username_and_a_password():
    assert _form(ua_enabled=True, ua_pass="longenough")[1]
    assert _form(ua_enabled=True, ua_user="op")[1]
    updates, err = _form(ua_enabled=True, ua_user="op", ua_pass="longenough")
    assert err is None and updates["ui_auth"] == {
        "enabled": True, "username": "op", "password": "longenough"}


def test_short_passwords_are_refused():
    assert "8" in _form(ua_enabled=True, ua_user="op", ua_pass="1234")[1]


def test_a_blank_password_keeps_the_saved_one():
    existing = {"ui_auth": {"enabled": True, "username": "op", "password": "old-password"}}
    updates, err = _form(ua_enabled=True, ua_user="op", existing=existing)
    assert err is None and updates["ui_auth"]["password"] == "old-password"


def test_a_heartbeat_needs_a_real_url():
    assert _form(hb_enabled=True, hb_url="hc-ping.com/x")[1]
    updates, err = _form(hb_enabled=True, hb_url=" https://hc-ping.com/x ", hb_interval_min=2)
    assert err is None
    assert updates["heartbeat"] == {"enabled": True, "url": "https://hc-ping.com/x",
                                    "interval_sec": 120}


def test_nothing_is_saved_from_a_form_with_an_error():
    updates, err = _form(hb_enabled=True, hb_url="", ua_enabled=True, ua_user="op",
                         ua_pass="longenough")
    assert updates is None and err


def test_no_login_is_flagged_on_the_section_header(monkeypatch):
    monkeypatch.delenv("UI_USERNAME", raising=False)
    assert reliability_badge({}) == ("No login", "warning")
    on = {"ui_auth": {"enabled": True, "username": "op", "password": "pw"}}
    assert reliability_badge(on) == ("Login on", "info")
    both = {**on, "heartbeat": {"enabled": True, "url": "https://hc-ping.com/x"}}
    assert reliability_badge(both) == ("Login on · Heartbeat", "success")


def test_a_login_set_by_environment_counts(monkeypatch):
    monkeypatch.setenv("UI_USERNAME", "op")
    assert reliability_badge({})[1] != "warning"

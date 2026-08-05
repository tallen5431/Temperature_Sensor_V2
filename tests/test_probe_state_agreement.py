"""The Dashboard card and the Devices card, on the same probe, at the same time.

Two pages showed a probe's condition and each derived it independently. They
disagreed, in opposite directions, on the one state that matters most:

    a probe that breached its limit and then stopped reporting

The Dashboard tested staleness first, so it rendered a calm grey "● stale" and
dropped the alarm entirely. The Devices grid tested the breach first, so it
rendered a red "ALARM" and dropped the silence — presenting an hours-old number
as if it were live. One probe, one moment, a grey card on one page and a red one
on the other, and neither told the whole truth.

Both now go through ``core.status.probe_state``. These pin the facts each page
must carry, and that they carry the same ones.
"""
import datetime

import dash
import pytest

from components import dashboard_view
from components.dashboard_view import build_probe_cards
from components.devices_panel import DevicesLayout, register_devices_callbacks
from core.config import Config
from core.db import Database
from core.status import probe_state

# Old enough to be stale under any window the hub will compute (the floor is
# ONLINE_TIMEOUT_SEC = 60 s, widened by interval and config, never shortened).
STALE_AGO = datetime.timedelta(hours=6)


def _iso(dt):
    return dt.isoformat(timespec="milliseconds")


class _HeldStub:
    def __init__(self, states=None):
        self._s = states or {}

    def get(self, pid):
        return self._s.get(pid)


class _NoFinder:
    def list_probes(self):
        return {}


def _dashboard_text(tmp_path, temp_c, thresholds, ago, held=None, monkeypatch=None):
    db = Database(tmp_path / "dash.db")
    cfg = Config(tmp_path / "dash.json")
    if thresholds:
        cfg.update({"alert_thresholds": {"A": thresholds}})
    db.append(_iso(datetime.datetime.now() - ago), temp_c, temp_c * 9 / 5 + 32, "A")
    monkeypatch.setattr(dashboard_view, "HELD", _HeldStub(held or {}))
    return str(build_probe_cards(db, cfg, "celsius"))


def _devices_text(tmp_path, temp_c, thresholds, ago, held=None):
    from core.alerts import HELD
    HELD.set_states(held or {})
    db = Database(tmp_path / "dev.db")
    db.append(_iso(datetime.datetime.now() - ago), temp_c, temp_c * 9 / 5 + 32, "A")
    app = dash.Dash(__name__)
    app.layout = DevicesLayout
    app.config.suppress_callback_exceptions = True
    cfg = {"alert_thresholds": {"A": thresholds}} if thresholds else {}
    register_devices_callbacks(app, finder=_NoFinder(), cfg=cfg, db=db)
    fn = app.callback_map["device-grid.children"]["callback"].__wrapped__
    return str(fn(0, "celsius"))


# --- the verdict itself ----------------------------------------------------

def test_a_breach_that_has_gone_silent_reports_both_facts():
    """Not one or the other. Dropping either half is what each page did."""
    st = probe_state(-8.0, {"min": -22.0, "max": -15.0}, stale=True)
    assert st["alarm"] == "high"
    assert st["stale"] is True
    assert st["severity"] == "danger", "silence must not downgrade an open breach"


def test_a_held_breach_still_counts_as_an_alarm_once_the_reading_is_back_inside():
    """The monitor's hysteresis deadband keeps the incident open; the pages read
    that from HELD, and it has to survive the shared verdict."""
    assert probe_state(29.5, {"max": 30.0}, held="high")["alarm"] == "high"
    assert probe_state(29.5, {"max": 30.0}, held=None)["alarm"] is None


def test_a_live_breach_does_not_need_the_held_registry():
    assert probe_state(31.0, {"max": 30.0})["alarm"] == "high"
    assert probe_state(-30.0, {"min": -22.0})["alarm"] == "low"


def test_a_probe_with_no_limits_is_not_success():
    """"OK" means "inside its limits". With none set nothing is checking it."""
    st = probe_state(21.0, {})
    assert st["watched"] is False and st["severity"] != "success"
    assert probe_state(21.0, {"max": 30.0})["severity"] == "success"


def test_a_zero_bound_is_a_real_limit():
    """A freezer at max 0.0 is watched. Truthiness would read 0.0 as "unset"."""
    assert probe_state(1.0, {"max": 0.0}) == {
        "alarm": "high", "stale": False, "watched": True, "severity": "danger"}


def test_a_missing_reading_never_invents_an_alarm():
    assert probe_state(None, {"max": 30.0})["alarm"] is None
    assert probe_state("n/a", {"max": 30.0})["alarm"] is None


# --- and that both pages actually use it -----------------------------------

def test_both_pages_report_the_alarm_when_a_breached_probe_goes_silent(tmp_path, monkeypatch):
    thr = {"min": -22.0, "max": -15.0}
    dash_txt = _dashboard_text(tmp_path, -8.0, thr, STALE_AGO, monkeypatch=monkeypatch)
    dev_txt = _devices_text(tmp_path, -8.0, thr, STALE_AGO)
    for page, txt in (("dashboard", dash_txt), ("devices", dev_txt)):
        assert "ALARM" in txt, f"{page} dropped the breach for a silent probe"
        assert "NO SIGNAL" in txt, (
            f"{page} shows an hours-old reading with nothing saying it is old")


def test_both_pages_agree_a_fresh_breach_is_an_alarm_without_the_signal_warning(
        tmp_path, monkeypatch):
    thr = {"max": -15.0}
    now = datetime.timedelta(0)
    dash_txt = _dashboard_text(tmp_path, -8.0, thr, now, monkeypatch=monkeypatch)
    dev_txt = _devices_text(tmp_path, -8.0, thr, now)
    assert "NO SIGNAL" not in dash_txt and "NO SIGNAL" not in dev_txt, \
        "a probe that is reporting normally must not be labelled as having no signal"
    assert "HIGH" in dash_txt and "ALARM" in dev_txt


@pytest.mark.parametrize("page", ["dashboard", "devices"])
def test_neither_page_calls_an_unwatched_probe_ok(tmp_path, monkeypatch, page):
    """Devices already refused to; the Dashboard said "● OK" in green for a probe
    with no limits behind it — the page most people leave open, reassuring them
    about a probe nothing was checking."""
    now = datetime.timedelta(0)
    txt = (_dashboard_text(tmp_path, 21.0, None, now, monkeypatch=monkeypatch)
           if page == "dashboard" else _devices_text(tmp_path, 21.0, None, now))
    assert "● OK" not in txt and "'OK'" not in txt
    assert "no alarm set" in txt.lower()

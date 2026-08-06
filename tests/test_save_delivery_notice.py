"""Tests for the Devices-page "when will this reach the probe?" notice.

A settings change is delivered by the probe PULLING it off an ``/api/ingest``
reply, so on a long deep-sleep interval it lands on the probe's next check-in
rather than on Save. The hub cannot query a sleeping probe to confirm, so the
notice is the only thing standing between the operator and "did that work?".
Two behaviours matter enough to pin:

1. With ``auto_provision`` false the hub omits ``config`` from every ingest
   reply, so the change reaches the probe *never* -- not merely late. Saying
   "it will apply shortly" there would be a lie.
2. The estimate must be a full interval, not half of one: the probe may have
   checked in moments before Save and so reads the new value on the check-in
   after next.
"""
import datetime

import dash
import pytest

from components.devices_panel import (DevicesLayout, register_devices_callbacks,
                                      _humanize_seconds)


def _callback(auto_provision=True, interval_sec=5, probe_intervals=None):
    """Build the real app wiring and hand back the undecorated callback."""
    app = dash.Dash(__name__)
    app.layout = DevicesLayout
    app.config.suppress_callback_exceptions = True
    cfg = {'auto_provision': auto_provision,
           'interval_sec': interval_sec,
           'probe_intervals': probe_intervals or {}}
    register_devices_callbacks(app, finder=None, cfg=cfg)
    return app.callback_map['device-save-status.children']['callback'].__wrapped__


def _text(node):
    """Flatten a Dash component tree to text.

    Handles a bare list/tuple at the TOP level too, not only as a component's
    children — a callback that returns one otherwise flattens to '' and every
    assertion against it passes vacuously.
    """
    if isinstance(node, str):
        return node
    if isinstance(node, (list, tuple)):
        return ' '.join(_text(c) for c in node)
    children = getattr(node, 'children', None)
    return _text(children) if children is not None else ''


# --- _humanize_seconds -------------------------------------------------------

@pytest.mark.parametrize('seconds,expected', [
    (0.5, '0.5 s'), (5, '5 s'), (59, '59 s'),
    (60, '1 minute'), (90, '1.5 minutes'), (600, '10 minutes'),
    (3600, '1 hour'), (7200, '2 hours'),
])
def test_humanize_seconds(seconds, expected):
    assert _humanize_seconds(seconds) == expected


@pytest.mark.parametrize('bad', [None, '', 'abc', object()])
def test_humanize_seconds_survives_garbage(bad):
    """The notice must never be the thing that raises inside a callback."""
    assert _humanize_seconds(bad) == 'a while'


# --- the notice --------------------------------------------------------------

def test_auto_provision_off_says_it_will_not_arrive():
    """The off-switch drops `config` from every ingest reply -- say so plainly."""
    body = _text(_callback(auto_provision=False)(1, 'Setpoint-9A3F2C', 600))
    assert 'not reach the probe' in body
    assert 'Automatic provisioning is switched off' in body
    # Must NOT imply it is merely pending.
    assert 'next check-in' not in body


def test_auto_provision_off_wins_even_on_a_fast_interval():
    """Delivery is off regardless of how often the probe reports."""
    body = _text(_callback(auto_provision=False, interval_sec=5)(1, 'p', 5))
    assert 'not reach the probe' in body


def test_short_interval_gets_a_plain_confirmation():
    """An always-on probe applies it next reading; a time estimate is noise."""
    body = _text(_callback()(1, 'Setpoint-9A3F2C', 5))
    assert 'next reading' in body
    assert 'check-in' not in body


def test_long_interval_quotes_the_interval_and_an_eta():
    body = _text(_callback()(1, 'Setpoint-9A3F2C', 600))
    assert 'next check-in' in body
    assert '10 minutes' in body
    assert 'cannot confirm delivery' in body


def test_eta_is_a_full_interval_away():
    """Worst case: the probe checked in just before Save."""
    before = datetime.datetime.now()
    body = _text(_callback()(1, 'Setpoint-9A3F2C', 3600))
    due = (before + datetime.timedelta(seconds=3600)).strftime('%H:%M')
    assert due in body


def test_falls_back_to_configured_interval_when_input_is_blank():
    """A blank box must not crash the callback or invent a 5 s estimate."""
    cb = _callback(probe_intervals={'Setpoint-9A3F2C': 1800})
    body = _text(cb(1, 'Setpoint-9A3F2C', None))
    assert '30 minutes' in body


def test_no_probe_id_is_a_no_op():
    assert _callback()(1, None, 600) is dash.no_update


def test_no_click_is_a_no_op():
    assert _callback()(None, 'Setpoint-9A3F2C', 600) is dash.no_update


def test_a_swapped_range_is_reported_not_just_logged():
    """min > max is silently swapped on save, and correctly so — threshold_breach
    tests 'value > max' first, so an inverted range makes EVERY reading a breach
    forever. But only the log said it happened: the operator saw a plain "Saved"
    and a card showing limits they never typed. On a product whose whole job is a
    safety limit, storing something other than what was entered has to be said."""
    body = _text(_callback()(1, 'Setpoint-9A3F2C', 5, 40, 2, 'celsius'))
    assert 'swapped' in body.lower()
    assert '2 to 40' in body


def test_a_sane_range_says_nothing_about_swapping():
    body = _text(_callback()(1, 'Setpoint-9A3F2C', 5, 2, 40, 'celsius'))
    assert 'swap' not in body.lower()


def test_the_swap_notice_speaks_the_operators_unit():
    body = _text(_callback()(1, 'Setpoint-9A3F2C', 5, 40, 35, 'fahrenheit'))
    assert '°F' in body and '35 to 40' in body


# --- "I set a limit, so I'm covered" ---------------------------------------
# Setting a min/max is the operator saying "tell me if this goes wrong", and the
# save confirmation is the moment they believe they are now covered. With the
# notification master switch off nothing will ever reach them: the dashboard
# shows the breach, and the 2am freezer failure this product exists to catch is
# found in the morning. The Settings badge said "Off" in the same neutral grey as
# "Keep forever" and "Single site" — genuinely-fine defaults — so nothing
# anywhere contradicted the belief.

def _notice(tmp_path, cfg_updates, min_v=1.0, max_v=5.0, dbname="n.db"):
    import dash
    from components.devices_panel import DevicesLayout, register_devices_callbacks
    from core.config import Config
    from core.db import Database

    class _NoFinder:
        def list_probes(self):
            return {}

    cfg = Config(tmp_path / (dbname + ".json"))
    cfg.update(cfg_updates)
    app = dash.Dash(__name__)
    app.layout = DevicesLayout
    app.config.suppress_callback_exceptions = True
    register_devices_callbacks(app, finder=_NoFinder(), cfg=cfg,
                               db=Database(tmp_path / dbname))
    fn = app.callback_map["device-save-status.children"]["callback"].__wrapped__
    return fn(1, "P1", 5, min_v, max_v, "celsius")


def test_saving_a_limit_with_alerts_off_says_nobody_will_be_told(tmp_path):
    out = _notice(tmp_path, {"notifications": {"enabled": False}})
    body = _text(out)
    assert "Alerts are switched off" in body
    assert "nobody will be told" in body
    assert out.color == "warning", "a green tick over that caveat reads as all-done"


def test_saving_a_limit_with_alerts_on_says_nothing_extra(tmp_path):
    out = _notice(tmp_path, {"notifications": {"enabled": True}}, dbname="on.db")
    assert "Alerts are switched off" not in _text(out)


def test_saving_without_touching_the_limits_does_not_nag(tmp_path):
    """Changing only the reporting interval is not the operator asking to be
    alerted, so this must not fire on every save."""
    out = _notice(tmp_path, {"notifications": {"enabled": False}},
                  min_v=None, max_v=None, dbname="int.db")
    assert "Alerts are switched off" not in _text(out)


def test_the_settings_badge_distinguishes_off_from_off_with_limits_set():
    """The badge is the other half: someone who set limits days ago and never
    revisits Devices should still see the contradiction on the Settings index."""
    from components.settings_panel import settings_badges

    nothing_watched = settings_badges({"notifications": {"enabled": False}})
    assert nothing_watched["alerts"] == ("Off", "secondary"), \
        "with no limits anywhere, alerts being off is a neutral fact"

    watched = settings_badges({
        "notifications": {"enabled": False},
        "alert_thresholds": {"P1": {"min": 1.0, "max": 5.0}}})
    label, colour = watched["alerts"]
    assert colour == "warning", "the one badge that must not read as settled"
    assert "off" in label.lower() and "limit" in label.lower(), label


def test_a_threshold_entry_with_no_bounds_does_not_count_as_watched():
    """An empty {} left behind by clearing a probe's limits is not a limit."""
    from components.settings_panel import settings_badges
    out = settings_badges({"notifications": {"enabled": False},
                           "alert_thresholds": {"P1": {}, "P2": None}})
    assert out["alerts"] == ("Off", "secondary")


def test_alerts_switched_on_is_unaffected_by_the_new_check():
    from components.settings_panel import settings_badges
    out = settings_badges({
        "notifications": {"enabled": True, "email": {"enabled": True,
                                                     "smtp_host": "smtp.x.com"}},
        "alert_thresholds": {"P1": {"max": 5.0}}})
    assert out["alerts"] == ("Email", "success")

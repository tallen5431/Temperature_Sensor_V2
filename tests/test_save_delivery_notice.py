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
    if isinstance(node, str):
        return node
    children = getattr(node, 'children', None)
    if isinstance(children, list):
        return ''.join(_text(c) for c in children)
    if children is not None:
        return _text(children)
    return ''


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

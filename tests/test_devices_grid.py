"""The Devices grid — the page an operator manages a probe from.

It used to show a name, an id, "via readings" and "Online", and nothing else:
not the current reading, not the range the probe is held to, not how often it
reports. Every question it raised had to be answered on the Dashboard, which
made the page that exists to look after probes the one page that could not tell
you how a probe was doing.

These pin the facts a card must carry, and two ways it previously lied.
"""
import datetime

import dash

from components.devices_panel import DevicesLayout, register_devices_callbacks
from core.db import Database


class _NoFinder:
    def list_probes(self):
        return {}


def _render(tmp_path, cfg=None, rows=(), held=None, unit="celsius", dbname="d.db"):
    """Render the real callback and return its list of cards."""
    from core.alerts import HELD
    HELD.set_states(held or {})
    db = Database(tmp_path / dbname)
    now = datetime.datetime.now()
    for pid, temp in rows:
        db.append(now.isoformat(timespec="milliseconds"), temp, temp * 9 / 5 + 32, pid)

    app = dash.Dash(__name__)
    app.layout = DevicesLayout
    app.config.suppress_callback_exceptions = True
    register_devices_callbacks(app, finder=_NoFinder(), cfg=cfg or {}, db=db)
    fn = app.callback_map["device-grid.children"]["callback"].__wrapped__
    return fn(0, unit)


def _text(node):
    """Flatten a Dash component tree to text. Handles a bare list, which is what
    the callback returns."""
    if isinstance(node, str):
        return node
    if isinstance(node, (int, float)):
        return str(node)
    if isinstance(node, (list, tuple)):
        return " ".join(_text(c) for c in node)
    children = getattr(node, "children", None)
    if children is not None:
        return _text(children)
    return ""


def _grid_text(*a, **kw):
    return _text(_render(*a, **kw))


def test_a_card_shows_the_current_reading(tmp_path):
    """The one fact someone opens this page to learn."""
    assert "3.4 °C" in _grid_text(tmp_path, rows=[("P1", 3.4)])


def test_a_card_shows_the_range_it_is_held_to(tmp_path):
    txt = _grid_text(tmp_path, cfg={"alert_thresholds": {"P1": {"min": 1.0, "max": 5.0}}},
                     rows=[("P1", 3.4)])
    assert "Alarm range" in txt
    assert "1.0" in txt and "5.0" in txt


def test_a_probe_with_no_threshold_says_so_rather_than_omitting_the_row(tmp_path):
    """An absent row reads as "this page does not know"; "not set" is a fact,
    and an unmonitored probe is worth noticing."""
    txt = _grid_text(tmp_path, rows=[("P1", 3.4)])
    assert "Alarm range" in txt and "not set" in txt


def test_reporting_cadence_is_shown_for_every_probe_not_only_overrides(tmp_path):
    """Only a per-probe OVERRIDE used to appear, so the common case — every
    probe on the global interval — displayed nothing at all."""
    txt = _grid_text(tmp_path, cfg={"interval_sec": 300}, rows=[("P1", 3.4)])
    assert "Reports" in txt and "every 5 minutes" in txt


def test_a_probe_in_breach_is_marked_on_its_card(tmp_path):
    """The alert engine holds the breach; the card has to show it, or the page
    displays a dangerous number in calm green."""
    txt = _grid_text(tmp_path, cfg={"alert_thresholds": {"P1": {"min": -22.0, "max": -15.0}}},
                     rows=[("P1", -8.0)], held={"P1": "high"})
    assert "ALARM" in txt


def test_a_healthy_probe_is_not_marked_alarm(tmp_path):
    txt = _grid_text(tmp_path, cfg={"alert_thresholds": {"P1": {"min": 1.0, "max": 5.0}}},
                     rows=[("P1", 3.4)])
    assert "OK" in txt and "ALARM" not in txt


def test_no_internal_jargon_reaches_the_customer(tmp_path):
    """'via readings' meant 'mDNS never saw this one' — an implementation
    detail, sitting in the identity slot of a customer-facing card."""
    assert "via readings" not in _grid_text(tmp_path, rows=[("P1", 3.4)])


def test_a_defaulted_port_is_never_presented_as_the_probes_port(tmp_path):
    """core.probes.probe_port falls back to 80, so a probe known only from its
    ingest posts rendered '127.0.0.1:80' — a port it never advertised."""
    assert ":80" not in _grid_text(tmp_path, rows=[("P1", 3.4)])


def test_calibration_offset_appears_only_when_one_is_set(tmp_path):
    assert "Calibration" not in _grid_text(tmp_path, rows=[("P1", 3.4)], dbname="a.db")
    with_cal = _grid_text(tmp_path, cfg={"calibration_offsets": {"P1": -0.3}},
                          rows=[("P1", 3.4)], dbname="b.db")
    assert "Calibration" in with_cal and "-0.30" in with_cal


def test_the_grid_renders_in_the_units_the_operator_chose(tmp_path):
    """temp-unit-store used to live in DashboardLayout, so this page had no id
    to read the preference from and always spoke Celsius."""
    assert "38.1 °F" in _grid_text(tmp_path, rows=[("P1", 3.4)], unit="fahrenheit")


def test_an_unmonitored_probe_is_not_called_ok(tmp_path):
    """"OK" means "inside its limits". A probe with no threshold has none, so
    nothing is checking it — and that is the case an operator most needs
    flagged, not the one that should look healthiest."""
    txt = _grid_text(tmp_path, rows=[("P1", 21.1)])
    assert "NO ALARM SET" in txt
    assert "OK" not in txt.replace("NO ALARM SET", "")

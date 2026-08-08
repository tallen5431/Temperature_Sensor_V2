"""Head office holds every store's readings but none of their configuration.

Thresholds, reporting intervals and calibration are per hub. The forwarder sends
readings and the store's own alert EVENTS (PROTOCOL.md §5.2); it does not send
config, and there is nowhere for it to go if it did. So head office re-deriving
alarms from forwarded readings applies its own settings to somebody else's
probes — and does it confidently:

  * an HQ that runs fridges (0..8 C) mailed a LOW alarm for every healthy store
    freezer sitting at -19 C;
  * a store probe on a 15-minute deep-sleep cadence was judged against HQ's own
    300 s window and called offline while it was working perfectly;
  * every genuine store breach landed in HQ's event log twice — once forwarded
    from the store, once re-derived here.

The store hub is the authority on its own probes. Head office aggregates and
displays; forwarded readings stay fully visible on the dashboard, chart, exports
and event log, they are simply not re-judged.

The first two are false alarms, which is the failure mode that matters most on an
alerting product: a head office whose mail is mostly wrong is a head office that
stops reading it, and that is how the real one gets missed.
"""
import datetime
import pathlib
import tempfile

import pytest
from flask import Flask

from alert_monitor import OWN_SITE, AlertMonitor
from api.routes import create_api
from core.alerts import evaluate_offline
from core.config import Config
from core.db import Database
from core.status import probe_fresh_window


class _NoDiscovery:
    def list_probes(self):
        return {}


def _hq(thresholds=None, **extra):
    """A head-office hub with an HTTP client, as a store would talk to it."""
    d = pathlib.Path(tempfile.mkdtemp())
    db, cfg = Database(d / "hq.db"), Config(d / "config.json")
    cfg.update({"provision_token": "s", "interval_sec": 5,
                "alert_thresholds": thresholds if thresholds is not None else {},
                "notifications": {"enabled": False, "offline_alerts": True},
                **extra})
    app = Flask(__name__)
    app.register_blueprint(create_api(cfg, db, _NoDiscovery(), lambda: "http://hq:8088", ""))
    return app.test_client(), db, cfg, AlertMonitor(db, cfg, notifier=None)


def _ago(seconds=0, minutes=0):
    return (datetime.datetime.now()
            - datetime.timedelta(seconds=seconds, minutes=minutes)
            ).isoformat(timespec="milliseconds")


def _forward(client, readings, events=(), site="store1"):
    body = {"readings": readings}
    if events:
        body["events"] = list(events)
    return client.post("/api/ingest_csv", json=body,
                       headers={"X-Site": site, "X-Token": "s"})


# --- the false alarms -------------------------------------------------------

def test_hq_does_not_alarm_on_a_healthy_store_freezer():
    """The headline case. Head office runs fridges; a store runs freezers. Every
    healthy store reading is a breach of HQ's limits and none of them are real."""
    client, _db, _cfg, hq = _hq({"default": {"min": 0.0, "max": 8.0}})
    hq.check_once()
    _forward(client, [{"probe_id": "S1-Freezer", "temperature_c": -19.0,
                       "timestamp": _ago(seconds=s)} for s in (120, 60, 5)])
    assert hq.check_once() == [], \
        "HQ judged a store freezer against its own fridge limits"


def test_hq_does_not_call_a_slow_store_probe_offline():
    """A 15-minute deep-sleep cadence is normal, and the store hub knows it
    because probe_intervals is its config. HQ has no entry for that probe, so it
    falls back to its own 300 s window and is wrong every single cycle."""
    d = pathlib.Path(tempfile.mkdtemp())
    store = Config(d / "store.json")
    store.update({"interval_sec": 5, "probe_intervals": {"S1-Freezer": 900}})
    hq_cfg = Config(d / "hq.json")
    hq_cfg.update({"interval_sec": 5})

    assert probe_fresh_window(store, "S1-Freezer") > 900, "the store knows the cadence"
    assert probe_fresh_window(hq_cfg, "S1-Freezer") == 300, "HQ does not, and cannot"

    import time
    now = time.time()
    healthy = {"S1-Freezer": now - 600}     # 10 min into a 15 min cadence
    seeded = {"S1-Freezer": "online"}

    store_events, _ = evaluate_offline(
        healthy, dict(seeded), now=now,
        offline_after_sec={"S1-Freezer": probe_fresh_window(store, "S1-Freezer")})
    assert store_events == [], "the store hub correctly says nothing"

    # ...and HQ must not be the one to say otherwise, which is why it no longer
    # looks at forwarded probes at all.
    hq_events, _ = evaluate_offline(
        healthy, dict(seeded), now=now,
        offline_after_sec={"S1-Freezer": probe_fresh_window(hq_cfg, "S1-Freezer")})
    assert [e["kind"] for e in hq_events] == ["offline"], \
        "if this stops being wrong, the scoping below is no longer load-bearing"


def test_a_forwarded_probe_is_not_in_hqs_offline_set():
    """The scoping that makes the previous test moot in practice."""
    client, db, _cfg, hq = _hq()
    _forward(client, [{"probe_id": "S1-Freezer", "temperature_c": -19.0,
                       "timestamp": _ago(seconds=5)}])
    assert db.last_reading_epoch_per_probe(site=OWN_SITE) == {}, \
        "a forwarded probe must not be in this hub's own offline tracking set"
    assert "S1-Freezer" in db.last_reading_epoch_per_probe(), \
        "...though it is still in the store, and still on every screen"
    hq.check_once()
    assert hq.check_once() == []


# --- the double-logging -----------------------------------------------------

@pytest.mark.parametrize("kind", ["high", "missed"])
def test_a_store_breach_lands_in_hqs_log_exactly_once(kind):
    """It arrived twice: forwarded from the store, and re-derived here from the
    same readings. `missed` is the one this could double most recently; `high`
    had been doing it for longer."""
    client, db, _cfg, hq = _hq({"default": {"min": -22.0, "max": -15.0}})
    hq.check_once()
    if kind == "missed":
        readings = [{"probe_id": "S1-Freezer",
                     "temperature_c": -8.0 if 2 <= m <= 15 else -19.0,
                     "timestamp": _ago(minutes=m)} for m in range(20, 0, -1)]
        when = _ago(minutes=15)
    else:
        readings = [{"probe_id": "S1-Freezer", "temperature_c": -8.0,
                     "timestamp": _ago(seconds=s)} for s in (120, 60, 5)]
        when = _ago(seconds=5)
    _forward(client, readings, events=[{"kind": kind, "probe_id": "S1-Freezer",
                                        "temperature_c": -8.0, "limit_c": -15.0,
                                        "ts": when}])
    hq.check_once()
    rows = [e for e in db.list_events(limit=20) if e["probe_id"] == "S1-Freezer"]
    assert len(rows) == 1, f"one incident, {len(rows)} rows in the log: {rows}"
    assert rows[0]["site"] == "store1", "and the surviving one is the store's own"


# --- what must NOT change ---------------------------------------------------

def test_hq_still_alerts_on_its_own_probes():
    """The scoping must not turn head office's own monitoring off — HQ has its
    own fridges, and it holds the right config for those."""
    client, _db, _cfg, hq = _hq({"default": {"min": 0.0, "max": 8.0}})
    hq.check_once()
    client.post("/api/ingest", json={"probe_id": "HQ-Fridge", "temperature_c": 14.0},
                headers={"X-Token": "s"})
    kinds = [e["kind"] for e in hq.check_once()]
    assert "high" in kinds


def test_a_store_hub_is_unaffected():
    """A single-site hub — every hub, until someone runs a roll-up — labels its own
    readings '', so scoping to '' changes nothing for it."""
    client, db, _cfg, hub = _hq({"default": {"min": 0.0, "max": 8.0}})
    hub.check_once()
    for s in (120, 60, 5):
        client.post("/api/ingest", json={"probe_id": "Local", "temperature_c": 14.0,
                                         "timestamp": _ago(seconds=s)},
                    headers={"X-Token": "s"})
    assert [e["kind"] for e in hub.check_once()] == ["high"]
    assert set(db.last_reading_epoch_per_probe(site=OWN_SITE)) == {"Local"}


def test_forwarded_readings_are_still_visible_everywhere_else():
    """Not judged is not hidden. The chart, the exports and the event log are the
    reason head office exists, and they are unchanged."""
    client, db, _cfg, _monitor = _hq()
    _forward(client, [{"probe_id": "S1-Freezer", "temperature_c": -19.0,
                       "timestamp": _ago(seconds=5)}])
    assert db.count() == 1
    assert "S1-Freezer" in db.last_reading_epoch_per_probe()
    assert "store1" in db.sites()
    import io
    buf = io.StringIO()
    db.export_csv(buf)
    assert "S1-Freezer" in buf.getvalue()


def test_the_sweep_asks_for_its_own_site():
    """Guards the seam directly: the three readers the alert paths use all pass
    OWN_SITE, and a fourth one added later without it re-opens all of this."""
    import ast
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "alert_monitor.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    wanted = {"latest_per_probe", "last_reading_epoch_per_probe", "readings_since_id"}
    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute) or fn.attr not in wanted:
            continue
        # The daily summary is a report, not an alert: it may legitimately span
        # every site, so only calls that pass `site` at all are pinned here.
        kwargs = {k.arg for k in node.keywords}
        if "site" not in kwargs:
            continue
        checked += 1
        site_arg = next(k.value for k in node.keywords if k.arg == "site")
        assert isinstance(site_arg, ast.Name) and site_arg.id == "OWN_SITE", \
            f"{fn.attr} passes a site that is not OWN_SITE"
    assert checked == 3, f"expected 3 site-scoped reads in the alert paths, found {checked}"


# --- and the same rule on the two pages -------------------------------------

def _card_text(cfg_dict, rows):
    """Render the Devices grid. ``rows`` is [(probe_id, temp_c, site)]."""
    import dash
    from components.devices_panel import DevicesLayout, register_devices_callbacks

    d = pathlib.Path(tempfile.mkdtemp())
    db = Database(d / "d.db")
    cfg = Config(d / "c.json")
    cfg.update(cfg_dict)
    now = datetime.datetime.now()
    for pid, temp, site in rows:
        db.append(now.isoformat(timespec="milliseconds"), temp, temp * 9 / 5 + 32,
                  pid, site=site)
    app = dash.Dash(__name__)
    app.layout = DevicesLayout
    app.config.suppress_callback_exceptions = True
    register_devices_callbacks(app, finder=_NoDiscovery(), cfg=cfg, db=db)
    fn = app.callback_map["device-grid.children"]["callback"].__wrapped__
    return _flatten(fn(0, "celsius")), cfg, db


def _flatten(node):
    if isinstance(node, (str, int, float)):
        return str(node)
    if isinstance(node, (list, tuple)):
        return " ".join(_flatten(c) for c in node)
    ch = getattr(node, "children", None)
    return _flatten(ch) if ch is not None else ""


def _dash_card_text(cfg, db):
    from components.dashboard_view import build_probe_cards
    return _flatten(build_probe_cards(db, cfg, "celsius"))


def test_both_pages_honour_the_default_threshold():
    """The alert engine resolves "this probe's entry, else `default`". The
    Dashboard card did too; the Devices card looked up the per-probe entry only.
    So one page said "▼ LOW" and the other "Alarm range not set" about the same
    probe — and the Devices answer is the dangerous direction, because it reads
    as "nothing is watching this" about a probe that will alarm."""
    cfgd = {"alert_thresholds": {"default": {"min": 0.0, "max": 8.0}}}
    devices, cfg, db = _card_text(cfgd, [("P1", 14.0, "")])
    dash_text = _dash_card_text(cfg, db)

    assert "not set" not in devices, "Devices ignored the default threshold"
    assert "8.0" in devices, "the range in effect has to be the one shown"
    assert "HIGH" in dash_text or "ALARM" in dash_text
    assert "ALARM" in devices or "HIGH" in devices, \
        "one page calling it a breach and the other calling it unmonitored is the bug"


def test_neither_page_judges_a_forwarded_probe():
    """Head office running fridges rendered every healthy store freezer as
    "▼ LOW" — its own limits applied to another hub's probe."""
    cfgd = {"alert_thresholds": {"default": {"min": 0.0, "max": 8.0}}}
    devices, cfg, db = _card_text(cfgd, [("S1-Freezer", -19.0, "store1")])
    dash_text = _dash_card_text(cfg, db)

    # Asserted positively: "NO ALARM SET" contains the substring "ALARM", so a
    # bare `not in` check passes for the wrong reason.
    assert "NO ALARM SET" in devices.upper(), \
        f"Devices judged a forwarded probe by this hub's limits: {devices}"
    assert "NO ALARM SET" in dash_text.upper(), \
        f"Dashboard judged a forwarded probe by this hub's limits: {dash_text}"
    for where, text in (("Devices", devices), ("Dashboard", dash_text)):
        assert "LOW" not in text.upper().replace("NO ALARM SET", ""), \
            f"{where} still rendered a breach verdict"
    assert "-19" in devices and "-19" in dash_text, \
        "the reading itself must still be shown — not judged is not hidden"


def test_limits_for_is_the_single_resolution_rule():
    from core.status import limits_for
    cfg = {"alert_thresholds": {"P1": {"min": 1.0, "max": 5.0},
                                "default": {"min": 0.0, "max": 8.0}}}
    assert limits_for(cfg, "P1") == {"min": 1.0, "max": 5.0}, "own entry wins"
    assert limits_for(cfg, "P2") == {"min": 0.0, "max": 8.0}, "else the default"
    assert limits_for(cfg, "P1", site="store1") == {}, \
        "a forwarded probe is judged by the hub that owns it, not this one"
    assert limits_for({}, "P1") == {}

"""Background workers that get switched on and off at runtime.

Each of these is something the UI now starts and stops while the hub keeps
running — a Wi-Fi scan gated on a Settings section, an MQTT publisher restarted
on Save, a forwarder draining a backlog. All three had a defect that only shows
on the SECOND cycle, which is exactly the case a start-it-once test never reaches.
"""
import threading
import time

import pytest


# --- SSIDWatcher: start -> stop -> start ------------------------------------

def test_watcher_can_be_restarted_after_being_stopped(monkeypatch):
    """The scan is now tied to a Settings section being open, so it is started
    and stopped repeatedly. A stop flag that is never cleared makes every
    restart spawn a thread that exits before its first scan — a watcher that
    looks running, reports nothing, and can never be revived."""
    import wifi_scan

    scans = []
    seen = threading.Event()

    def _fake_scan():
        scans.append(1)
        seen.set()
        return {"Setpoint-9A3F2C", "HomeWifi"}

    monkeypatch.setattr(wifi_scan, "scan_ssids", _fake_scan)
    w = wifi_scan.SSIDWatcher("Setpoint", interval_sec=0.02)

    w.start()
    assert seen.wait(2.0), "first start never scanned"
    assert w.matched() == ["Setpoint-9A3F2C"]

    w.stop()
    assert w.latest == set(), "a stale sighting must not survive a stop"

    seen.clear()
    before = len(scans)
    w.start()
    assert seen.wait(2.0), "restart never scanned — the stop flag was not cleared"
    assert len(scans) > before
    assert w.matched() == ["Setpoint-9A3F2C"]
    w.stop()


def test_stopping_interrupts_the_sleep_rather_than_waiting_it_out(monkeypatch):
    """stop() has to take effect now, not after up to one full interval of
    further shelling out to netsh/nmcli."""
    import wifi_scan

    monkeypatch.setattr(wifi_scan, "scan_ssids", lambda: set())
    w = wifi_scan.SSIDWatcher("Setpoint", interval_sec=30.0)
    w.start()
    time.sleep(0.1)
    assert w.running()
    w.stop()
    # Join the REAL thread, not the running() flag: with time.sleep(interval) it
    # would sit there for another 30 s still holding a scan subprocess slot.
    w._th.join(timeout=3.0)
    assert not w._th.is_alive(), "the watcher thread outlived stop() by a whole interval"
    assert not w.running()


def test_starting_twice_does_not_stack_threads(monkeypatch):
    import wifi_scan

    monkeypatch.setattr(wifi_scan, "scan_ssids", lambda: set())
    w = wifi_scan.SSIDWatcher("Setpoint", interval_sec=5.0)
    w.start()
    first = w._th
    w.start()
    assert w._th is first
    w.stop()


# --- MQTT: Save does stop() then start() ------------------------------------

def test_saving_new_mqtt_topics_re_announces_every_probe():
    """Settings Save restarts the publisher. Home Assistant learns a probe's
    state topic from a RETAINED discovery message, so a changed base_topic
    leaves HA subscribed to the old topic; unless the restart re-announces,
    every existing sensor goes stale until the hub is restarted."""
    from core.mqtt_publish import MqttPublisher, state_topic

    published = []

    class _Client:
        def publish(self, topic, payload=None, retain=False):
            published.append((topic, retain))

        def loop_stop(self):
            pass

        def disconnect(self):
            pass

    pub = MqttPublisher()
    pub._client, pub._enabled = _Client(), True
    pub._base_topic, pub._discovery_enabled = "setpoint", True

    pub.publish_reading("Setpoint-9A3F", 4.0, "Walk-in")
    announces = [t for t, retain in published if retain]
    assert len(announces) == 1, "first reading should announce the probe"

    # A second reading must NOT re-announce while nothing has changed.
    published.clear()
    pub.publish_reading("Setpoint-9A3F", 4.1, "Walk-in")
    assert [t for t, retain in published if retain] == []

    # ...but a restart with a new base topic must.
    pub.stop()
    published.clear()
    pub._client, pub._enabled = _Client(), True
    pub._base_topic = "coldstore"
    pub.publish_reading("Setpoint-9A3F", 4.2, "Walk-in")
    assert [t for t, retain in published if retain], \
        "changing the base topic left Home Assistant pointed at the old one"
    assert (state_topic("coldstore", "Setpoint-9A3F"), False) in published


def test_stop_clears_the_announce_cap_flag():
    from core.mqtt_publish import MqttPublisher

    pub = MqttPublisher()
    pub._announced = {"x:temperature"}
    pub._announce_capped = True
    pub.stop()
    assert pub._announced == set() and pub._announce_capped is False


# --- Forwarder: draining a backlog ------------------------------------------

@pytest.mark.parametrize("configured,expected", [
    (None, 500),        # unset -> DEFAULT_BATCH
    (100, 100),
    (0, 500),           # falsy -> default
    (5000, 1000),       # clamped to the protocol cap
    ("abc", 500),       # junk from a hand-edited config
])
def test_batch_size_is_one_definition(configured, expected):
    """One clamp for the row limit, whatever a hand-edited config holds.

    The end-to-end behaviour this feeds — a full batch draining at one second
    instead of a whole interval, for readings OR events — is driven through the
    real ``run()`` loop in test_forwarder.py; this only pins the clamp itself.
    """
    from core.forwarder import batch_size

    block = {} if configured is None else {"batch": configured}
    assert batch_size(block) == expected

from core.mqtt_publish import (
    state_topic,
    discovery_topic,
    discovery_payload,
    MqttPublisher,
)


def test_topics():
    assert state_topic("setpoint", "Setpoint-1") == "setpoint/Setpoint-1/state"
    assert state_topic("setpoint/", "Setpoint-1") == "setpoint/Setpoint-1/state"
    assert discovery_topic("homeassistant", "Setpoint-9A3F2C") == \
        "homeassistant/sensor/setpoint_Setpoint_9A3F2C_temperature/config"
    assert discovery_topic("homeassistant", "Setpoint-9A3F2C", "humidity") == \
        "homeassistant/sensor/setpoint_Setpoint_9A3F2C_humidity/config"


def test_discovery_payload_is_valid_ha_temperature_sensor():
    p = discovery_payload("Setpoint-9A3F2C", "Kitchen Fridge", "setpoint")
    assert p["device_class"] == "temperature"
    assert p["unit_of_measurement"] == "°C"
    assert p["state_class"] == "measurement"
    assert p["unique_id"] == "setpoint_Setpoint-9A3F2C_temperature"
    assert p["state_topic"] == "setpoint/Setpoint-9A3F2C/state"
    assert p["value_template"] == "{{ value_json.temperature_c }}"
    assert p["device"]["manufacturer"] == "Setpoint"


def test_discovery_payloads_for_humidity_and_vpd():
    h = discovery_payload("P1", "Tent", "setpoint", "humidity")
    assert h["device_class"] == "humidity"
    assert h["unit_of_measurement"] == "%"
    assert h["value_template"] == "{{ value_json.humidity_pct }}"
    v = discovery_payload("P1", "Tent", "setpoint", "vpd")
    assert "device_class" not in v          # VPD has no HA device_class
    assert v["unit_of_measurement"] == "kPa"
    assert v["value_template"] == "{{ value_json.vpd_kpa }}"


def test_publish_is_noop_when_disabled():
    pub = MqttPublisher()  # never started → no client
    # Must not raise even though nothing is connected.
    pub.publish_reading("Setpoint-1", 20.0, "x")


class _FakeCfg:
    def __init__(self, d):
        self._d = d

    def get(self, k, default=None):
        return self._d.get(k, default)


def test_start_disabled_by_config_does_nothing():
    pub = MqttPublisher()
    pub.start(_FakeCfg({"mqtt": {"enabled": False}}))
    pub.publish_reading("Setpoint-1", 20.0, "x")  # still a no-op, no crash
    assert pub.is_ready() is False


class _RecordingClient:
    def __init__(self):
        self.published = []

    def username_pw_set(self, *a, **k):
        pass

    def connect(self, *a, **k):
        pass

    def loop_start(self):
        pass

    def publish(self, topic, payload, retain=False):
        self.published.append(topic)


def test_start_coerces_null_topic_and_string_discovery_flag(monkeypatch):
    # Regression: a hand-edited config with base_topic=null and a string
    # discovery flag must not silently kill publishing. Null base_topic must
    # fall back to "setpoint" (not None, which crashed every publish on
    # None.rstrip()), and discovery_enabled="false" must read as False, not
    # truthy. Uses a fake paho client so no broker is needed.
    import paho.mqtt.client as mqtt_mod
    fake = _RecordingClient()
    monkeypatch.setattr(mqtt_mod, "Client", lambda *a, **k: fake)

    pub = MqttPublisher()
    pub.start(_FakeCfg({"mqtt": {"enabled": True, "host": "localhost",
                                 "base_topic": None, "discovery_prefix": "",
                                 "discovery_enabled": "false"}}))
    assert pub.is_ready() is True
    assert pub._base_topic == "setpoint"          # null -> default, not None
    assert pub._discovery_prefix == "homeassistant"  # empty -> default
    assert pub._discovery_enabled is False         # "false" -> off, not truthy

    # Publishing now actually reaches the broker (would have silently crashed
    # on None.rstrip() before), and no discovery entity is announced.
    pub.publish_reading("Setpoint-1", 20.0, "Fridge")
    assert fake.published == ["setpoint/Setpoint-1/state"]


class _FakeClient:
    def loop_stop(self):
        pass

    def disconnect(self):
        pass


def test_is_ready_reflects_connection_state():
    pub = MqttPublisher()
    assert pub.is_ready() is False        # never started
    with pub._lock:                        # simulate a successful start()
        pub._client = _FakeClient()
        pub._enabled = True
    assert pub.is_ready() is True
    pub.stop()
    assert pub.is_ready() is False        # stop() tears the connection down

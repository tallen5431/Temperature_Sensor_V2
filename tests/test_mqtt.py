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

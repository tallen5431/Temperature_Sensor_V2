from core.mqtt_publish import (
    state_topic,
    discovery_topic,
    discovery_payload,
    MqttPublisher,
)


def test_topics():
    assert state_topic("thermahub", "ThermaProbe-1") == "thermahub/ThermaProbe-1/state"
    assert state_topic("thermahub/", "ThermaProbe-1") == "thermahub/ThermaProbe-1/state"
    assert discovery_topic("homeassistant", "ThermaProbe-9A3F2C") == \
        "homeassistant/sensor/thermahub_ThermaProbe_9A3F2C_temperature/config"
    assert discovery_topic("homeassistant", "ThermaProbe-9A3F2C", "humidity") == \
        "homeassistant/sensor/thermahub_ThermaProbe_9A3F2C_humidity/config"


def test_discovery_payload_is_valid_ha_temperature_sensor():
    p = discovery_payload("ThermaProbe-9A3F2C", "Kitchen Fridge", "thermahub")
    assert p["device_class"] == "temperature"
    assert p["unit_of_measurement"] == "°C"
    assert p["state_class"] == "measurement"
    assert p["unique_id"] == "thermahub_ThermaProbe-9A3F2C_temperature"
    assert p["state_topic"] == "thermahub/ThermaProbe-9A3F2C/state"
    assert p["value_template"] == "{{ value_json.temperature_c }}"
    assert p["device"]["manufacturer"] == "ThermaHub"


def test_discovery_payloads_for_humidity_and_vpd():
    h = discovery_payload("P1", "Tent", "thermahub", "humidity")
    assert h["device_class"] == "humidity"
    assert h["unit_of_measurement"] == "%"
    assert h["value_template"] == "{{ value_json.humidity_pct }}"
    v = discovery_payload("P1", "Tent", "thermahub", "vpd")
    assert "device_class" not in v          # VPD has no HA device_class
    assert v["unit_of_measurement"] == "kPa"
    assert v["value_template"] == "{{ value_json.vpd_kpa }}"


def test_publish_is_noop_when_disabled():
    pub = MqttPublisher()  # never started → no client
    # Must not raise even though nothing is connected.
    pub.publish_reading("ThermaProbe-1", 20.0, "x")


class _FakeCfg:
    def __init__(self, d):
        self._d = d

    def get(self, k, default=None):
        return self._d.get(k, default)


def test_start_disabled_by_config_does_nothing():
    pub = MqttPublisher()
    pub.start(_FakeCfg({"mqtt": {"enabled": False}}))
    pub.publish_reading("ThermaProbe-1", 20.0, "x")  # still a no-op, no crash

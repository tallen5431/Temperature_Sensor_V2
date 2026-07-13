# core/mqtt_publish.py
"""Optional MQTT publishing with Home Assistant auto-discovery.

For the homelab / self-hosted beachhead, publishing readings to MQTT with HA
discovery means each probe shows up automatically as a sensor in Home Assistant
(and anything else on the bus) with zero manual config — the integration that
turns "another dashboard" into "part of my stack".

Disabled by default. Enable via the `mqtt` config block. paho-mqtt is imported
lazily so the base install stays lean and a missing package degrades to a clear
warning instead of a crash.
"""
from __future__ import annotations

import json
import threading

from core.applog import get_logger

log = get_logger("mqtt")


def state_topic(base_topic: str, probe_id: str) -> str:
    return f"{base_topic.rstrip('/')}/{probe_id}/state"


# Per-metric Home Assistant sensor definitions. Each reads the same state JSON.
_METRICS = {
    "temperature": {"field": "temperature_c", "unit": "°C", "device_class": "temperature", "label": "Temperature"},
    "humidity": {"field": "humidity_pct", "unit": "%", "device_class": "humidity", "label": "Humidity"},
    "vpd": {"field": "vpd_kpa", "unit": "kPa", "device_class": None, "label": "VPD"},
}


def discovery_topic(discovery_prefix: str, probe_id: str, metric: str = "temperature") -> str:
    # HA object_id must be unique per entity and use only safe chars.
    node = probe_id.replace("-", "_")
    return f"{discovery_prefix.rstrip('/')}/sensor/tempsensor_{node}_{metric}/config"


def discovery_payload(probe_id: str, friendly_name: str, base_topic: str, metric: str = "temperature") -> dict:
    """Home Assistant MQTT-discovery config for one metric of one probe."""
    m = _METRICS[metric]
    name = friendly_name or probe_id
    payload = {
        "name": f"{name} {m['label']}",
        "unique_id": f"tempsensor_{probe_id}_{metric}",
        "state_topic": state_topic(base_topic, probe_id),
        "value_template": f"{{{{ value_json.{m['field']} }}}}",
        "unit_of_measurement": m["unit"],
        "state_class": "measurement",
        "expire_after": 120,
        "device": {
            "identifiers": [f"tempsensor_{probe_id}"],
            "name": name,
            "manufacturer": "TempSensor",
            "model": "TempSensor",
        },
    }
    if m["device_class"]:
        payload["device_class"] = m["device_class"]
    return payload


class MqttPublisher:
    def __init__(self) -> None:
        self._client = None
        self._lock = threading.Lock()
        self._enabled = False
        self._base_topic = "tempsensor"
        self._discovery_prefix = "homeassistant"
        self._discovery_enabled = True
        self._announced: set[str] = set()

    def start(self, cfg) -> None:
        m = (cfg.get("mqtt", {}) or {})
        if not m.get("enabled"):
            return
        try:
            import paho.mqtt.client as mqtt  # lazy import
        except Exception:
            log.warning("mqtt.enabled is true but paho-mqtt is not installed "
                        "(`pip install paho-mqtt`); MQTT publishing is off.")
            return

        self._base_topic = m.get("base_topic", "tempsensor")
        self._discovery_prefix = m.get("discovery_prefix", "homeassistant")
        self._discovery_enabled = bool(m.get("discovery_enabled", True))
        try:
            client = mqtt.Client()
            if m.get("username"):
                client.username_pw_set(m.get("username"), m.get("password", ""))
            client.connect(m.get("host", "localhost"), int(m.get("port", 1883)), keepalive=60)
            client.loop_start()
            with self._lock:
                self._client = client
                self._enabled = True
            log.info("MQTT publishing enabled -> %s:%s (base topic '%s')",
                     m.get("host"), m.get("port", 1883), self._base_topic)
        except Exception as e:
            log.warning("Could not connect to MQTT broker: %s", e)

    def publish_reading(self, probe_id: str, temp_c: float, friendly_name: str = "",
                        humidity: float | None = None, vpd: float | None = None) -> None:
        with self._lock:
            client, enabled = self._client, self._enabled
        if not (enabled and client and probe_id):
            return
        try:
            metrics = ["temperature"]
            if humidity is not None:
                metrics.append("humidity")
            if vpd is not None:
                metrics.append("vpd")
            # Announce each metric once per (probe, metric) so a probe that later
            # gains humidity still gets its humidity/VPD entities in HA. Guard the
            # check-then-add with the lock so concurrent worker threads don't both
            # publish the same discovery entity (the set is otherwise read/mutated
            # off-lock). The lock only does fast set lookups after the one-time
            # first announce, and the hot state publish below stays lock-free.
            if self._discovery_enabled:
                with self._lock:
                    for metric in metrics:
                        key = f"{probe_id}:{metric}"
                        if key not in self._announced:
                            client.publish(
                                discovery_topic(self._discovery_prefix, probe_id, metric),
                                json.dumps(discovery_payload(probe_id, friendly_name, self._base_topic, metric)),
                                retain=True,
                            )
                            self._announced.add(key)
            state = {"temperature_c": round(float(temp_c), 3), "probe_id": probe_id}
            if humidity is not None:
                state["humidity_pct"] = round(float(humidity), 2)
            if vpd is not None:
                state["vpd_kpa"] = round(float(vpd), 3)
            client.publish(state_topic(self._base_topic, probe_id), json.dumps(state), retain=False)
        except Exception as e:
            log.debug("MQTT publish failed for %s: %s", probe_id, e)

    def stop(self) -> None:
        with self._lock:
            client = self._client
            self._client = None
            self._enabled = False
        if client:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass


MQTT = MqttPublisher()

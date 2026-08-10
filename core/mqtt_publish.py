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

# Ceiling on distinct (probe, metric) pairs we will announce to Home Assistant.
# Mirrors probe_discovery._MAX_PROBES and exists for the same reason it does: a
# probe id comes from an X-Probe-ID header on the open-by-default ingest API and
# sanitizes to 32 chars of [A-Za-z0-9_-], so its cardinality is effectively
# unbounded. Each NOVEL id publishes a discovery entity with retain=True, and a
# retained message outlives the hub, the broker restart, and the flood itself --
# so an id flood does not just grow this set, it permanently litters the user's
# Home Assistant with phantom entities they must hand-clear. Far above any real
# deployment (512 probes x 3 metrics).
_MAX_ANNOUNCED = 1536


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
    return f"{discovery_prefix.rstrip('/')}/sensor/setpoint_{node}_{metric}/config"


def discovery_payload(probe_id: str, friendly_name: str, base_topic: str, metric: str = "temperature") -> dict:
    """Home Assistant MQTT-discovery config for one metric of one probe."""
    m = _METRICS[metric]
    name = friendly_name or probe_id
    payload = {
        "name": f"{name} {m['label']}",
        "unique_id": f"setpoint_{probe_id}_{metric}",
        "state_topic": state_topic(base_topic, probe_id),
        "value_template": f"{{{{ value_json.{m['field']} }}}}",
        "unit_of_measurement": m["unit"],
        "state_class": "measurement",
        "expire_after": 120,
        "device": {
            "identifiers": [f"setpoint_{probe_id}"],
            "name": name,
            "manufacturer": "Setpoint",
            "model": "Setpoint",
        },
    }
    if m["device_class"]:
        payload["device_class"] = m["device_class"]
    return payload


# How long start() waits for CONNACK before returning. Long enough for a broker
# on the LAN or a nearby host, short enough not to stall the Settings save (or
# hub boot) on one that is not answering.
CONNECT_WAIT_SEC = 2.0


class MqttPublisher:
    def __init__(self) -> None:
        self._client = None
        self._lock = threading.Lock()
        self._enabled = False
        self._base_topic = "setpoint"
        self._discovery_prefix = "homeassistant"
        self._discovery_enabled = True
        self._announced: set[str] = set()
        self._announce_capped = False
        # Set by the CONNACK callback. start() waits on it briefly so a caller
        # that reports readiness immediately afterwards - Settings' Save does,
        # on the very next line - is not told a healthy broker is broken.
        self._connected_evt = threading.Event()

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

        # Defensive against a hand-edited config (this module's threat model):
        # `or` — not a key-missing default — so a present-but-null or empty
        # base_topic/prefix falls back instead of becoming None (which would
        # crash every publish on None.rstrip() and silently disable the whole
        # integration). discovery_enabled likewise honours a string "false"/"off"
        # rather than reading any non-empty string as truthy via bool().
        self._base_topic = m.get("base_topic") or "setpoint"
        self._discovery_prefix = m.get("discovery_prefix") or "homeassistant"
        de = m.get("discovery_enabled", True)
        if isinstance(de, str):
            de = de.strip().lower() not in ("0", "false", "no", "off", "")
        self._discovery_enabled = bool(de)
        try:
            client = mqtt.Client()
            # connect() below completes the TCP handshake and sends CONNECT --
            # it does NOT wait for CONNACK, so a broker that refuses the
            # credentials says so later, on the network loop. Without these the
            # refusal is never observed anywhere: publish() on a disconnected
            # client RETURNS an error code rather than raising, so
            # publish_reading's except never fires either, and Settings sat on
            # a green "publishing to <host>" while nothing was.
            def _on_connect(_client, _userdata, _flags, rc, *_a):
                if rc == 0:
                    self._connected_evt.set()
                else:
                    log.warning("MQTT broker refused the connection (%s) — check the "
                                "host, port and credentials; readings are NOT being "
                                "published.", mqtt.connack_string(rc))

            def _on_disconnect(_client, _userdata, rc, *_a):
                if rc != 0:
                    log.warning("MQTT connection lost (code %s); paho will retry.", rc)

            client.on_connect = _on_connect
            client.on_disconnect = _on_disconnect
            if m.get("username"):
                client.username_pw_set(m.get("username"), m.get("password", ""))
            self._connected_evt.clear()
            client.connect(m.get("host", "localhost"), int(m.get("port", 1883)), keepalive=60)
            client.loop_start()
            # connect() returns once the TCP handshake is done and CONNECT is
            # queued; CONNACK arrives on the network loop a moment later. Wait
            # for it, bounded, so is_ready() means something to whoever asks
            # next. Outside the lock - nothing may block a publish - and a
            # timeout is not a failure: paho keeps retrying, and is_ready()
            # will start answering True when it lands.
            self._connected_evt.wait(CONNECT_WAIT_SEC)
            with self._lock:
                self._client = client
                self._enabled = True
            log.info("MQTT publishing enabled -> %s:%s (base topic '%s')",
                     m.get("host"), m.get("port", 1883), self._base_topic)
        except Exception as e:
            log.warning("Could not connect to MQTT broker: %s", e)

    def is_ready(self) -> bool:
        """True when a broker connection is up and readings will be published.

        Asks the client, rather than trusting that ``start()`` got that far.
        ``connect()`` returns before CONNACK, so "start() did not raise" only
        means the TCP handshake worked — a wrong username, a wrong port with
        something else listening, or an ACL rejection all produced a client that
        reported ready and published nothing. This is the one place Settings
        reads to tell the operator MQTT is working, so it has to mean it.

        A stand-in client without ``is_connected`` (tests, a future transport)
        is taken at face value: the honesty being restored is about the real
        paho client, not about inventing a failure for an object that cannot
        report one.
        """
        with self._lock:
            client, enabled = self._client, self._enabled
        if not (enabled and client is not None):
            return False
        probe = getattr(client, "is_connected", None)
        if probe is None:
            return True
        try:
            return bool(probe())
        except Exception:  # noqa: BLE001 - a status readout must never raise
            return False

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
                        if key in self._announced:
                            continue
                        # Stop announcing rather than evicting: eviction would let
                        # an already-seen probe re-announce on its next reading,
                        # turning a bounded set into an unbounded stream of
                        # retained publishes -- worse than the leak it fixes.
                        # Readings keep flowing below; only the HA entity is
                        # skipped, and only past a count no real fleet reaches.
                        if len(self._announced) >= _MAX_ANNOUNCED:
                            if not self._announce_capped:
                                self._announce_capped = True
                                log.warning(
                                    "MQTT discovery announcements capped at %d distinct "
                                    "(probe, metric) pairs; new probes will publish "
                                    "readings but will not appear in Home Assistant. "
                                    "This usually means unknown probe ids are reaching "
                                    "/api/ingest.", _MAX_ANNOUNCED)
                            continue
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
            # Forget what has been announced. Saving Settings does stop() then
            # start(), so a changed base_topic or discovery_prefix produces a
            # publisher writing to new topics — while Home Assistant still
            # subscribes to the old ones from the retained discovery config.
            # Every existing probe's sensor would go stale (and stay stale until
            # the hub was restarted) because it had already been announced and
            # was therefore never announced again. Clearing here means the next
            # reading re-announces each probe against the topics now in effect.
            self._announced.clear()
            self._announce_capped = False
        if client:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass


MQTT = MqttPublisher()

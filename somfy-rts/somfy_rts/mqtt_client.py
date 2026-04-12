"""MQTT Client: Verbindung, HA Discovery (Gateway + Geräte, Modus A/B) und Command Handling.

Discovery-Struktur:
  Gateway-Device (diagnostisch):
    - sensor: Verbindungsstatus, USB-Port, Geräteanzahl, SW-Version

  Sub-Device pro Gerät (via_device: Gateway):
    Modus A: cover entity (optimistisch, device_class je Gerätetyp)
    Modus B: 3x button (entity_category: config)
             + 2x sensor: rolling_code, letzter_befehl (entity_category: diagnostic)

Availability: LWT auf Topic 'cul2mqtt/status' (online/offline, retain=True).
Origin-Block in allen Discovery-Payloads.
"""

import json
import logging
import time
from typing import Callable, Dict, Optional

import paho.mqtt.client as mqtt

from . import __version__
from .config import Config, DeviceConfig

logger = logging.getLogger(__name__)

HA_DISCOVERY = "homeassistant"
LWT_TOPIC = "cul2mqtt/status"
GW_TOPIC_BASE = "cul2mqtt/gateway"
MQTT_TOPIC_PREFIX = "somfy"

ORIGIN = {
    "name": "Somfy RTS",
    "support_url": "https://github.com/isi07/hassio-somfy-rts",
}

# Kein hardcodiertes device_class-Mapping hier — kommt aus device_profiles.json via profile-Parameter

_GW_DEVICE = {
    "identifiers": ["somfy_rts_gateway"],
    "name": "Somfy RTS Gateway",
    "model": "NanoCUL (culfw)",
    "manufacturer": "culfw",
    "sw_version": __version__,
}


class MQTTClient:
    """Verwaltet MQTT-Verbindung, HA Discovery und Command-Dispatch."""

    def __init__(self, config: Config):
        self._config = config
        self._client = mqtt.Client(client_id="somfy_rts_addon", clean_session=True)
        self._handlers: Dict[str, Callable[[str], None]] = {}

        if config.mqtt_user:
            self._client.username_pw_set(config.mqtt_user, config.mqtt_password)

        # LWT: wird automatisch bei ungeplanter Trennung veröffentlicht
        self._client.will_set(LWT_TOPIC, "offline", retain=True)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

    # ---------- Verbindung ----------

    def connect(self) -> None:
        logger.info("Verbinde mit MQTT %s:%d ...", self._config.mqtt_host, self._config.mqtt_port)
        self._client.connect(
            self._config.mqtt_host,
            self._config.mqtt_port,
            keepalive=60,
        )
        self._client.loop_start()
        deadline = time.time() + 10
        while not self._client.is_connected() and time.time() < deadline:
            time.sleep(0.1)
        if not self._client.is_connected():
            raise RuntimeError("MQTT Verbindung fehlgeschlagen (Timeout 10s).")
        self._client.publish(LWT_TOPIC, "online", retain=True)

    def disconnect(self) -> None:
        self._client.publish(LWT_TOPIC, "offline", retain=True)
        time.sleep(0.2)
        self._client.loop_stop()
        self._client.disconnect()

    # ---------- Gateway Discovery ----------

    def register_gateway(self, port_name: str, device_count: int) -> None:
        """Veröffentlicht HA Discovery für das Gateway-Gerät (4 Diagnose-Sensoren)."""
        avail = _avail_block()

        sensor_defs = [
            ("status",       "Verbindung",   f"{GW_TOPIC_BASE}/status",       "mdi:lan-connect", None),
            ("port",         "USB-Port",     f"{GW_TOPIC_BASE}/port",          "mdi:usb",         None),
            ("device_count", "Geräte",       f"{GW_TOPIC_BASE}/device_count",  "mdi:counter",     None),
            ("sw_version",   "SW-Version",   f"{GW_TOPIC_BASE}/sw_version",    "mdi:tag",         None),
        ]

        for sensor_id, sensor_name, state_topic, icon, unit in sensor_defs:
            payload: Dict = {
                "name": sensor_name,
                "unique_id": f"somfy_rts_gw_{sensor_id}",
                "state_topic": state_topic,
                "entity_category": "diagnostic",
                "icon": icon,
                "availability": avail,
                "device": _GW_DEVICE,
                "origin": ORIGIN,
            }
            if unit:
                payload["unit_of_measurement"] = unit
            disc_topic = f"{HA_DISCOVERY}/sensor/somfy_rts_gw_{sensor_id}/config"
            self._client.publish(disc_topic, json.dumps(payload), retain=True)

        # Initiale Werte
        self._client.publish(f"{GW_TOPIC_BASE}/status",       "Verbunden",       retain=True)
        self._client.publish(f"{GW_TOPIC_BASE}/port",         port_name,         retain=True)
        self._client.publish(f"{GW_TOPIC_BASE}/device_count", str(device_count), retain=True)
        self._client.publish(f"{GW_TOPIC_BASE}/sw_version",   __version__,       retain=True)
        logger.info("Gateway Discovery veröffentlicht (%d Gerät(e)).", device_count)

    def update_gateway_status(self, status: str) -> None:
        self._client.publish(f"{GW_TOPIC_BASE}/status", status, retain=True)

    # ---------- Geräte-Registration ----------

    def register_device(
        self,
        device: DeviceConfig,
        command_handler: Callable[[str], None],
        profile: Optional[Dict] = None,
    ) -> None:
        """Registriert ein Gerät via HA Discovery — Modus A oder B.

        Args:
            profile: Geräte-Profil aus device_profiles.json (device_class, icons, button-labels).
                     Wenn None, werden generische Defaults verwendet.
        """
        if device.mode == "B":
            self._register_mode_b(device, command_handler, profile or {})
        else:
            self._register_mode_a(device, command_handler, profile or {})

    def _register_mode_a(
        self,
        device: DeviceConfig,
        command_handler: Callable[[str], None],
        profile: Dict,
    ) -> None:
        """Modus A: Optimistisches MQTT Cover-Entity.
        device_class kommt aus dem Profil (device_profiles.json).
        """
        prefix = MQTT_TOPIC_PREFIX
        slug = device.slug
        state_topic = f"{prefix}/{slug}/state"
        command_topic = f"{prefix}/{slug}/set"

        payload: Dict = {
            "name": device.name,
            "unique_id": f"{device.unique_id_base}_cover",
            "state_topic": state_topic,
            "command_topic": command_topic,
            "payload_open": "OPEN",
            "payload_close": "CLOSE",
            "payload_stop": "STOP",
            "state_open": "open",
            "state_closed": "closed",
            "state_stopped": "stopped",
            "optimistic": True,
            "availability": _avail_block(),
            "device": _sub_device(device, profile),
            "origin": ORIGIN,
        }
        device_class = profile.get("device_class")
        if device_class:
            payload["device_class"] = device_class

        disc_topic = f"{HA_DISCOVERY}/cover/{device.unique_id_base}/config"
        self._client.publish(disc_topic, json.dumps(payload), retain=True)

        self._subscribe(command_topic, command_handler)
        logger.info("[Modus A] '%s' → Cover auf %s", device.name, command_topic)

    def _register_mode_b(
        self,
        device: DeviceConfig,
        command_handler: Callable[[str], None],
        profile: Dict,
    ) -> None:
        """Modus B: 3 Button-Entities (config) + 2 Diagnose-Sensoren.
        Button-Labels und Icons kommen aus device_profiles.json.
        """
        prefix = MQTT_TOPIC_PREFIX
        slug = device.slug
        sub_dev = _sub_device(device, profile)
        avail = _avail_block()

        # 3 Buttons: open / close / stop — Labels/Icons aus Profil
        buttons = profile.get("buttons", {})
        for action_key, btn_key in [("auf", "open"), ("zu", "close"), ("stop", "stop")]:
            btn = buttons.get(btn_key, {})
            label = btn.get("label", action_key.title())
            icon = btn.get("icon", "mdi:remote")
            rts_action = btn.get("rts", action_key.upper())

            cmd_topic = f"{prefix}/{slug}/button/{action_key}"
            payload = {
                "name": f"{device.name} {label}",
                "unique_id": f"{device.unique_id_base}_btn_{action_key}",
                "command_topic": cmd_topic,
                "payload_press": "PRESS",
                "entity_category": "config",
                "icon": icon,
                "availability": avail,
                "device": sub_dev,
                "origin": ORIGIN,
            }
            disc_topic = f"{HA_DISCOVERY}/button/{device.unique_id_base}_{action_key}/config"
            self._client.publish(disc_topic, json.dumps(payload), retain=True)

            self._subscribe(cmd_topic, lambda _payload, a=rts_action: command_handler(a))

        # 2 Diagnose-Sensoren: rolling_code + letzter_befehl
        for sensor_id, sensor_name, icon in [
            ("rolling_code", "Rolling Code",   "mdi:counter"),
            ("last_command", "Letzter Befehl", "mdi:history"),
        ]:
            state_topic = f"{prefix}/{slug}/{sensor_id}"
            payload = {
                "name": f"{device.name} {sensor_name}",
                "unique_id": f"{device.unique_id_base}_{sensor_id}",
                "state_topic": state_topic,
                "entity_category": "diagnostic",
                "icon": icon,
                "availability": avail,
                "device": sub_dev,
                "origin": ORIGIN,
            }
            disc_topic = f"{HA_DISCOVERY}/sensor/{device.unique_id_base}_{sensor_id}/config"
            self._client.publish(disc_topic, json.dumps(payload), retain=True)

        logger.info("[Modus B] '%s' → 3 Buttons + 2 Sensoren", device.name)

    # ---------- Publish ----------

    def publish_state(self, device: DeviceConfig, state: str) -> None:
        """Modus A: Veröffentlicht Cover-Status (open/closed/stopped)."""
        topic = f"{MQTT_TOPIC_PREFIX}/{device.slug}/state"
        self._client.publish(topic, state, retain=True)

    def publish_diagnostic(self, device: DeviceConfig, key: str, value: str) -> None:
        """Modus B: Aktualisiert einen Diagnose-Sensor (rolling_code / last_command)."""
        topic = f"{MQTT_TOPIC_PREFIX}/{device.slug}/{key}"
        self._client.publish(topic, value, retain=True)

    # ---------- Interna ----------

    def _subscribe(self, topic: str, handler: Callable[[str], None]) -> None:
        self._client.subscribe(topic)
        self._handlers[topic] = handler

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("MQTT verbunden.")
            client.publish(LWT_TOPIC, "online", retain=True)
            for topic in self._handlers:
                client.subscribe(topic)
        else:
            logger.error("MQTT Verbindungsfehler, RC=%d", rc)

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            logger.warning("MQTT getrennt (RC=%d) — paho reconnect...", rc)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace").strip()
        logger.debug("MQTT RX [%s]: %s", topic, payload)
        handler = self._handlers.get(topic)
        if handler:
            handler(payload)
        else:
            logger.warning("Kein Handler für Topic: %s", topic)


# ---------- Hilfsfunktionen ----------

def _avail_block() -> dict:
    return {
        "topic": LWT_TOPIC,
        "payload_available": "online",
        "payload_not_available": "offline",
    }


def _sub_device(device: DeviceConfig, profile: Optional[Dict] = None) -> dict:
    return {
        "identifiers": [device.unique_id_base],
        "name": device.name,
        "model": f"Somfy RTS {device.type.title()}",
        "manufacturer": "Somfy",
        "via_device": "somfy_rts_gateway",
    }

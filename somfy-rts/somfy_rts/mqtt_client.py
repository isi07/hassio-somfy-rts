"""MQTT Client: Verbindung, HA Discovery (Gateway + Geräte, Modus A/B) und Command Handling.

Discovery-Struktur:
  Gateway-Device (diagnostisch):
    - sensor: Verbindungsstatus, USB-Port, Geräteanzahl, SW-Version

  Sub-Device pro Gerät (via_device: Gateway):
    Modus A: cover entity (optimistisch, device_class je Gerätetyp)
             + 3x sensor (entity_category: diagnostic):
               rolling_code, last_command (+ raw_frame Attribut), device_address
             + 2x button (entity_category: config): PROG Lang (Yr8), PROG Anlern (Yr4)
    Modus B: 3x button (entity_category: config): Auf, Zu, Stop
             + 2x button (entity_category: config): PROG Lang (Yr8), PROG Anlern (Yr4)
             + 2x sensor (entity_category: diagnostic):
               rolling_code, last_command (+ raw_frame Attribut)

  PROG-Buttons (beide Modi): command_topic somfy/{slug}/cmd,
    payload_press PROG_LONG (Yr8) / PROG_PAIR (Yr4)

Availability: LWT auf Topic 'cul2mqtt/status' (online/offline, retain=True).
Alle Discovery-Payloads enthalten availability mit payload_available='online'
und payload_not_available='offline'.
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

    def __init__(self, config: Config) -> None:
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
        """Veröffentlicht HA Discovery für das Gateway-Gerät.

        Verbindungsstatus: binary_sensor ohne availability-Block — liest LWT_TOPIC direkt,
        bleibt in HA immer verfügbar und zeigt "Verbunden"/"Getrennt" statt "Nicht verfügbar".

        Die drei anderen Diagnose-Sensoren (USB-Port, Geräte, SW-Version) haben einen
        availability-Block und werden bei Offline auf "Nicht verfügbar" gesetzt.
        """
        avail = _avail_block()

        # Verbindungsstatus als binary_sensor — kein availability-Block, liest LWT direkt.
        # Altes sensor-Topic (aus Vorversionen) wird gecleart um Duplikate zu vermeiden.
        self._client.publish(
            f"{HA_DISCOVERY}/sensor/somfy_rts_gw_status/config", "", retain=True
        )
        conn_payload: Dict = {
            "name": "Verbindung",
            "unique_id": "somfy_rts_gw_status",
            "state_topic": LWT_TOPIC,
            "payload_on": "online",
            "payload_off": "offline",
            "device_class": "connectivity",
            "entity_category": "diagnostic",
            "icon": "mdi:lan-connect",
            "device": _GW_DEVICE,
            "origin": ORIGIN,
            # Kein availability-Block — Entität bleibt immer verfügbar,
            # Status wechselt zwischen online/offline via LWT.
        }
        self._client.publish(
            f"{HA_DISCOVERY}/binary_sensor/somfy_rts_gw_status/config",
            json.dumps(conn_payload),
            retain=True,
        )

        # Drei Diagnose-Sensoren mit availability (werden bei Offline unavailable)
        sensor_defs = [
            ("port",         "USB-Port",    f"{GW_TOPIC_BASE}/port",         "mdi:usb",     None),
            ("device_count", "Geräte",      f"{GW_TOPIC_BASE}/device_count", "mdi:counter", None),
            ("sw_version",   "SW-Version",  f"{GW_TOPIC_BASE}/sw_version",   "mdi:tag",     None),
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

        # Initiale Werte (LWT wird von connect() auf "online" gesetzt)
        self._client.publish(f"{GW_TOPIC_BASE}/port",         port_name,         retain=True)
        self._client.publish(f"{GW_TOPIC_BASE}/device_count", str(device_count), retain=True)
        self._client.publish(f"{GW_TOPIC_BASE}/sw_version",   __version__,       retain=True)
        logger.info("Gateway Discovery veröffentlicht (%d Gerät(e)).", device_count)

    def update_gateway_status(self, status: str) -> None:
        self._client.publish(f"{GW_TOPIC_BASE}/status", status, retain=True)

    def update_device_count(self, count: int) -> None:
        """Aktualisiert den Geräteanzahl-Sensor am Gateway (z.B. nach Import oder Löschen)."""
        self._client.publish(f"{GW_TOPIC_BASE}/device_count", str(count), retain=True)

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
        """Modus A: Optimistisches MQTT Cover-Entity + 3 Diagnose-Sensoren.

        Cover: device_class kommt aus dem Profil (device_profiles.json).
        Sensoren: rolling_code, last_command (json_attributes_topic für raw_frame),
                  device_address (statisch, nur einmal publiziert).
        """
        prefix = MQTT_TOPIC_PREFIX
        slug = device.slug
        state_topic = f"{prefix}/{slug}/state"
        command_topic = f"{prefix}/{slug}/set"
        sub_dev = _sub_device(device, profile)

        cover_payload: Dict = {
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
            "device": sub_dev,
            "origin": ORIGIN,
        }
        device_class = profile.get("device_class")
        if device_class:
            cover_payload["device_class"] = device_class

        disc_topic = f"{HA_DISCOVERY}/cover/{device.unique_id_base}/config"
        self._client.publish(disc_topic, json.dumps(cover_payload), retain=True)

        # 3 Diagnose-Sensoren
        diag_sensors = [
            ("rolling_code",   "Rolling Code",    "mdi:counter",    None),
            ("last_command",   "Letzter Befehl",  "mdi:history",    f"{prefix}/{slug}/last_command_attr"),
            ("device_address", "Adresse",         "mdi:identifier", None),
        ]
        for sensor_id, sensor_name, icon, attr_topic in diag_sensors:
            s_payload: Dict = {
                "name": f"{device.name} {sensor_name}",
                "unique_id": f"{device.unique_id_base}_{sensor_id}",
                "state_topic": f"{prefix}/{slug}/{sensor_id}",
                "entity_category": "diagnostic",
                "icon": icon,
                "availability": _avail_block(),
                "device": sub_dev,
                "origin": ORIGIN,
            }
            if attr_topic:
                s_payload["json_attributes_topic"] = attr_topic
            s_disc = f"{HA_DISCOVERY}/sensor/{device.unique_id_base}_{sensor_id}/config"
            self._client.publish(s_disc, json.dumps(s_payload), retain=True)

        self._subscribe(command_topic, command_handler)

        # PROG Lang + PROG Anlern Buttons (entity_category: config) — beide Modi
        self._register_prog_buttons(device, command_handler, sub_dev)

        logger.info("[Modus A] '%s' → Cover + 3 Diagnose-Sensoren + 2 PROG-Buttons auf %s", device.name, command_topic)

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

        # 2 Diagnose-Sensoren: rolling_code + last_command (mit raw_frame Attribut)
        for sensor_id, sensor_name, icon, attr_topic in [
            ("rolling_code", "Rolling Code",   "mdi:counter", None),
            ("last_command", "Letzter Befehl", "mdi:history", f"{prefix}/{slug}/last_command_attr"),
        ]:
            s_payload = {
                "name": f"{device.name} {sensor_name}",
                "unique_id": f"{device.unique_id_base}_{sensor_id}",
                "state_topic": f"{prefix}/{slug}/{sensor_id}",
                "entity_category": "diagnostic",
                "icon": icon,
                "availability": avail,
                "device": sub_dev,
                "origin": ORIGIN,
            }
            if attr_topic:
                s_payload["json_attributes_topic"] = attr_topic
            disc_topic = f"{HA_DISCOVERY}/sensor/{device.unique_id_base}_{sensor_id}/config"
            self._client.publish(disc_topic, json.dumps(s_payload), retain=True)

        # PROG Lang + PROG Anlern Buttons (entity_category: config) — beide Modi
        self._register_prog_buttons(device, command_handler, sub_dev)

        logger.info("[Modus B] '%s' → 3 Buttons + 2 PROG-Buttons + 2 Sensoren", device.name)

    def _register_prog_buttons(
        self,
        device: DeviceConfig,
        command_handler: Callable[[str], None],
        sub_dev: dict,
    ) -> None:
        """Registriert PROG Lang (Yr8) und PROG Anlern (Yr4) als HA-Button-Entitäten.

        Gilt für ALLE Gerätetypen und BEIDE Modi (A + B).
        Beide Buttons teilen das Topic somfy/{slug}/cmd; Payload differenziert die Aktion.
        """
        prefix = MQTT_TOPIC_PREFIX
        cmd_topic = f"{prefix}/{device.slug}/cmd"
        avail = _avail_block()

        prog_buttons = [
            ("prog_long", f"{device.name} PROG Lang",   "mdi:timer",   "PROG_LONG"),
            ("prog_pair", f"{device.name} PROG Anlern", "mdi:antenna", "PROG_PAIR"),
        ]

        for btn_key, btn_name, icon, payload_press in prog_buttons:
            btn_payload: Dict = {
                "name": btn_name,
                "unique_id": f"{device.unique_id_base}_{btn_key}",
                "command_topic": cmd_topic,
                "payload_press": payload_press,
                "entity_category": "config",
                "icon": icon,
                "availability": avail,
                "device": sub_dev,
                "origin": ORIGIN,
            }
            disc_topic = f"{HA_DISCOVERY}/button/{device.unique_id_base}_{btn_key}/config"
            self._client.publish(disc_topic, json.dumps(btn_payload), retain=True)

        self._subscribe(cmd_topic, command_handler)

    # ---------- Publish ----------

    def publish_state(self, device: DeviceConfig, state: str) -> None:
        """Modus A: Veröffentlicht Cover-Status (open/closed/stopped)."""
        topic = f"{MQTT_TOPIC_PREFIX}/{device.slug}/state"
        self._client.publish(topic, state, retain=True)

    def publish_diagnostic(self, device: DeviceConfig, key: str, value: str) -> None:
        """Aktualisiert einen Diagnose-Sensor (rolling_code / last_command / device_address)."""
        topic = f"{MQTT_TOPIC_PREFIX}/{device.slug}/{key}"
        self._client.publish(topic, value, retain=True)

    def publish_json_attributes(self, device: DeviceConfig, key: str, attrs: Dict) -> None:
        """Veröffentlicht JSON-Attribute für einen Sensor (z.B. raw_frame für last_command).

        Publiziert auf Topic somfy/{slug}/{key}_attr als JSON-String.
        HA liest den Inhalt als Entity-Attribute des zugehörigen Sensors.
        """
        topic = f"{MQTT_TOPIC_PREFIX}/{device.slug}/{key}_attr"
        self._client.publish(topic, json.dumps(attrs), retain=True)

    # ---------- Interna ----------

    def _subscribe(self, topic: str, handler: Callable[[str], None]) -> None:
        self._client.subscribe(topic)
        self._handlers[topic] = handler

    def _on_connect(self, client: mqtt.Client, userdata: object, flags: dict, rc: int) -> None:
        if rc == 0:
            logger.info("MQTT verbunden.")
            client.publish(LWT_TOPIC, "online", retain=True)
            for topic in self._handlers:
                client.subscribe(topic)
        else:
            logger.error("MQTT Verbindungsfehler, RC=%d", rc)

    def _on_disconnect(self, client: mqtt.Client, userdata: object, rc: int) -> None:
        if rc != 0:
            logger.warning("MQTT getrennt (RC=%d) — paho reconnect...", rc)

    def _on_message(self, client: mqtt.Client, userdata: object, msg: mqtt.MQTTMessage) -> None:
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

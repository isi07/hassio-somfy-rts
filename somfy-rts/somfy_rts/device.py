"""Allgemeine RTS-Geräte-Klasse für alle Somfy-Typen.

Das RTS-Protokoll ist für ALLE Gerätetypen identisch:
  CMD 0x2 = Auf, 0x4 = Zu, 0x1 = MY/Stop, 0x8 = Prog

Gerätetyp-spezifisches (HA device_class, Icons, Button-Labels) stammt
ausschließlich aus device_profiles.json — keine separaten Klassen pro Typ.
"""

import json
import logging
import os
from typing import Any, Dict

from .config import DeviceConfig
from .gateway import BaseGateway, GatewayError
from .mqtt_client import MQTTClient
from .rolling_code import get_current
from . import rts as rts_module

logger = logging.getLogger(__name__)

_PROFILES_PATH = os.path.join(os.path.dirname(__file__), "device_profiles.json")

_FALLBACK_PROFILE: Dict[str, Any] = {
    "device_class": None,
    "icon": "mdi:remote",
    "buttons": {
        "open":  {"rts": "OPEN",  "label": "Auf",  "icon": "mdi:arrow-up-circle"},
        "close": {"rts": "CLOSE", "label": "Zu",   "icon": "mdi:arrow-down-circle"},
        "stop":  {"rts": "STOP",  "label": "Stop", "icon": "mdi:stop-circle"},
    },
    "default_travel_time_open": 30,
    "default_travel_time_close": 30,
}


def _load_profiles() -> Dict[str, Any]:
    try:
        with open(_PROFILES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("device_profiles.json nicht lesbar: %s — verwende Fallback.", e)
        return {}


class Device:
    """Repräsentiert ein einzelnes Somfy RTS Gerät — unabhängig vom Typ.

    Modus A: Empfängt MQTT Cover-Befehle (OPEN/CLOSE/STOP), sendet RTS, meldet Zustand zurück.
    Modus B: Empfängt Button-Press-Events, sendet RTS, aktualisiert Diagnose-Sensoren.
    """

    def __init__(self, device_cfg: DeviceConfig, gateway: BaseGateway, mqtt: MQTTClient) -> None:
        self._device = device_cfg
        self._gateway = gateway
        self._mqtt = mqtt
        profiles = _load_profiles()
        self._profile = profiles.get(device_cfg.type, _FALLBACK_PROFILE)
        self._state = "stopped"

    def setup(self) -> None:
        """Registriert das Gerät in HA via MQTT Discovery und publiziert Initialzustand."""
        self._mqtt.register_device(self._device, self._handle_command, self._profile)

        if self._device.mode == "A":
            self._mqtt.publish_state(self._device, self._state)
        elif self._device.mode == "B":
            self._publish_diagnostics()

        logger.info(
            "Gerät '%s' bereit — Typ=%s | Modus=%s | Adresse=%s",
            self._device.name,
            self._device.type,
            self._device.mode,
            self._device.address,
        )

    def _handle_command(self, command: str) -> None:
        """Verarbeitet MQTT-Befehl: Rolling Code atomar persistieren → RTS senden → Status melden."""
        command = command.upper()
        if command not in {"OPEN", "CLOSE", "STOP", "PROG", "MY_UP", "MY_DOWN"}:
            logger.warning("Unbekannter Befehl '%s' für '%s'.", command, self._device.name)
            return

        logger.info("Befehl für '%s': %s", self._device.name, command)
        self._send_rts(command)

        if self._device.mode == "A":
            self._state = _command_to_state(command)
            self._mqtt.publish_state(self._device, self._state)
        elif self._device.mode == "B":
            self._publish_diagnostics(last_command=command)

    def _send_rts(self, action: str) -> None:
        """Baut RTS-Sequenz (RC atomar persistiert) und sendet beide Befehle via Gateway."""
        try:
            commands = rts_module.build_rts_sequence(
                self._device.address, action, self._device.name
            )
            for cmd in commands:
                self._gateway.send_raw(cmd)
        except GatewayError as e:
            logger.error("Gateway-Fehler bei '%s': %s", self._device.name, e)
        except ValueError as e:
            logger.error("RTS-Protokollfehler bei '%s': %s", self._device.name, e)

    def _publish_diagnostics(self, last_command: str = "") -> None:
        """Modus B: Aktualisiert rolling_code und last_command Sensoren in HA."""
        rc = get_current(self._device.address)
        self._mqtt.publish_diagnostic(self._device, "rolling_code", str(rc))
        if last_command:
            self._mqtt.publish_diagnostic(self._device, "last_command", last_command)


def _command_to_state(command: str) -> str:
    return {
        "OPEN":    "open",
        "CLOSE":   "closed",
        "STOP":    "stopped",
        "PROG":    "stopped",
        "MY_UP":   "open",
        "MY_DOWN": "closed",
    }.get(command, "stopped")

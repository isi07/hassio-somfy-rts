"""Liest die Add-on Konfiguration aus /data/options.json."""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)

OPTIONS_PATH = os.environ.get("OPTIONS_PATH", "/data/options.json")

VALID_TYPES = frozenset({"awning", "shutter", "blind", "screen", "gate", "light", "heater"})
VALID_MODES = frozenset({"A", "B"})
_ADDRESS_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class DeviceConfig:
    name: str
    type: str    # awning | shutter | blind | screen | gate | light | heater
    address: str  # 3-Byte Hex, z.B. "A1B2C3"
    mode: str = "A"   # A = optimistisches Cover-Entity | B = 3 Buttons + Diagnose
    rolling_code: int = 0

    @property
    def slug(self) -> str:
        """URL- und MQTT-sicherer Bezeichner (z.B. 'wohnzimmer_markise')."""
        return _SLUG_RE.sub("_", self.name.lower()).strip("_")

    @property
    def unique_id_base(self) -> str:
        """Basis-ID für HA unique_id Felder."""
        return f"somfy_rts_{self.address.lower()}"


@dataclass
class Config:
    serial_port: str = "/dev/ttyUSB0"
    baud_rate: int = 38400
    mqtt_host: str = "core-mosquitto"
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_password: str = ""
    mqtt_topic_prefix: str = "somfy"
    log_level: str = "INFO"
    devices: List[DeviceConfig] = field(default_factory=list)


def load_config() -> Config:
    """Liest /data/options.json und gibt ein validiertes Config-Objekt zurück."""
    try:
        with open(OPTIONS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        logger.warning("%s nicht gefunden — Entwicklungsmodus, verwende Defaults.", OPTIONS_PATH)
        raw = {}
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Ungültiges JSON in {OPTIONS_PATH}: {e}") from e

    devices: List[DeviceConfig] = []
    for d in raw.get("devices", []):
        addr = d.get("address", "").upper()
        if not _ADDRESS_RE.match(addr):
            logger.error(
                "Ungültige Adresse '%s' für Gerät '%s' (erwartet: 6 Hex-Zeichen) — überspringe.",
                addr, d.get("name", "?"),
            )
            continue

        dev_type = d.get("type", "shutter")
        if dev_type not in VALID_TYPES:
            logger.warning("Unbekannter Typ '%s' — verwende 'shutter'.", dev_type)
            dev_type = "shutter"

        mode = str(d.get("mode", "A")).upper()
        if mode not in VALID_MODES:
            logger.warning("Unbekannter Modus '%s' — verwende 'A'.", mode)
            mode = "A"

        devices.append(DeviceConfig(
            name=d["name"],
            type=dev_type,
            address=addr,
            mode=mode,
            rolling_code=int(d.get("rolling_code", 0)),
        ))

    return Config(
        serial_port=raw.get("serial_port", "/dev/ttyUSB0"),
        baud_rate=int(raw.get("baud_rate", 38400)),
        mqtt_host=raw.get("mqtt_host", "core-mosquitto"),
        mqtt_port=int(raw.get("mqtt_port", 1883)),
        mqtt_user=raw.get("mqtt_user", ""),
        mqtt_password=raw.get("mqtt_password", ""),
        mqtt_topic_prefix=raw.get("mqtt_topic_prefix", "somfy"),
        log_level=raw.get("log_level", "INFO").upper(),
        devices=devices,
    )

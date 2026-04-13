"""Reads add-on configuration from environment variables (set by run.sh via bashio).

run.sh reads /data/options.json via bashio and exports each value as
SOMFY_* environment variables. This module reads those variables.
Devices are managed separately via /data/somfy_codes.json (rolling_code.py).
"""

import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class DeviceConfig:
    name: str
    type: str    # awning | shutter | blind | screen | gate | light | heater
    address: str  # 3-byte hex, e.g. "A1B2C3"
    mode: str = "A"  # A = optimistic cover entity | B = 3 buttons + diagnostic sensors

    @property
    def slug(self) -> str:
        """URL- and MQTT-safe identifier, e.g. 'wohnzimmer_markise'."""
        return _SLUG_RE.sub("_", self.name.lower()).strip("_")

    @property
    def unique_id_base(self) -> str:
        """Base ID for HA unique_id fields."""
        return f"somfy_rts_{self.address.lower()}"


@dataclass
class Config:
    usb_port: str = "/dev/ttyACM0"
    baudrate: int = 9600
    mqtt_host: str = "core-mosquitto"
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_password: str = ""
    log_level: str = "INFO"
    address_prefix: str = "A000"  # single source of truth — passed to PairingWizard
    log_format: str = "text"       # "text" | "json"
    simulation_mode: bool = False  # Use SimGateway instead of CULGateway
    file_logging: bool = False     # Write RTS frames to /share/somfy_rts/rts_frames.log


def load_config() -> Config:
    """Reads configuration from SOMFY_* environment variables exported by run.sh."""
    return Config(
        usb_port=os.environ.get("SOMFY_USB_PORT", "/dev/ttyACM0"),
        baudrate=int(os.environ.get("SOMFY_BAUDRATE", "9600")),
        mqtt_host=os.environ.get("SOMFY_MQTT_HOST", "core-mosquitto"),
        mqtt_port=int(os.environ.get("SOMFY_MQTT_PORT", "1883")),
        mqtt_user=os.environ.get("SOMFY_MQTT_USER", ""),
        mqtt_password=os.environ.get("SOMFY_MQTT_PASSWORD", ""),
        log_level=os.environ.get("SOMFY_LOG_LEVEL", "info").upper(),
        address_prefix=os.environ.get("SOMFY_ADDRESS_PREFIX", "A000").upper(),
        log_format=os.environ.get("SOMFY_LOG_FORMAT", "text").lower(),
        simulation_mode=os.environ.get("SOMFY_SIMULATION_MODE", "false").lower() == "true",
        file_logging=os.environ.get("SOMFY_FILE_LOGGING", "false").lower() == "true",
    )

"""Add-on entry point."""

import logging
import signal
import sys
import types
import time

from . import __version__
from .config import load_config
from .gateway import CULGateway, GatewayError
from .mqtt_client import MQTTClient
from .rolling_code import _load as load_codes


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
    logger = logging.getLogger(__name__)
    logger.info("=== Somfy RTS Add-on v%s starting ===", __version__)

    config = load_config()
    logging.getLogger().setLevel(getattr(logging, config.log_level, logging.INFO))

    # Load device list from somfy_codes.json (source of truth for devices)
    store = load_codes()
    device_count = len(store.get("devices", []))
    logger.info("Found %d device(s) in somfy_codes.json.", device_count)

    gateway = CULGateway(config.usb_port, config.baudrate)
    mqtt_client = MQTTClient(config)

    running = True

    def _shutdown(signum: int, frame: types.FrameType | None) -> None:
        nonlocal running
        logger.info("Signal %d received — shutting down...", signum)
        running = False

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Connect gateway with retry until SIGTERM
    while running:
        try:
            gateway.connect()
            break
        except GatewayError as e:
            logger.error("Gateway error: %s — retrying in 10s.", e)
            time.sleep(10)

    if not running:
        sys.exit(0)

    # Connect MQTT
    try:
        mqtt_client.connect()
    except RuntimeError as e:
        logger.error("MQTT error: %s", e)
        gateway.disconnect()
        sys.exit(1)

    # Register gateway device in HA
    mqtt_client.register_gateway(gateway.port_name, device_count)

    logger.info("Add-on running — waiting for MQTT commands...")

    while running:
        time.sleep(1)

    mqtt_client.update_gateway_status("Offline")
    mqtt_client.disconnect()
    gateway.disconnect()
    logger.info("Somfy RTS Add-on stopped.")


if __name__ == "__main__":
    main()

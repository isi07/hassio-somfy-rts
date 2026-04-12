"""Einstiegspunkt des Somfy RTS Add-ons."""

import logging
import signal
import sys
import time

from . import __version__
from .config import load_config
from .device import Device
from .gateway import CULGateway, GatewayError
from .mqtt_client import MQTTClient


def main() -> None:
    # Basis-Logging bis Config geladen ist
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
    logger = logging.getLogger(__name__)
    logger.info("=== Somfy RTS Add-on v%s startet ===", __version__)

    config = load_config()

    # Log-Level aus Konfiguration anwenden
    logging.getLogger().setLevel(getattr(logging, config.log_level, logging.INFO))

    if not config.devices:
        logger.warning(
            "Keine Geräte konfiguriert — bitte 'devices' in der Add-on Konfiguration eintragen."
        )

    gateway = CULGateway(config.serial_port, config.baud_rate)
    mqtt_client = MQTTClient(config)

    running = True

    def _shutdown(signum, frame):
        nonlocal running
        logger.info("Signal %d empfangen — beende Add-on...", signum)
        running = False

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Gateway verbinden (mit Retry bis SIGTERM)
    while running:
        try:
            gateway.connect()
            break
        except GatewayError as e:
            logger.error("Gateway-Fehler: %s — neuer Versuch in 10s.", e)
            time.sleep(10)

    if not running:
        sys.exit(0)

    # MQTT verbinden
    try:
        mqtt_client.connect()
    except RuntimeError as e:
        logger.error("MQTT Fehler: %s", e)
        gateway.disconnect()
        sys.exit(1)

    # Gateway-Device in HA registrieren
    mqtt_client.register_gateway(gateway.port_name, len(config.devices))

    # Geräte anlegen und registrieren
    devices = [Device(dev, gateway, mqtt_client) for dev in config.devices]
    for device in devices:
        device.setup()

    logger.info(
        "Add-on läuft — %d Gerät(e) registriert. Warte auf MQTT-Befehle...",
        len(devices),
    )

    # Hauptschleife
    while running:
        time.sleep(1)

    # Geordnetes Herunterfahren
    mqtt_client.update_gateway_status("Offline")
    mqtt_client.disconnect()
    gateway.disconnect()
    logger.info("Somfy RTS Add-on beendet.")


if __name__ == "__main__":
    main()

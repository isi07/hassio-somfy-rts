"""App entry point — asyncio main loop with aiohttp Web UI."""

import asyncio
import logging
import signal
import sys

from . import __version__
from .config import DeviceConfig, load_config
from .device import Device
from .gateway import CULGateway, GatewayError, SimGateway
from .mqtt_client import MQTTClient
from .rolling_code import _load as load_codes
from .rts_logger import init as init_rts_logger
from .web.api import AppContext
from .web.server import start_server

WEB_HOST = "0.0.0.0"
WEB_PORT = 8099


def main() -> None:
    """Entry point — delegates to the asyncio main coroutine."""
    asyncio.run(_async_main())


async def _async_main() -> None:
    """Async main loop: gateway, MQTT, Web UI, graceful shutdown."""
    config = load_config()

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
    logger = logging.getLogger(__name__)
    logger.info("=== Somfy RTS App v%s starting ===", __version__)

    init_rts_logger(log_format=config.log_format, file_logging=config.file_logging)

    store = load_codes()
    device_count = len(store.get("devices", []))
    logger.info("Found %d device(s) in somfy_codes.json.", device_count)

    # Gateway selection
    if config.simulation_mode:
        logger.info("Simulation mode active — using SimGateway (no hardware required).")
        gateway: CULGateway | SimGateway = SimGateway()
    else:
        gateway = CULGateway(config.usb_port, config.baudrate)

    mqtt_client = MQTTClient(config)

    # Shutdown event — set by SIGTERM / SIGINT
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _on_signal() -> None:
        logger.info("Shutdown-Signal empfangen.")
        shutdown_event.set()

    # add_signal_handler only works on Unix; ignore on Windows
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except (NotImplementedError, OSError):
            pass  # Windows: handled via KeyboardInterrupt

    # Connect gateway with retry until shutdown
    while not shutdown_event.is_set():
        try:
            gateway.connect()
            break
        except GatewayError as e:
            logger.error("Gateway Fehler: %s — erneuter Versuch in 10s.", e)
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                pass

    if shutdown_event.is_set():
        sys.exit(0)

    # Connect MQTT (paho threaded mode, non-blocking)
    try:
        mqtt_client.connect()
    except RuntimeError as e:
        logger.error("MQTT Fehler: %s", e)
        gateway.disconnect()
        sys.exit(1)

    mqtt_client.register_gateway(gateway.port_name, device_count)

    # Publish MQTT Discovery for all existing devices
    devices: list[Device] = []
    for dev_data in store.get("devices", []):
        device_cfg = DeviceConfig(
            name=dev_data.get("name", ""),
            type=dev_data.get("device_type", "shutter"),
            address=dev_data.get("address", ""),
            mode=dev_data.get("mode", "A"),
        )
        dev = Device(device_cfg, gateway, mqtt_client)
        dev.setup()
        devices.append(dev)

    # Build app context and start Web UI
    ctx = AppContext(gateway=gateway, config=config, mqtt_client=mqtt_client)
    ctx.attach_log_handler()

    runner = await start_server(WEB_HOST, WEB_PORT, ctx)
    logger.info("App running — Web UI: http://%s:%d", WEB_HOST, WEB_PORT)

    # Wait for shutdown signal
    try:
        await shutdown_event.wait()
    except KeyboardInterrupt:
        pass

    # Graceful shutdown
    logger.info("Fahre herunter…")
    mqtt_client.update_gateway_status("Offline")
    mqtt_client.disconnect()
    gateway.disconnect()
    await runner.cleanup()
    logger.info("Somfy RTS App stopped.")


if __name__ == "__main__":
    main()

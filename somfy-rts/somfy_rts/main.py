"""App entry point — asyncio main loop with aiohttp Web UI."""

import asyncio
import logging
import signal
import sys

from . import __version__
from .config import DeviceConfig, load_config
from .device import Device
from .gateway import BaseGateway, CULGateway, GatewayError, SimGateway
from .mqtt_client import MQTTClient
from .rolling_code import RollingCodeStoreError
from .rolling_code import _load as load_codes
from .rts_logger import init as init_rts_logger
from .web.api import AppContext
from .web.server import start_server

WEB_HOST = "0.0.0.0"
WEB_PORT = 8099
MQTT_WAIT_POLL_S = 0.5
GATEWAY_RETRY_S = 10.0

logger = logging.getLogger(__name__)


async def wait_for_mqtt(
    mqtt_client: MQTTClient,
    shutdown_event: asyncio.Event,
    poll_s: float = MQTT_WAIT_POLL_S,
) -> bool:
    """Wait until the MQTT client is connected or shutdown is requested.

    The connection itself is retried by paho in the background (see
    MQTTClient.connect); failed attempts are logged there.

    Args:
        mqtt_client: Client on which connect() has been called.
        shutdown_event: Set by SIGTERM/SIGINT.
        poll_s: Polling interval in seconds.

    Returns:
        True once connected, False if shutdown was requested first.
    """
    waiting_logged = False
    while not mqtt_client.is_connected:
        if not waiting_logged:
            logger.info(
                "Warte auf Verbindung zum MQTT-Broker — Discovery folgt danach automatisch."
            )
            waiting_logged = True
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=poll_s)
            return False
        except TimeoutError:
            continue
    return True


async def connect_gateway(
    gateway: BaseGateway,
    shutdown_event: asyncio.Event,
    retry_s: float = GATEWAY_RETRY_S,
) -> bool:
    """Connect the gateway, retrying until it succeeds or shutdown is requested.

    Args:
        gateway: CULGateway or SimGateway.
        shutdown_event: Set by SIGTERM/SIGINT.
        retry_s: Delay between attempts in seconds.

    Returns:
        True once connected, False if shutdown was requested first.
    """
    while not shutdown_event.is_set():
        try:
            gateway.connect()
            return True
        except GatewayError as e:
            logger.error("Gateway Fehler: %s — erneuter Versuch in %.0fs.", e, retry_s)
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=retry_s)
            except TimeoutError:
                pass
    return False


def main() -> None:
    """Entry point — delegates to the asyncio main coroutine."""
    asyncio.run(_async_main())


async def _async_main(shutdown_event: asyncio.Event | None = None) -> None:
    """Async main loop: Web UI, gateway, MQTT, graceful shutdown.

    The Web UI starts first so that Ingress and the HA watchdog (GET /api/status)
    get an answer while the app is still waiting for the NanoCUL or the broker.

    Args:
        shutdown_event: Injected by tests; created and bound to SIGTERM/SIGINT
            otherwise.
    """
    config = load_config()

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
    logger.info("=== Somfy RTS App v%s starting ===", __version__)

    init_rts_logger(log_format=config.log_format, file_logging=config.file_logging)

    # A corrupt store must never be replaced: keep running (Web UI shows the
    # error), register no devices, and let every send fail until it is repaired.
    store_error = ""
    try:
        store = load_codes()
    except RollingCodeStoreError as e:
        store_error = str(e)
        logger.error("%s", store_error)
        store = {"devices": []}
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
    if shutdown_event is None:
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

    # Web UI first — Ingress and the HA watchdog must answer while waiting below
    ctx = AppContext(gateway=gateway, config=config, mqtt_client=mqtt_client)
    ctx.attach_log_handler()
    runner = await start_server(WEB_HOST, WEB_PORT, ctx)

    try:
        if not await connect_gateway(gateway, shutdown_event):
            return

        # Connect MQTT in the background (paho retries until the broker is
        # reachable) and wait — discovery would be dropped while disconnected.
        mqtt_client.connect()
        if not await wait_for_mqtt(mqtt_client, shutdown_event):
            return

        mqtt_client.register_gateway(gateway.port_name, device_count)
        if store_error:
            mqtt_client.update_gateway_status("Fehler: somfy_codes.json beschädigt")

        # Publish MQTT Discovery for all existing devices
        for dev_data in store.get("devices", []):
            device_cfg = DeviceConfig(
                name=dev_data.get("name", ""),
                type=dev_data.get("device_type", "shutter"),
                address=dev_data.get("address", ""),
                mode=dev_data.get("mode", "A"),
            )
            Device(device_cfg, gateway, mqtt_client).setup()

        logger.info("App running — Web UI: http://%s:%d", WEB_HOST, WEB_PORT)
        try:
            await shutdown_event.wait()
        except KeyboardInterrupt:
            pass
    finally:
        # Graceful shutdown — also when stopped while waiting for stick/broker
        logger.info("Fahre herunter…")
        if mqtt_client.is_connected:
            mqtt_client.update_gateway_status("Offline")
        mqtt_client.disconnect()
        gateway.disconnect()
        await runner.cleanup()
        logger.info("Somfy RTS App stopped.")


if __name__ == "__main__":
    main()

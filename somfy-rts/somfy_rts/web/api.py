"""REST API routes for the Somfy RTS Web UI.

Endpoints:
  GET  /api/status               → gateway + simulation status
  GET  /api/devices              → all devices from somfy_codes.json
  GET  /api/devices/{id}         → single device by address
  POST /api/devices/import       → add device by known address + rolling code (no pairing)
  POST /api/devices/{id}/cmd     → send RTS command (OPEN/CLOSE/STOP/MY_UP/MY_DOWN)
  DELETE /api/devices/{id}       → remove device

  GET  /api/wizard/status        → current wizard state
  POST /api/wizard/start         → start pairing (name, device_type)
  POST /api/wizard/send_prog     → transmit PROG telegram
  POST /api/wizard/confirm       → confirm motor pairing
  POST /api/wizard/cancel        → abort wizard session

  GET  /api/settings             → current config
  POST /api/settings             → (read-only — managed via HA)

  GET  /api/logs                 → last 100 RTS frame log entries
  GET  /api/logs/download        → download /share/somfy_rts/rts_frames.log
"""

import logging
import pathlib
import re
from collections import deque
from typing import Optional

from aiohttp import web

from .. import __version__
from ..config import Config, DeviceConfig
from ..device import Device
from ..gateway import BaseGateway, SimGateway
from ..mqtt_client import MQTTClient
from ..rolling_code import _load, _save_atomic
from ..rts import build_rts_sequence, log_rts_frame
from ..wizard import PairingWizard

routes = web.RouteTableDef()
logger = logging.getLogger(__name__)

_HEX_ADDR_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
_VALID_DEVICE_TYPES = {"awning", "shutter", "blind", "screen", "gate", "light", "heater"}

# ---------- AppContext ----------


class AppContext:
    """Shared application state passed to all API handlers via request.app['ctx']."""

    def __init__(
        self,
        gateway: BaseGateway,
        config: Config,
        mqtt_client: Optional[MQTTClient] = None,
    ) -> None:
        self.gateway = gateway
        self.config = config
        self.mqtt_client = mqtt_client
        self.wizard: Optional[PairingWizard] = None
        self.log_buffer: deque[dict] = deque(maxlen=100)

    def attach_log_handler(self) -> None:
        """Attach a memory handler to the RTS frame logger."""
        handler = _LogBufferHandler(self.log_buffer)
        logging.getLogger("somfy_rts.frames").addHandler(handler)


class _LogBufferHandler(logging.Handler):
    def __init__(self, buf: deque[dict]) -> None:
        super().__init__()
        self._buf = buf

    def emit(self, record: logging.LogRecord) -> None:
        self._buf.append({"ts": record.created, "message": record.getMessage()})


# ---------- Status ----------


@routes.get("/api/status")
async def get_status(request: web.Request) -> web.Response:
    """Return gateway connection and simulation status."""
    ctx: AppContext = request.app["ctx"]
    return web.json_response(
        {
            "connected": ctx.gateway.is_connected,
            "simulation": isinstance(ctx.gateway, SimGateway),
            "port": ctx.gateway.port_name,
            "version": __version__,
        }
    )


# ---------- Devices ----------


@routes.get("/api/devices")
async def get_devices(request: web.Request) -> web.Response:
    """Return all devices from somfy_codes.json."""
    store = _load()
    return web.json_response({"devices": store.get("devices", [])})


@routes.post("/api/devices/import")
async def import_device(request: web.Request) -> web.Response:
    """Import a device by known address and rolling code — no radio pairing needed.

    Use this when a device was previously paired via ioBroker or another system
    and you know the 6-char hex address and the last rolling code value.

    Body: {"name": "...", "device_type": "shutter", "address": "A1B2C3", "rolling_code": 42}
    Returns: the new device dict, HTTP 201.
    """
    ctx: AppContext = request.app["ctx"]
    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Ungültiges JSON.")

    name = str(data.get("name", "")).strip()
    device_type = str(data.get("device_type", "shutter")).strip().lower()
    address = str(data.get("address", "")).strip().upper()
    rolling_code_raw = data.get("rolling_code", None)

    # --- Validation ---
    if not name:
        raise web.HTTPBadRequest(reason="name darf nicht leer sein.")
    if device_type not in _VALID_DEVICE_TYPES:
        raise web.HTTPBadRequest(
            reason=f"Unbekannter device_type: {device_type!r}. "
                   f"Erlaubt: {sorted(_VALID_DEVICE_TYPES)}"
        )
    if not _HEX_ADDR_RE.match(address):
        raise web.HTTPBadRequest(
            reason="address muss genau 6 Hex-Zeichen sein (z.B. 'A1B2C3')."
        )
    if rolling_code_raw is None:
        raise web.HTTPBadRequest(reason="rolling_code ist erforderlich.")
    try:
        rolling_code = int(rolling_code_raw)
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(reason="rolling_code muss eine ganze Zahl sein.")
    if rolling_code < 0:
        raise web.HTTPBadRequest(reason="rolling_code muss >= 0 sein.")

    # --- Persist via ioBroker-import logic ---
    PairingWizard.import_from_iobroker(
        name=name,
        device_type=device_type,
        address=address,
        rolling_code=rolling_code,
    )

    # --- Publish MQTT Discovery immediately (no restart required) ---
    if ctx.mqtt_client is not None:
        device_cfg = DeviceConfig(name=name, type=device_type, address=address, mode="A")
        dev = Device(device_cfg, ctx.gateway, ctx.mqtt_client)
        dev.setup()

    logger.info("Import: '%s' Adresse=%s RC=%d Typ=%s", name, address, rolling_code, device_type)
    return web.json_response(
        {
            "name": name,
            "type": device_type,
            "address": address,
            "rolling_code": rolling_code,
            "mode": "A",
        },
        status=201,
    )


@routes.get("/api/devices/{id}")
async def get_device(request: web.Request) -> web.Response:
    """Return a single device by hex address."""
    addr = request.match_info["id"].upper()
    store = _load()
    device = next(
        (d for d in store.get("devices", []) if d.get("address", "").upper() == addr),
        None,
    )
    if device is None:
        raise web.HTTPNotFound(reason=f"Gerät {addr} nicht gefunden.")
    return web.json_response(device)


@routes.post("/api/devices/{id}/cmd")
async def send_command(request: web.Request) -> web.Response:
    """Send an RTS command to a device.

    Body: {"action": "OPEN" | "CLOSE" | "STOP" | "MY_UP" | "MY_DOWN" | "PROG"}
    """
    ctx: AppContext = request.app["ctx"]
    addr = request.match_info["id"].upper()

    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Ungültiges JSON.")

    action = str(data.get("action", "")).upper()
    if action not in {"OPEN", "CLOSE", "STOP", "MY_UP", "MY_DOWN", "PROG"}:
        raise web.HTTPBadRequest(reason=f"Unbekannter Befehl: {action!r}")

    store = _load()
    device = next(
        (d for d in store.get("devices", []) if d.get("address", "").upper() == addr),
        None,
    )
    if device is None:
        raise web.HTTPNotFound(reason=f"Gerät {addr} nicht gefunden.")

    if not ctx.gateway.is_connected:
        raise web.HTTPServiceUnavailable(reason="Gateway nicht verbunden.")

    try:
        seq = build_rts_sequence(addr, action, device.get("name", ""))
    except ValueError as exc:
        raise web.HTTPBadRequest(reason=str(exc)) from exc

    try:
        for cmd in seq.commands:
            ctx.gateway.send_raw(cmd)
    except Exception as exc:
        logger.error("Sendefehler %s → %s: %s", addr, action, exc)
        log_rts_frame(seq, addr, action, success=False, error=str(exc))
        raise web.HTTPInternalServerError(reason=str(exc)) from exc

    log_rts_frame(seq, addr, action, success=True)

    logger.info("API: %s → %s gesendet.", addr, action)
    return web.json_response({"status": "sent", "action": action, "address": addr})


@routes.delete("/api/devices/{id}")
async def delete_device(request: web.Request) -> web.Response:
    """Remove a device from somfy_codes.json."""
    addr = request.match_info["id"].upper()
    store = _load()
    devices = store.get("devices", [])
    remaining = [d for d in devices if d.get("address", "").upper() != addr]
    if len(remaining) == len(devices):
        raise web.HTTPNotFound(reason=f"Gerät {addr} nicht gefunden.")
    store["devices"] = remaining
    _save_atomic(store)
    logger.info("API: Gerät %s gelöscht.", addr)
    return web.json_response({"status": "deleted", "address": addr})


# ---------- Wizard ----------


@routes.get("/api/wizard/status")
async def wizard_status(request: web.Request) -> web.Response:
    """Return the current pairing wizard state."""
    ctx: AppContext = request.app["ctx"]
    if ctx.wizard is None:
        return web.json_response(
            {"state": "IDLE", "address": "", "error": "", "timed_out": False}
        )
    return web.json_response(
        {
            "state": ctx.wizard.state.name,
            "address": ctx.wizard.address,
            "error": ctx.wizard._session.error,  # noqa: SLF001
            "timed_out": ctx.wizard.is_timed_out(),
        }
    )


@routes.post("/api/wizard/start")
async def wizard_start(request: web.Request) -> web.Response:
    """Start a new pairing session.

    Body: {"name": "Wohnzimmer Markise", "device_type": "awning"}
    """
    ctx: AppContext = request.app["ctx"]
    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Ungültiges JSON.")

    name = str(data.get("name", "")).strip()
    device_type = str(data.get("device_type", "shutter"))
    if not name:
        raise web.HTTPBadRequest(reason="Name ist erforderlich.")

    ctx.wizard = PairingWizard(ctx.gateway, ctx.config.address_prefix)
    addr = ctx.wizard.start(name, device_type)
    return web.json_response({"state": "ADDR_READY", "address": addr})


@routes.post("/api/wizard/send_prog")
async def wizard_send_prog(request: web.Request) -> web.Response:
    """Transmit the PROG telegram to the motor."""
    ctx: AppContext = request.app["ctx"]
    if ctx.wizard is None:
        raise web.HTTPBadRequest(reason="Keine aktive Wizard-Sitzung.")
    try:
        ctx.wizard.send_prog()
    except RuntimeError as exc:
        raise web.HTTPConflict(reason=str(exc)) from exc
    return web.json_response({"state": "PROG_SENT"})


@routes.post("/api/wizard/confirm")
async def wizard_confirm(request: web.Request) -> web.Response:
    """Confirm motor pairing (operator observed motor jog)."""
    ctx: AppContext = request.app["ctx"]
    if ctx.wizard is None:
        raise web.HTTPBadRequest(reason="Keine aktive Wizard-Sitzung.")
    try:
        ctx.wizard.confirm()
        cfg = ctx.wizard.get_device_config()
    except RuntimeError as exc:
        raise web.HTTPConflict(reason=str(exc)) from exc

    # Publish MQTT Discovery immediately so the device appears in HA without restart
    if ctx.mqtt_client is not None:
        device_cfg = DeviceConfig(
            name=cfg["name"],
            type=cfg["type"],
            address=cfg["address"],
            mode=cfg.get("mode", "A"),
        )
        dev = Device(device_cfg, ctx.gateway, ctx.mqtt_client)
        dev.setup()

    ctx.wizard = None
    return web.json_response({"state": "CONFIRMED", "device": cfg})


@routes.post("/api/wizard/cancel")
async def wizard_cancel(request: web.Request) -> web.Response:
    """Abort the current wizard session."""
    ctx: AppContext = request.app["ctx"]
    ctx.wizard = None
    return web.json_response({"state": "IDLE"})


# ---------- Settings ----------


@routes.get("/api/settings")
async def get_settings(request: web.Request) -> web.Response:
    """Return current app configuration."""
    ctx: AppContext = request.app["ctx"]
    c = ctx.config
    return web.json_response(
        {
            "usb_port": c.usb_port,
            "baudrate": c.baudrate,
            "mqtt_host": c.mqtt_host,
            "mqtt_port": c.mqtt_port,
            "mqtt_user": c.mqtt_user,
            "log_level": c.log_level.lower(),
            "address_prefix": c.address_prefix,
            "log_format": c.log_format,
            "simulation_mode": c.simulation_mode,
            "file_logging": c.file_logging,
            "timezone": c.timezone,
        }
    )


@routes.post("/api/settings")
async def post_settings(request: web.Request) -> web.Response:
    """Settings are managed via the Home Assistant app configuration."""
    return web.json_response(
        {
            "status": "readonly",
            "message": (
                "Einstellungen werden in Home Assistant unter "
                "Einstellungen → Apps → Somfy RTS → Konfiguration verwaltet. "
                "Änderungen erfordern einen Neustart der App."
            ),
        },
        status=200,
    )


# ---------- Logs ----------


@routes.get("/api/logs")
async def get_logs(request: web.Request) -> web.Response:
    """Return the last 100 RTS frame log entries."""
    ctx: AppContext = request.app["ctx"]
    return web.json_response({"entries": list(ctx.log_buffer)})


@routes.get("/api/logs/download")
async def download_log_file(request: web.Request) -> web.FileResponse:
    """Download the rotating RTS frame log file.

    Only available when file_logging is enabled in the add-on config.
    Returns 404 if the file does not exist yet.
    """
    log_path = pathlib.Path("/share/somfy_rts/rts_frames.log")
    if not log_path.exists():
        raise web.HTTPNotFound(
            reason="Log-Datei nicht vorhanden. Bitte file_logging in der App-Konfiguration aktivieren."
        )
    return web.FileResponse(
        log_path,
        headers={"Content-Disposition": 'attachment; filename="rts_frames.log"'},
    )

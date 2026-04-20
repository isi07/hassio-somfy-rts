"""REST API routes for the Somfy RTS Web UI.

Endpoints:
  GET  /api/status                    → gateway + simulation status
  GET  /api/config/debug              → {"debug_mode": bool} from app config
  GET  /api/devices                   → all devices from somfy_codes.json
  GET  /api/devices/{id}              → single device by address
  POST /api/devices/import            → add device by known address + rolling code (no pairing)
  POST /api/devices/{id}/cmd          → send RTS command (OPEN/CLOSE/STOP/MY_UP/MY_DOWN)
  POST /api/devices/{id}/prog-long    → send PROG Yr14 (put motor in pairing mode)
  POST /api/devices/{id}/prog-pair    → send PROG Yr4 (register/deregister remote)
  POST /api/devices/{id}/raw-cmd      → send any Layer-2 command with custom repeat (debug_mode)
  DELETE /api/devices/{id}            → remove device

  GET  /api/wizard/status             → current wizard state
  POST /api/wizard/start              → start pairing (name, device_type)
  POST /api/wizard/send_prog_long     → transmit PROG Yr14 (motor into pairing mode)
  POST /api/wizard/send_prog          → transmit PROG Yr4 (register virtual remote)
  POST /api/wizard/confirm            → confirm motor pairing
  POST /api/wizard/cancel             → abort wizard session

  GET  /api/settings                  → current config
  POST /api/settings                  → (read-only — managed via HA)

  GET  /api/logs                      → last 100 RTS frame log entries
  GET  /api/logs/download             → download /share/somfy_rts/rts_frames.log
"""

import json
import logging
import pathlib
import re
from collections import deque
from typing import Optional

from aiohttp import web

from .. import __version__
from ..config import Config, DeviceConfig
from ..device import Device, resolve_rts_action
from ..gateway import BaseGateway, SimGateway
from ..mqtt_client import MQTTClient
from ..rolling_code import _load, _save_atomic, get_current
from ..rts import build_rts_sequence, log_rts_frame
from ..wizard import PairingWizard

routes = web.RouteTableDef()
logger = logging.getLogger(__name__)

_HEX_ADDR_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
_VALID_DEVICE_TYPES = {"awning", "shutter", "blind", "screen", "gate", "light", "heater", "light_dimmer"}
_VALID_MODES = {"A", "B"}

# ha_platform je Gerätetyp — spiegelt device_profiles.json; für MQTT State-Publishing.
# "cover" ist der Default für alle Cover-Typen (awning/shutter/blind/screen/gate).
_HA_PLATFORM_BY_TYPE: dict = {
    "light": "light",
    "heater": "switch",
    "light_dimmer": None,  # kein Modus-A-Entity
}


def _device_ha_platform(device_type: str) -> Optional[str]:
    """Gibt die ha_platform aus device_profiles.json zurück ('cover', 'light', 'switch', None)."""
    return _HA_PLATFORM_BY_TYPE.get(device_type, "cover")


def _api_command_to_state(command: str) -> str:
    """Übersetzt HA-Semantik-Befehl in MQTT Cover-Zustandsstring für Modus-A-State-Publishing."""
    return {
        "OPEN":    "open",
        "CLOSE":   "closed",
        "STOP":    "stopped",
        "MY_UP":   "open",
        "MY_DOWN": "closed",
    }.get(command, "stopped")

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


# ---------- Config ----------


@routes.get("/api/config/debug")
async def get_debug_config(request: web.Request) -> web.Response:
    """Return whether debug mode is enabled in the app configuration."""
    ctx: AppContext = request.app["ctx"]
    return web.json_response({"debug_mode": ctx.config.debug_mode})


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
    mode = str(data.get("mode", "A")).strip().upper()

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
    if mode not in _VALID_MODES:
        raise web.HTTPBadRequest(reason=f"Ungültiger Modus: {mode!r}. Erlaubt: A, B")

    # --- Persist via ioBroker-import logic ---
    PairingWizard.import_from_iobroker(
        name=name,
        device_type=device_type,
        address=address,
        rolling_code=rolling_code,
        mode=mode,
    )

    # --- Publish MQTT Discovery + update Gateway device_count ---
    if ctx.mqtt_client is not None:
        device_cfg = DeviceConfig(name=name, type=device_type, address=address, mode=mode)
        dev = Device(device_cfg, ctx.gateway, ctx.mqtt_client)
        dev.setup()
        updated_count = len(_load().get("devices", []))
        ctx.mqtt_client.update_device_count(updated_count)

    logger.info("Import: '%s' Adresse=%s RC=%d Typ=%s Modus=%s", name, address, rolling_code, device_type, mode)
    return web.json_response(
        {
            "name": name,
            "type": device_type,
            "address": address,
            "rolling_code": rolling_code,
            "mode": mode,
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

    # Semantischen Befehl per command_map in RTS-Aktion übersetzen (z.B. awning OPEN↔CLOSE).
    # Entspricht dem Verhalten von Device._handle_command() im Modus A, damit WebUI und
    # MQTT-Cover identisch reagieren.
    device_type = device.get("device_type", "shutter")
    rts_action = resolve_rts_action(action, device_type)
    if rts_action != action:
        logger.info("API: %s %s → RTS %s (command_map)", addr, action, rts_action)

    try:
        seq = build_rts_sequence(addr, rts_action, device.get("name", ""))
    except ValueError as exc:
        raise web.HTTPBadRequest(reason=str(exc)) from exc

    try:
        for cmd in seq.commands:
            ctx.gateway.send_raw(cmd)
    except Exception as exc:
        logger.error("Sendefehler %s → %s: %s", addr, rts_action, exc)
        log_rts_frame(seq, addr, rts_action, success=False, error=str(exc))
        raise web.HTTPInternalServerError(reason=str(exc)) from exc

    log_rts_frame(seq, addr, rts_action, success=True)

    # MQTT-Diagnose-Updates nach erfolgreichem Senden:
    # rolling_code, last_command, raw_frame und state (Modus A) publizieren.
    if ctx.mqtt_client is not None:
        device_mode = device.get("mode", "A")
        device_cfg_mqtt = DeviceConfig(
            name=device.get("name", addr),
            type=device_type,
            address=addr,
            mode=device_mode,
        )
        rc = get_current(addr)
        ctx.mqtt_client.publish_diagnostic(device_cfg_mqtt, "rolling_code", str(rc))
        display_cmd = {"MY_UP": "MY", "MY_DOWN": "MY"}.get(rts_action, rts_action)
        ctx.mqtt_client.publish_diagnostic(device_cfg_mqtt, "last_command", display_cmd)
        ctx.mqtt_client.publish_json_attributes(device_cfg_mqtt, "last_command", {"raw_frame": seq.frame})
        # State nur in Modus A, nicht für PROG-Befehle
        if device_mode == "A" and action != "PROG":
            ha_platform = _device_ha_platform(device_type)
            if ha_platform in ("light", "switch"):
                state_val = "ON" if action == "OPEN" else "OFF"
            else:
                state_val = _api_command_to_state(action)
            ctx.mqtt_client.publish_state(device_cfg_mqtt, state_val)

    logger.info("API: %s → %s gesendet.", addr, rts_action)
    return web.json_response({"status": "sent", "action": rts_action, "address": addr})


async def _send_prog_with_repeat(
    request: web.Request, repeat: int, label: str
) -> web.Response:
    """Shared implementation for prog-long and prog-pair device endpoints."""
    ctx: AppContext = request.app["ctx"]
    addr = request.match_info["id"].upper()

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
        seq = build_rts_sequence(addr, "PROG", device.get("name", ""), repeat=repeat)
    except ValueError as exc:
        raise web.HTTPBadRequest(reason=str(exc)) from exc

    try:
        for cmd in seq.commands:
            ctx.gateway.send_raw(cmd)
    except Exception as exc:
        logger.error("Sendefehler %s → PROG Yr%d: %s", addr, repeat, exc)
        log_rts_frame(seq, addr, "PROG", success=False, error=str(exc))
        raise web.HTTPInternalServerError(reason=str(exc)) from exc

    log_rts_frame(seq, addr, "PROG", success=True)
    logger.info("API: %s → %s (Yr%d) gesendet.", addr, label, repeat)
    return web.json_response(
        {"status": "sent", "action": label, "address": addr, "repeat": repeat}
    )


@routes.post("/api/devices/{id}/prog-long")
async def send_prog_long(request: web.Request) -> web.Response:
    """Send PROG with repeat=14 (Yr14) — puts the motor in pairing mode.

    Use this instead of holding the PROG button on the original remote.
    After the motor enters pairing mode, send prog-pair to register the virtual remote.
    repeat=14 (~420 ms) is empirically verified: Yr13 too short, Yr16+ crashes NanoCUL.
    """
    return await _send_prog_with_repeat(request, repeat=14, label="PROG_LONG")


@routes.post("/api/devices/{id}/prog-pair")
async def send_prog_pair(request: web.Request) -> web.Response:
    """Send PROG with repeat=4 (Yr4) — registers or deregisters the virtual remote.

    The motor must already be in pairing mode (via prog-long or the original remote).
    """
    return await _send_prog_with_repeat(request, repeat=4, label="PROG_PAIR")


_RAW_CMD_VALID_ACTIONS = {"UP", "DOWN", "MY", "MY_UP", "MY_DOWN", "PROG"}


@routes.post("/api/devices/{id}/raw-cmd")
async def send_raw_cmd(request: web.Request) -> web.Response:
    """Send any Layer-2 RTS command with a custom Yr repeat value.

    Only available when debug_mode is enabled in the app configuration.
    Body: {"command": "UP|DOWN|MY|MY_UP|MY_DOWN|PROG", "repeat": 1..255}
    """
    ctx: AppContext = request.app["ctx"]
    if not ctx.config.debug_mode:
        raise web.HTTPForbidden(reason="raw-cmd ist nur im Debug-Modus verfügbar.")

    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Ungültiges JSON.")

    command = str(data.get("command", "")).upper()
    if command not in _RAW_CMD_VALID_ACTIONS:
        raise web.HTTPBadRequest(
            reason=f"Unbekannter Befehl: {command!r}. Erlaubt: {sorted(_RAW_CMD_VALID_ACTIONS)}"
        )

    repeat_raw = data.get("repeat", None)
    if repeat_raw is None:
        raise web.HTTPBadRequest(reason="repeat ist erforderlich.")
    try:
        repeat = int(repeat_raw)
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(reason="repeat muss eine ganze Zahl sein.")
    if not 1 <= repeat <= 255:
        raise web.HTTPBadRequest(reason="repeat muss zwischen 1 und 255 liegen.")

    addr = request.match_info["id"].upper()
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
        seq = build_rts_sequence(addr, command, device.get("name", ""), repeat=repeat)
    except ValueError as exc:
        raise web.HTTPBadRequest(reason=str(exc)) from exc

    try:
        for cmd in seq.commands:
            ctx.gateway.send_raw(cmd)
    except Exception as exc:
        logger.error("Sendefehler %s → %s Yr%d: %s", addr, command, repeat, exc)
        log_rts_frame(seq, addr, command, success=False, error=str(exc))
        raise web.HTTPInternalServerError(reason=str(exc)) from exc

    log_rts_frame(seq, addr, command, success=True)
    logger.info("API raw-cmd: %s → %s Yr%d gesendet.", addr, command, repeat)
    return web.json_response(
        {"status": "sent", "command": command, "address": addr, "repeat": repeat}
    )


@routes.delete("/api/devices/{id}")
async def delete_device(request: web.Request) -> web.Response:
    """Remove a device from somfy_codes.json and clear its HA Discovery topics."""
    ctx: AppContext = request.app["ctx"]
    addr = request.match_info["id"].upper()
    store = _load()
    devices = store.get("devices", [])
    device_dict = next(
        (d for d in devices if d.get("address", "").upper() == addr),
        None,
    )
    if device_dict is None:
        raise web.HTTPNotFound(reason=f"Gerät {addr} nicht gefunden.")

    # Clear MQTT Discovery topics before removing from the store
    if ctx.mqtt_client is not None:
        device_cfg = DeviceConfig(
            name=device_dict.get("name", addr),
            type=device_dict.get("device_type", "shutter"),
            address=addr,
            mode=device_dict.get("mode", "A"),
        )
        ctx.mqtt_client.unregister_device(device_cfg)

    remaining = [d for d in devices if d.get("address", "").upper() != addr]
    store["devices"] = remaining
    _save_atomic(store)

    if ctx.mqtt_client is not None:
        ctx.mqtt_client.update_device_count(len(remaining))

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
    mode = str(data.get("mode", "A")).strip().upper()
    if not name:
        raise web.HTTPBadRequest(reason="Name ist erforderlich.")
    if mode not in _VALID_MODES:
        raise web.HTTPBadRequest(reason=f"Ungültiger Modus: {mode!r}. Erlaubt: A, B")

    ctx.wizard = PairingWizard(ctx.gateway, ctx.config.address_prefix)
    addr = ctx.wizard.start(name, device_type, mode)
    return web.json_response({"state": "ADDR_READY", "address": addr})


@routes.post("/api/wizard/send_prog_long")
async def wizard_send_prog_long(request: web.Request) -> web.Response:
    """Transmit PROG Yr14 to put the motor in pairing mode (no original remote needed).

    Wizard state remains ADDR_READY — follow up with /api/wizard/send_prog.
    """
    ctx: AppContext = request.app["ctx"]
    if ctx.wizard is None:
        raise web.HTTPBadRequest(reason="Keine aktive Wizard-Sitzung.")
    try:
        ctx.wizard.send_prog_long()
    except (RuntimeError, Exception) as exc:
        raise web.HTTPConflict(reason=str(exc)) from exc
    return web.json_response({"state": ctx.wizard.state.name, "repeat": 14})


@routes.post("/api/wizard/send_prog")
async def wizard_send_prog(request: web.Request) -> web.Response:
    """Transmit PROG Yr4 to register the virtual remote with the motor."""
    ctx: AppContext = request.app["ctx"]
    if ctx.wizard is None:
        raise web.HTTPBadRequest(reason="Keine aktive Wizard-Sitzung.")
    try:
        ctx.wizard.send_prog_pair()
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
        updated_count = len(_load().get("devices", []))
        ctx.mqtt_client.update_device_count(updated_count)

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
            "debug_mode": c.debug_mode,
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

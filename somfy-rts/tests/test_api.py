"""Tests for the REST API (web/api.py) using aiohttp test client."""

import json
import pytest

from somfy_rts.config import Config
from somfy_rts.gateway import SimGateway
from somfy_rts.web.api import AppContext
from somfy_rts.web.server import create_app


# ---------- Fixtures ----------


@pytest.fixture
def ctx(tmp_codes_path):
    """AppContext with a connected SimGateway and default Config."""
    gw = SimGateway()
    gw.connect()
    return AppContext(gateway=gw, config=Config())


@pytest.fixture
async def client(aiohttp_client, ctx):
    """aiohttp test client wrapping the API app."""
    app = create_app(ctx)
    return await aiohttp_client(app)


# ---------- GET /api/status ----------


async def test_status_simulation_true(client, ctx):
    """SimGateway must cause simulation=true in the status response."""
    resp = await client.get("/api/status")
    assert resp.status == 200
    data = await resp.json()
    assert data["simulation"] is True
    assert data["connected"] is True
    assert data["port"] == "sim://localhost"


# ---------- GET /api/devices ----------


async def test_get_devices_empty(client):
    """Fresh somfy_codes.json returns an empty device list."""
    resp = await client.get("/api/devices")
    assert resp.status == 200
    data = await resp.json()
    assert data["devices"] == []


async def test_get_devices_after_insert(client, tmp_codes_path):
    """Devices written to somfy_codes.json appear in the API response."""
    import somfy_rts.rolling_code as rc
    store = rc._load()
    store["devices"].append({"address": "A00001", "name": "Test", "rolling_code": 5})
    rc._save_atomic(store)

    resp = await client.get("/api/devices")
    assert resp.status == 200
    data = await resp.json()
    assert len(data["devices"]) == 1
    assert data["devices"][0]["address"] == "A00001"


# ---------- GET /api/devices/{id} ----------


async def test_get_device_not_found(client):
    resp = await client.get("/api/devices/FFFFFF")
    assert resp.status == 404


async def test_get_device_found(client, tmp_codes_path):
    import somfy_rts.rolling_code as rc
    store = rc._load()
    store["devices"].append({"address": "B00001", "name": "Küche", "rolling_code": 3})
    rc._save_atomic(store)

    resp = await client.get("/api/devices/B00001")
    assert resp.status == 200
    data = await resp.json()
    assert data["address"] == "B00001"
    assert data["name"] == "Küche"


# ---------- POST /api/devices/{id}/cmd ----------


async def test_send_command_open(client, ctx, tmp_codes_path):
    """Sending OPEN to a known device relays two culfw commands to the gateway."""
    import somfy_rts.rolling_code as rc
    store = rc._load()
    store["devices"].append({"address": "A00001", "name": "Markise", "rolling_code": 0})
    rc._save_atomic(store)

    resp = await client.post(
        "/api/devices/A00001/cmd",
        data=json.dumps({"action": "OPEN"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "sent"
    assert data["action"] == "OPEN"
    # SimGateway must have received exactly two commands: Yr1 + YsA0...
    assert ctx.gateway.sent_commands[0] == "Yr1"
    assert ctx.gateway.sent_commands[1].startswith("YsA0")


async def test_send_command_unknown_action(client, tmp_codes_path):
    import somfy_rts.rolling_code as rc
    store = rc._load()
    store["devices"].append({"address": "A00001", "name": "X", "rolling_code": 0})
    rc._save_atomic(store)

    resp = await client.post(
        "/api/devices/A00001/cmd",
        data=json.dumps({"action": "EXPLODE"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 400


async def test_send_command_device_not_found(client):
    resp = await client.post(
        "/api/devices/FFFFFF/cmd",
        data=json.dumps({"action": "STOP"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 404


# ---------- DELETE /api/devices/{id} ----------


async def test_delete_device(client, tmp_codes_path):
    import somfy_rts.rolling_code as rc
    store = rc._load()
    store["devices"].append({"address": "C00001", "name": "Del", "rolling_code": 1})
    rc._save_atomic(store)

    resp = await client.delete("/api/devices/C00001")
    assert resp.status == 200

    # Verify device is gone
    resp2 = await client.get("/api/devices/C00001")
    assert resp2.status == 404


async def test_delete_device_not_found(client):
    resp = await client.delete("/api/devices/FFFFFF")
    assert resp.status == 404


# ---------- GET /api/wizard/status ----------


async def test_wizard_status_idle(client):
    """Wizard returns IDLE when no session is active."""
    resp = await client.get("/api/wizard/status")
    assert resp.status == 200
    data = await resp.json()
    assert data["state"] == "IDLE"
    assert data["address"] == ""


# ---------- POST /api/wizard/start ----------


async def test_wizard_start(client, tmp_codes_path):
    resp = await client.post(
        "/api/wizard/start",
        data=json.dumps({"name": "Test Markise", "device_type": "awning"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["state"] == "ADDR_READY"
    assert len(data["address"]) == 6


async def test_wizard_start_no_name(client):
    resp = await client.post(
        "/api/wizard/start",
        data=json.dumps({"name": "", "device_type": "shutter"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 400


# ---------- POST /api/wizard/cancel ----------


async def test_wizard_cancel(client, tmp_codes_path):
    # Start first
    await client.post(
        "/api/wizard/start",
        data=json.dumps({"name": "X", "device_type": "shutter"}),
        headers={"Content-Type": "application/json"},
    )
    resp = await client.post("/api/wizard/cancel")
    assert resp.status == 200
    data = await resp.json()
    assert data["state"] == "IDLE"


# ---------- Full wizard flow ----------


async def test_wizard_full_flow(client, ctx, tmp_codes_path):
    """Start → send_prog → confirm completes successfully."""
    # Step 1: start
    r1 = await client.post(
        "/api/wizard/start",
        data=json.dumps({"name": "Wohnzimmer", "device_type": "shutter"}),
        headers={"Content-Type": "application/json"},
    )
    assert r1.status == 200

    # Step 2: send_prog (SimGateway accepts without hardware)
    r2 = await client.post("/api/wizard/send_prog")
    assert r2.status == 200
    assert (await r2.json())["state"] == "PROG_SENT"

    # Step 3: confirm
    r3 = await client.post("/api/wizard/confirm")
    assert r3.status == 200
    d3 = await r3.json()
    assert d3["state"] == "CONFIRMED"
    assert d3["device"]["name"] == "Wohnzimmer"
    assert d3["device"]["type"] == "shutter"


# ---------- GET /api/settings ----------


async def test_get_settings(client):
    resp = await client.get("/api/settings")
    assert resp.status == 200
    data = await resp.json()
    assert "usb_port" in data
    assert "mqtt_host" in data
    assert "log_format" in data
    assert "simulation_mode" in data


# ---------- POST /api/settings ----------


async def test_post_settings_readonly(client):
    resp = await client.post(
        "/api/settings",
        data=json.dumps({"log_level": "debug"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "readonly"


# ---------- GET /api/logs ----------


async def test_get_logs_empty(client):
    resp = await client.get("/api/logs")
    assert resp.status == 200
    data = await resp.json()
    assert data["entries"] == []


async def test_get_logs_after_command(client, ctx, tmp_codes_path):
    """After sending a command, the log buffer contains frame entries."""
    from somfy_rts.rts_logger import init as init_rts_logger
    init_rts_logger(log_format="text")
    ctx.attach_log_handler()

    import somfy_rts.rolling_code as rc
    store = rc._load()
    store["devices"].append({"address": "A00001", "name": "X", "rolling_code": 0})
    rc._save_atomic(store)

    await client.post(
        "/api/devices/A00001/cmd",
        data=json.dumps({"action": "STOP"}),
        headers={"Content-Type": "application/json"},
    )

    resp = await client.get("/api/logs")
    data = await resp.json()
    assert len(data["entries"]) > 0

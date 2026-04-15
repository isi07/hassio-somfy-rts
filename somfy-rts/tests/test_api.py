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


async def test_send_command_awning_open_sends_rts_close(client, ctx, tmp_codes_path):
    """REST API: awning OPEN → command_map → RTS CLOSE (Ausfahren = ctrl 0x4 = 0x40)."""
    import somfy_rts.rolling_code as rc
    store = rc._load()
    store["devices"].append({
        "address": "A00002", "name": "Markise", "rolling_code": 0, "device_type": "awning",
    })
    rc._save_atomic(store)

    resp = await client.post(
        "/api/devices/A00002/cmd",
        data=json.dumps({"action": "OPEN"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    data = await resp.json()
    # Response reports the actual RTS action sent (CLOSE after command_map)
    assert data["action"] == "CLOSE"
    # Telegram Byte1 must be 0x40 (CLOSE ctrl=0x4 shifted to high nibble)
    telegram = ctx.gateway.sent_commands[1]
    assert telegram[4:6] == "40", f"Expected 0x40 (CLOSE), got {telegram[4:6]!r}: {telegram}"


async def test_send_command_awning_close_sends_rts_open(client, ctx, tmp_codes_path):
    """REST API: awning CLOSE → command_map → RTS OPEN (Einfahren = ctrl 0x2 = 0x20)."""
    import somfy_rts.rolling_code as rc
    store = rc._load()
    store["devices"].append({
        "address": "A00003", "name": "Markise2", "rolling_code": 0, "device_type": "awning",
    })
    rc._save_atomic(store)

    resp = await client.post(
        "/api/devices/A00003/cmd",
        data=json.dumps({"action": "CLOSE"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["action"] == "OPEN"
    telegram = ctx.gateway.sent_commands[1]
    assert telegram[4:6] == "20", f"Expected 0x20 (OPEN), got {telegram[4:6]!r}: {telegram}"


async def test_send_command_awning_stop_unchanged(client, ctx, tmp_codes_path):
    """REST API: awning STOP is not in command_map and passes through unchanged."""
    import somfy_rts.rolling_code as rc
    store = rc._load()
    store["devices"].append({
        "address": "A00004", "name": "Markise3", "rolling_code": 0, "device_type": "awning",
    })
    rc._save_atomic(store)

    resp = await client.post(
        "/api/devices/A00004/cmd",
        data=json.dumps({"action": "STOP"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["action"] == "STOP"
    telegram = ctx.gateway.sent_commands[1]
    assert telegram[4:6] == "10", f"Expected 0x10 (STOP), got {telegram[4:6]!r}: {telegram}"


async def test_send_command_shutter_open_unchanged(client, ctx, tmp_codes_path):
    """REST API: shutter has no command_map — OPEN stays OPEN (0x20), no regression."""
    import somfy_rts.rolling_code as rc
    store = rc._load()
    store["devices"].append({
        "address": "A00005", "name": "Rollladen", "rolling_code": 0, "device_type": "shutter",
    })
    rc._save_atomic(store)

    resp = await client.post(
        "/api/devices/A00005/cmd",
        data=json.dumps({"action": "OPEN"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["action"] == "OPEN"
    telegram = ctx.gateway.sent_commands[1]
    assert telegram[4:6] == "20"


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


# ---------- POST /api/devices/import ----------


class TestImportDevice:
    """Tests for POST /api/devices/import."""

    async def test_import_success_201(self, client, tmp_codes_path):
        """Valid import returns HTTP 201 and the device dict."""
        resp = await client.post(
            "/api/devices/import",
            data=json.dumps({
                "name": "Carport Markise",
                "device_type": "awning",
                "address": "A1B2C3",
                "rolling_code": 42,
            }),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 201
        data = await resp.json()
        assert data["name"] == "Carport Markise"
        assert data["address"] == "A1B2C3"
        assert data["rolling_code"] == 42
        assert data["type"] == "awning"
        assert data["mode"] == "A"

    async def test_import_persists_to_codes_json(self, client, tmp_codes_path):
        """After import the device appears in somfy_codes.json."""
        import somfy_rts.rolling_code as rc
        await client.post(
            "/api/devices/import",
            data=json.dumps({
                "name": "Kellerfenster",
                "device_type": "shutter",
                "address": "B00042",
                "rolling_code": 10,
            }),
            headers={"Content-Type": "application/json"},
        )
        store = rc._load()
        addresses = [d["address"].upper() for d in store.get("devices", [])]
        assert "B00042" in addresses

    async def test_import_device_type_persisted(self, client, tmp_codes_path):
        """device_type is saved to somfy_codes.json (regression: was not persisted)."""
        import somfy_rts.rolling_code as rc
        await client.post(
            "/api/devices/import",
            data=json.dumps({
                "name": "Carport Markise",
                "device_type": "awning",
                "address": "C0DE42",
                "rolling_code": 55,
            }),
            headers={"Content-Type": "application/json"},
        )
        store = rc._load()
        device = next(
            (d for d in store.get("devices", []) if d["address"].upper() == "C0DE42"),
            None,
        )
        assert device is not None
        assert device["device_type"] == "awning"

    async def test_import_address_case_insensitive(self, client, tmp_codes_path):
        """Lowercase address is accepted and normalised to uppercase."""
        resp = await client.post(
            "/api/devices/import",
            data=json.dumps({
                "name": "Test",
                "device_type": "shutter",
                "address": "a1b2c3",
                "rolling_code": 0,
            }),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 201
        data = await resp.json()
        assert data["address"] == "A1B2C3"

    async def test_import_rolling_code_zero(self, client, tmp_codes_path):
        """Rolling code 0 is valid."""
        resp = await client.post(
            "/api/devices/import",
            data=json.dumps({"name": "X", "device_type": "shutter",
                             "address": "C00001", "rolling_code": 0}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 201

    async def test_import_missing_name_400(self, client, tmp_codes_path):
        """Empty name is rejected with 400."""
        resp = await client.post(
            "/api/devices/import",
            data=json.dumps({"name": "", "device_type": "shutter",
                             "address": "A1B2C3", "rolling_code": 1}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    async def test_import_invalid_address_short_400(self, client, tmp_codes_path):
        """Address shorter than 6 chars is rejected with 400."""
        resp = await client.post(
            "/api/devices/import",
            data=json.dumps({"name": "X", "device_type": "shutter",
                             "address": "A1B2", "rolling_code": 1}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    async def test_import_invalid_address_non_hex_400(self, client, tmp_codes_path):
        """Address with non-hex characters is rejected with 400."""
        resp = await client.post(
            "/api/devices/import",
            data=json.dumps({"name": "X", "device_type": "shutter",
                             "address": "ZZZZZZ", "rolling_code": 1}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    async def test_import_negative_rolling_code_400(self, client, tmp_codes_path):
        """Negative rolling code is rejected with 400."""
        resp = await client.post(
            "/api/devices/import",
            data=json.dumps({"name": "X", "device_type": "shutter",
                             "address": "A1B2C3", "rolling_code": -1}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    async def test_import_unknown_device_type_400(self, client, tmp_codes_path):
        """Unknown device_type is rejected with 400."""
        resp = await client.post(
            "/api/devices/import",
            data=json.dumps({"name": "X", "device_type": "spaceship",
                             "address": "A1B2C3", "rolling_code": 1}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    async def test_import_mode_b_success(self, client, tmp_codes_path):
        """Importing with mode='B' returns HTTP 201 and mode B in response."""
        resp = await client.post(
            "/api/devices/import",
            data=json.dumps({"name": "Jalousie Modus B", "device_type": "blind",
                             "address": "D00001", "rolling_code": 5, "mode": "B"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 201
        data = await resp.json()
        assert data["mode"] == "B"

    async def test_import_invalid_mode_400(self, client, tmp_codes_path):
        """Unknown mode is rejected with 400."""
        resp = await client.post(
            "/api/devices/import",
            data=json.dumps({"name": "X", "device_type": "shutter",
                             "address": "A1B2C3", "rolling_code": 1, "mode": "C"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    async def test_import_device_appears_in_device_list(self, client, tmp_codes_path):
        """After import, GET /api/devices lists the new device."""
        await client.post(
            "/api/devices/import",
            data=json.dumps({"name": "Terrasse", "device_type": "awning",
                             "address": "AABBCC", "rolling_code": 5}),
            headers={"Content-Type": "application/json"},
        )
        resp = await client.get("/api/devices")
        assert resp.status == 200
        devices = (await resp.json())["devices"]
        assert any(d["address"].upper() == "AABBCC" for d in devices)

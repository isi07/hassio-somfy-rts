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
    # Response reports Layer-2 action (OPEN→UP after command_map for shutter)
    assert data["action"] == "UP"
    # SimGateway must have received exactly two commands: Yr1 + YsA0...
    assert ctx.gateway.sent_commands[0] == "Yr1"
    assert ctx.gateway.sent_commands[1].startswith("YsA0")


async def test_send_command_awning_open_sends_rts_down(client, ctx, tmp_codes_path):
    """REST API: awning OPEN → command_map → Layer-2 DOWN (Ausfahren = ctrl 0x4 = 0x40)."""
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
    # Response reports Layer-2 action (DOWN after command_map for awning)
    assert data["action"] == "DOWN"
    # Telegram Byte1 must be 0x40 (DOWN ctrl=0x4 shifted to high nibble)
    telegram = ctx.gateway.sent_commands[1]
    assert telegram[4:6] == "40", f"Expected 0x40 (DOWN), got {telegram[4:6]!r}: {telegram}"


async def test_send_command_awning_close_sends_rts_up(client, ctx, tmp_codes_path):
    """REST API: awning CLOSE → command_map → Layer-2 UP (Einfahren = ctrl 0x2 = 0x20)."""
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
    assert data["action"] == "UP"
    telegram = ctx.gateway.sent_commands[1]
    assert telegram[4:6] == "20", f"Expected 0x20 (UP), got {telegram[4:6]!r}: {telegram}"


async def test_send_command_awning_stop_sends_rts_my(client, ctx, tmp_codes_path):
    """REST API: awning STOP → command_map → Layer-2 MY (ctrl 0x1 = 0x10)."""
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
    assert data["action"] == "MY"
    telegram = ctx.gateway.sent_commands[1]
    assert telegram[4:6] == "10", f"Expected 0x10 (MY), got {telegram[4:6]!r}: {telegram}"


async def test_send_command_shutter_open_maps_to_up(client, ctx, tmp_codes_path):
    """REST API: shutter OPEN → command_map → UP (0x20)."""
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
    assert data["action"] == "UP"
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


async def test_delete_device_calls_unregister(aiohttp_client, tmp_codes_path):
    """DELETE must call mqtt_client.unregister_device() when an MQTT client is set."""
    from unittest.mock import MagicMock
    import somfy_rts.rolling_code as rc
    from somfy_rts.config import Config
    from somfy_rts.gateway import SimGateway
    from somfy_rts.mqtt_client import MQTTClient
    from somfy_rts.web.server import create_app

    # Prepare store with a Mode-A device
    store = rc._load()
    store["devices"].append({
        "address": "D00001",
        "name": "Garten Markise",
        "rolling_code": 7,
        "device_type": "awning",
        "mode": "A",
    })
    rc._save_atomic(store)

    # Create a mock MQTTClient
    mock_mqtt = MagicMock(spec=MQTTClient)

    gw = SimGateway()
    gw.connect()
    ctx = AppContext(gateway=gw, config=Config(), mqtt_client=mock_mqtt)
    app = create_app(ctx)
    test_client = await aiohttp_client(app)

    resp = await test_client.delete("/api/devices/D00001")
    assert resp.status == 200

    # unregister_device() must have been called exactly once
    mock_mqtt.unregister_device.assert_called_once()
    # device_count updated after deletion
    mock_mqtt.update_device_count.assert_called_once_with(0)


async def test_delete_device_unregister_uses_correct_mode(aiohttp_client, tmp_codes_path):
    """unregister_device() must receive the DeviceConfig with the correct mode."""
    from unittest.mock import MagicMock
    import somfy_rts.rolling_code as rc
    from somfy_rts.config import Config, DeviceConfig
    from somfy_rts.gateway import SimGateway
    from somfy_rts.mqtt_client import MQTTClient
    from somfy_rts.web.server import create_app

    store = rc._load()
    store["devices"].append({
        "address": "E00001",
        "name": "Küche Rollladen",
        "rolling_code": 3,
        "device_type": "shutter",
        "mode": "B",
    })
    rc._save_atomic(store)

    mock_mqtt = MagicMock(spec=MQTTClient)

    gw = SimGateway()
    gw.connect()
    ctx = AppContext(gateway=gw, config=Config(), mqtt_client=mock_mqtt)
    app = create_app(ctx)
    test_client = await aiohttp_client(app)

    await test_client.delete("/api/devices/E00001")

    called_device: DeviceConfig = mock_mqtt.unregister_device.call_args[0][0]
    assert called_device.address == "E00001"
    assert called_device.mode == "B"
    assert called_device.type == "shutter"


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


# ---------- POST /api/devices/{id}/prog-long and prog-pair ----------


class TestProgEndpoints:
    """Tests for the PROG Long (Yr14) and PROG Pair (Yr4) device endpoints."""

    async def _insert_device(self, addr: str = "A00010") -> None:
        import somfy_rts.rolling_code as rc
        store = rc._load()
        store["devices"].append({
            "address": addr, "name": "Testgerät", "rolling_code": 0, "device_type": "shutter",
        })
        rc._save_atomic(store)

    async def test_prog_long_sends_yr14(self, client, ctx, tmp_codes_path):
        """prog-long endpoint sends Yr14 as the first gateway command."""
        await self._insert_device()
        resp = await client.post("/api/devices/A00010/prog-long")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "sent"
        assert data["repeat"] == 14
        assert ctx.gateway.sent_commands[0] == "Yr14"
        assert ctx.gateway.sent_commands[1].startswith("YsA0")
        # PROG CMD byte must be 0x80
        assert ctx.gateway.sent_commands[1][4:6] == "80"

    async def test_prog_pair_sends_yr4(self, client, ctx, tmp_codes_path):
        """prog-pair endpoint sends Yr4 as the first gateway command."""
        await self._insert_device()
        resp = await client.post("/api/devices/A00010/prog-pair")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "sent"
        assert data["repeat"] == 4
        assert ctx.gateway.sent_commands[0] == "Yr4"
        assert ctx.gateway.sent_commands[1].startswith("YsA0")
        assert ctx.gateway.sent_commands[1][4:6] == "80"

    async def test_prog_long_device_not_found(self, client):
        resp = await client.post("/api/devices/FFFFFF/prog-long")
        assert resp.status == 404

    async def test_prog_pair_device_not_found(self, client):
        resp = await client.post("/api/devices/FFFFFF/prog-pair")
        assert resp.status == 404


# ---------- POST /api/wizard/send_prog_long ----------


async def test_wizard_send_prog_long(client, ctx, tmp_codes_path):
    """Wizard send_prog_long keeps state at ADDR_READY and sends Yr14."""
    # Start wizard first
    await client.post(
        "/api/wizard/start",
        data=json.dumps({"name": "Testgerät", "device_type": "shutter"}),
        headers={"Content-Type": "application/json"},
    )
    resp = await client.post("/api/wizard/send_prog_long")
    assert resp.status == 200
    data = await resp.json()
    # State remains ADDR_READY — not PROG_SENT
    assert data["state"] == "ADDR_READY"
    assert data["repeat"] == 14
    assert ctx.gateway.sent_commands[0] == "Yr14"


async def test_wizard_send_prog_long_no_session(client):
    """send_prog_long without an active wizard session returns 400."""
    resp = await client.post("/api/wizard/send_prog_long")
    assert resp.status == 400


async def test_wizard_full_flow_with_prog_long(client, ctx, tmp_codes_path):
    """Full wizard flow using send_prog_long + send_prog completes successfully."""
    # Start
    r1 = await client.post(
        "/api/wizard/start",
        data=json.dumps({"name": "Wohnzimmer", "device_type": "shutter"}),
        headers={"Content-Type": "application/json"},
    )
    assert r1.status == 200

    # Send PROG Lang (Yr14) — motor enters pairing mode
    r2 = await client.post("/api/wizard/send_prog_long")
    assert r2.status == 200
    assert (await r2.json())["state"] == "ADDR_READY"

    # Send PROG Pair (Yr4) — register virtual remote
    r3 = await client.post("/api/wizard/send_prog")
    assert r3.status == 200
    assert (await r3.json())["state"] == "PROG_SENT"

    # Confirm
    r4 = await client.post("/api/wizard/confirm")
    assert r4.status == 200
    assert (await r4.json())["state"] == "CONFIRMED"


# ---------- GET /api/config/debug ----------


async def test_get_debug_config_default_false(client):
    """Default config returns debug_mode=false."""
    resp = await client.get("/api/config/debug")
    assert resp.status == 200
    data = await resp.json()
    assert data["debug_mode"] is False


async def test_get_debug_config_true(aiohttp_client, tmp_codes_path):
    """Config with debug_mode=True returns debug_mode=true."""
    from somfy_rts.config import Config
    from somfy_rts.gateway import SimGateway
    from somfy_rts.web.server import create_app

    gw = SimGateway()
    gw.connect()
    ctx = AppContext(gateway=gw, config=Config(debug_mode=True))
    app = create_app(ctx)
    test_client = await aiohttp_client(app)

    resp = await test_client.get("/api/config/debug")
    assert resp.status == 200
    data = await resp.json()
    assert data["debug_mode"] is True


# ---------- POST /api/devices/{id}/raw-cmd ----------


class TestRawCmd:
    """Tests for POST /api/devices/{id}/raw-cmd (requires debug_mode=True)."""

    @pytest.fixture
    async def debug_client(self, aiohttp_client, tmp_codes_path):
        """aiohttp test client with debug_mode=True."""
        from somfy_rts.config import Config
        from somfy_rts.gateway import SimGateway
        from somfy_rts.web.server import create_app

        gw = SimGateway()
        gw.connect()
        self._ctx = AppContext(gateway=gw, config=Config(debug_mode=True))
        app = create_app(self._ctx)
        return await aiohttp_client(app)

    async def _insert_device(self, addr: str = "A00020") -> None:
        import somfy_rts.rolling_code as rc
        store = rc._load()
        store["devices"].append({
            "address": addr, "name": "Debug Gerät", "rolling_code": 0, "device_type": "shutter",
        })
        rc._save_atomic(store)

    async def test_raw_cmd_prog_custom_repeat(self, debug_client, tmp_codes_path):
        """raw-cmd PROG with repeat=17 sends Yr17 as first gateway command."""
        await self._insert_device()
        resp = await debug_client.post(
            "/api/devices/A00020/raw-cmd",
            data=json.dumps({"command": "PROG", "repeat": 17}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "sent"
        assert data["command"] == "PROG"
        assert data["repeat"] == 17
        assert self._ctx.gateway.sent_commands[0] == "Yr17"
        assert self._ctx.gateway.sent_commands[1].startswith("YsA0")
        assert self._ctx.gateway.sent_commands[1][4:6] == "80"

    async def test_raw_cmd_up(self, debug_client, tmp_codes_path):
        """raw-cmd UP sends Yr with correct UP telegram (0x20)."""
        await self._insert_device()
        resp = await debug_client.post(
            "/api/devices/A00020/raw-cmd",
            data=json.dumps({"command": "UP", "repeat": 1}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        assert self._ctx.gateway.sent_commands[0] == "Yr1"
        assert self._ctx.gateway.sent_commands[1][4:6] == "20"

    async def test_raw_cmd_repeat_1(self, debug_client, tmp_codes_path):
        """Minimum repeat value 1 is accepted."""
        await self._insert_device()
        resp = await debug_client.post(
            "/api/devices/A00020/raw-cmd",
            data=json.dumps({"command": "PROG", "repeat": 1}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        assert self._ctx.gateway.sent_commands[0] == "Yr1"

    async def test_raw_cmd_repeat_255(self, debug_client, tmp_codes_path):
        """Maximum repeat value 255 is accepted."""
        await self._insert_device()
        resp = await debug_client.post(
            "/api/devices/A00020/raw-cmd",
            data=json.dumps({"command": "PROG", "repeat": 255}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        assert self._ctx.gateway.sent_commands[0] == "Yr255"

    async def test_raw_cmd_repeat_0_rejected(self, debug_client, tmp_codes_path):
        """repeat=0 is below minimum — must return 400."""
        await self._insert_device()
        resp = await debug_client.post(
            "/api/devices/A00020/raw-cmd",
            data=json.dumps({"command": "PROG", "repeat": 0}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    async def test_raw_cmd_repeat_256_rejected(self, debug_client, tmp_codes_path):
        """repeat=256 exceeds uint8 range — must return 400."""
        await self._insert_device()
        resp = await debug_client.post(
            "/api/devices/A00020/raw-cmd",
            data=json.dumps({"command": "PROG", "repeat": 256}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    async def test_raw_cmd_missing_repeat_rejected(self, debug_client, tmp_codes_path):
        """Missing repeat field must return 400."""
        await self._insert_device()
        resp = await debug_client.post(
            "/api/devices/A00020/raw-cmd",
            data=json.dumps({"command": "PROG"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    async def test_raw_cmd_invalid_command_rejected(self, debug_client, tmp_codes_path):
        """Unknown command must return 400."""
        await self._insert_device()
        resp = await debug_client.post(
            "/api/devices/A00020/raw-cmd",
            data=json.dumps({"command": "EXPLODE", "repeat": 4}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    async def test_raw_cmd_device_not_found(self, debug_client):
        """Unknown address must return 404."""
        resp = await debug_client.post(
            "/api/devices/FFFFFF/raw-cmd",
            data=json.dumps({"command": "PROG", "repeat": 8}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 404

    async def test_raw_cmd_forbidden_without_debug_mode(self, client, tmp_codes_path):
        """raw-cmd returns 403 when debug_mode is False (default)."""
        await self._insert_device()
        resp = await client.post(
            "/api/devices/A00020/raw-cmd",
            data=json.dumps({"command": "PROG", "repeat": 4}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 403

    async def test_raw_cmd_response_fields(self, debug_client, tmp_codes_path):
        """Response body contains command, address and repeat fields."""
        await self._insert_device()
        resp = await debug_client.post(
            "/api/devices/A00020/raw-cmd",
            data=json.dumps({"command": "PROG", "repeat": 4}),
            headers={"Content-Type": "application/json"},
        )
        data = await resp.json()
        assert data["address"] == "A00020"
        assert data["command"] == "PROG"
        assert data["repeat"] == 4

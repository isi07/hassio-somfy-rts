"""Tests for main.py — waiting for the MQTT broker at startup."""

import asyncio
from unittest.mock import MagicMock

from somfy_rts.main import wait_for_mqtt


async def test_wait_for_mqtt_returns_true_once_connected():
    client = MagicMock()
    states = iter([False, False, True])
    type(client).is_connected = property(lambda self: next(states))
    shutdown = asyncio.Event()
    assert await wait_for_mqtt(client, shutdown, poll_s=0.01) is True


async def test_wait_for_mqtt_returns_false_on_shutdown():
    client = MagicMock()
    type(client).is_connected = property(lambda self: False)
    shutdown = asyncio.Event()
    asyncio.get_running_loop().call_later(0.05, shutdown.set)
    assert await wait_for_mqtt(client, shutdown, poll_s=0.01) is False


async def test_wait_for_mqtt_logs_waiting_once(caplog):
    import logging

    client = MagicMock()
    states = iter([False, False, False, True])
    type(client).is_connected = property(lambda self: next(states))
    with caplog.at_level(logging.INFO):
        await wait_for_mqtt(client, asyncio.Event(), poll_s=0.01)
    assert caplog.text.count("Warte auf Verbindung zum MQTT-Broker") == 1


# ---------- Gateway retry and startup order (watchdog needs the web UI early) ----------


async def test_connect_gateway_retries_until_success():
    from somfy_rts.gateway import GatewayError
    from somfy_rts.main import connect_gateway

    gw = MagicMock()
    gw.connect.side_effect = [GatewayError("no stick"), GatewayError("no stick"), None]
    assert await connect_gateway(gw, asyncio.Event(), retry_s=0.01) is True
    assert gw.connect.call_count == 3


async def test_connect_gateway_returns_false_on_shutdown():
    from somfy_rts.gateway import GatewayError
    from somfy_rts.main import connect_gateway

    gw = MagicMock()
    gw.connect.side_effect = GatewayError("no stick")
    shutdown = asyncio.Event()
    asyncio.get_running_loop().call_later(0.05, shutdown.set)
    assert await connect_gateway(gw, shutdown, retry_s=0.01) is False


async def test_web_ui_starts_before_gateway_and_is_cleaned_up(monkeypatch):
    """Web UI must answer (Ingress, watchdog) while the stick is still missing."""
    from unittest.mock import AsyncMock

    import somfy_rts.main as main_mod
    from somfy_rts.config import Config
    from somfy_rts.gateway import GatewayError

    order: list[str] = []
    runner = MagicMock()
    runner.cleanup = AsyncMock()

    async def fake_start_server(host, port, ctx):
        order.append("web")
        return runner

    gw = MagicMock()
    gw.connect.side_effect = lambda: (order.append("gateway"), (_ for _ in ()).throw(
        GatewayError("no stick")))[1]
    monkeypatch.setattr(main_mod, "load_config", lambda: Config())
    monkeypatch.setattr(main_mod, "load_codes", lambda: {"devices": []})
    monkeypatch.setattr(main_mod, "init_rts_logger", lambda **kw: None)
    monkeypatch.setattr(main_mod, "CULGateway", lambda *a, **k: gw)
    monkeypatch.setattr(main_mod, "MQTTClient", lambda cfg: MagicMock(is_connected=False))
    monkeypatch.setattr(main_mod, "start_server", fake_start_server)

    shutdown = asyncio.Event()
    asyncio.get_running_loop().call_later(0.1, shutdown.set)
    await main_mod._async_main(shutdown_event=shutdown)

    assert order[0] == "web" and "gateway" in order
    runner.cleanup.assert_awaited_once()

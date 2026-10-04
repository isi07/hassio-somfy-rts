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

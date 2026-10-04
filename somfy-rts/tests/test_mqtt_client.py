"""Tests for mqtt_client.py — discovery_topics() and unregister_device()."""

from unittest.mock import MagicMock, patch

import pytest
from somfy_rts.config import DeviceConfig
from somfy_rts.mqtt_client import (
    HA_DISCOVERY,
    MQTT_TOPIC_PREFIX,
    MQTTClient,
    discovery_topics,
    state_topics,
)

# ---------- Fixtures ----------


@pytest.fixture
def device_a():
    """Mode-A device."""
    return DeviceConfig(name="Wohnzimmer Markise", type="awning", address="A00001", mode="A")


@pytest.fixture
def device_b():
    """Mode-B device."""
    return DeviceConfig(name="Schlafzimmer Rollladen", type="shutter", address="B00002", mode="B")


@pytest.fixture
def mqtt_client_with_mock(tmp_path):
    """MQTTClient whose internal paho client is fully mocked (no broker needed)."""
    from somfy_rts.config import Config
    cfg = Config()
    with patch("paho.mqtt.client.Client") as MockPaho:
        mock_paho = MagicMock()
        MockPaho.return_value = mock_paho
        mock_paho.is_connected.return_value = True
        client = MQTTClient(cfg)
        client._client = mock_paho  # replace with mock directly
        yield client, mock_paho


# ---------- discovery_topics() — Modus A ----------


class TestDiscoveryTopicsModeA:
    def test_contains_cover(self, device_a):
        topics = discovery_topics(device_a)
        uid = device_a.unique_id_base
        assert f"{HA_DISCOVERY}/cover/{uid}/config" in topics

    def test_contains_rolling_code_sensor(self, device_a):
        topics = discovery_topics(device_a)
        uid = device_a.unique_id_base
        assert f"{HA_DISCOVERY}/sensor/{uid}_rolling_code/config" in topics

    def test_contains_last_command_sensor(self, device_a):
        topics = discovery_topics(device_a)
        uid = device_a.unique_id_base
        assert f"{HA_DISCOVERY}/sensor/{uid}_last_command/config" in topics

    def test_contains_device_address_sensor(self, device_a):
        topics = discovery_topics(device_a)
        uid = device_a.unique_id_base
        assert f"{HA_DISCOVERY}/sensor/{uid}_device_address/config" in topics

    def test_contains_prog_long_button(self, device_a):
        topics = discovery_topics(device_a)
        uid = device_a.unique_id_base
        assert f"{HA_DISCOVERY}/button/{uid}_prog_long/config" in topics

    def test_contains_prog_pair_button(self, device_a):
        topics = discovery_topics(device_a)
        uid = device_a.unique_id_base
        assert f"{HA_DISCOVERY}/button/{uid}_prog_pair/config" in topics

    def test_contains_my_button(self, device_a):
        topics = discovery_topics(device_a)
        uid = device_a.unique_id_base
        assert f"{HA_DISCOVERY}/button/{uid}_my/config" in topics

    def test_total_count(self, device_a):
        """Mode A awning (no has_tilt) has exactly 7 discovery topics."""
        assert len(discovery_topics(device_a)) == 7

    def test_no_mode_b_buttons(self, device_a):
        """Mode A must not include auf/zu/stop button topics."""
        topics = discovery_topics(device_a)
        uid = device_a.unique_id_base
        assert f"{HA_DISCOVERY}/button/{uid}_auf/config" not in topics
        assert f"{HA_DISCOVERY}/button/{uid}_zu/config" not in topics
        assert f"{HA_DISCOVERY}/button/{uid}_stop/config" not in topics


# ---------- discovery_topics() — Modus B ----------


class TestDiscoveryTopicsModeB:
    def test_contains_auf_button(self, device_b):
        topics = discovery_topics(device_b)
        uid = device_b.unique_id_base
        assert f"{HA_DISCOVERY}/button/{uid}_auf/config" in topics

    def test_contains_zu_button(self, device_b):
        topics = discovery_topics(device_b)
        uid = device_b.unique_id_base
        assert f"{HA_DISCOVERY}/button/{uid}_zu/config" in topics

    def test_contains_stop_button(self, device_b):
        topics = discovery_topics(device_b)
        uid = device_b.unique_id_base
        assert f"{HA_DISCOVERY}/button/{uid}_stop/config" in topics

    def test_contains_rolling_code_sensor(self, device_b):
        topics = discovery_topics(device_b)
        uid = device_b.unique_id_base
        assert f"{HA_DISCOVERY}/sensor/{uid}_rolling_code/config" in topics

    def test_contains_last_command_sensor(self, device_b):
        topics = discovery_topics(device_b)
        uid = device_b.unique_id_base
        assert f"{HA_DISCOVERY}/sensor/{uid}_last_command/config" in topics

    def test_contains_prog_long_button(self, device_b):
        topics = discovery_topics(device_b)
        uid = device_b.unique_id_base
        assert f"{HA_DISCOVERY}/button/{uid}_prog_long/config" in topics

    def test_contains_prog_pair_button(self, device_b):
        topics = discovery_topics(device_b)
        uid = device_b.unique_id_base
        assert f"{HA_DISCOVERY}/button/{uid}_prog_pair/config" in topics

    def test_contains_my_button(self, device_b):
        topics = discovery_topics(device_b)
        uid = device_b.unique_id_base
        assert f"{HA_DISCOVERY}/button/{uid}_my/config" in topics

    def test_contains_device_address_sensor(self, device_b):
        """Mode B includes the device_address sensor topic."""
        topics = discovery_topics(device_b)
        uid = device_b.unique_id_base
        assert f"{HA_DISCOVERY}/sensor/{uid}_device_address/config" in topics

    def test_total_count(self, device_b):
        """Mode B shutter (no has_tilt) has exactly 9 discovery topics."""
        assert len(discovery_topics(device_b)) == 9

    def test_no_cover_topic(self, device_b):
        """Mode B must not include a cover topic."""
        topics = discovery_topics(device_b)
        uid = device_b.unique_id_base
        assert f"{HA_DISCOVERY}/cover/{uid}/config" not in topics


# ---------- unregister_device() — Modus A ----------


class TestUnregisterDeviceModeA:
    def test_publishes_empty_payload_on_all_topics(self, mqtt_client_with_mock, device_a):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_a)

        published_topics = {c.args[0] for c in mock_paho.publish.call_args_list}
        expected = set(discovery_topics(device_a))
        assert expected.issubset(published_topics)

    def test_all_payloads_are_empty_string(self, mqtt_client_with_mock, device_a):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_a)

        for c in mock_paho.publish.call_args_list:
            topic, payload = c.args[0], c.args[1]
            if topic in discovery_topics(device_a):
                assert payload == "", f"Topic {topic} had non-empty payload: {payload!r}"

    def test_all_publishes_use_retain(self, mqtt_client_with_mock, device_a):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_a)

        for c in mock_paho.publish.call_args_list:
            topic = c.args[0]
            if topic in discovery_topics(device_a):
                assert c.kwargs.get("retain") is True or c.args[2] is True, (
                    f"Topic {topic} not published with retain=True"
                )

    def test_exactly_seven_discovery_topics_cleared(self, mqtt_client_with_mock, device_a):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_a)

        cleared = [
            c for c in mock_paho.publish.call_args_list
            if c.args[0] in discovery_topics(device_a)
        ]
        assert len(cleared) == 7

    def test_state_topics_also_cleared(self, mqtt_client_with_mock, device_a):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_a)

        published_topics = {c.args[0] for c in mock_paho.publish.call_args_list}
        for topic in state_topics(device_a):
            assert topic in published_topics, f"State-Topic nicht gecleart: {topic}"

    def test_state_topics_payload_empty(self, mqtt_client_with_mock, device_a):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_a)

        for c in mock_paho.publish.call_args_list:
            if c.args[0] in state_topics(device_a):
                assert c.args[1] == "", f"State-Topic {c.args[0]} hatte nicht-leere Payload"

    def test_state_topics_retain(self, mqtt_client_with_mock, device_a):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_a)

        for c in mock_paho.publish.call_args_list:
            if c.args[0] in state_topics(device_a):
                assert c.kwargs.get("retain") is True or c.args[2] is True, (
                    f"State-Topic {c.args[0]} nicht mit retain=True publiziert"
                )


# ---------- unregister_device() — Modus B ----------


class TestUnregisterDeviceModeB:
    def test_publishes_empty_payload_on_all_discovery_topics(self, mqtt_client_with_mock, device_b):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_b)

        published_topics = {c.args[0] for c in mock_paho.publish.call_args_list}
        expected = set(discovery_topics(device_b))
        assert expected.issubset(published_topics)

    def test_exactly_nine_discovery_topics_cleared(self, mqtt_client_with_mock, device_b):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_b)

        cleared = [
            c for c in mock_paho.publish.call_args_list
            if c.args[0] in discovery_topics(device_b)
        ]
        assert len(cleared) == 9

    def test_no_cover_topic_published(self, mqtt_client_with_mock, device_b):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_b)

        uid = device_b.unique_id_base
        cover_topic = f"{HA_DISCOVERY}/cover/{uid}/config"
        published_topics = {c.args[0] for c in mock_paho.publish.call_args_list}
        assert cover_topic not in published_topics

    def test_state_topics_also_cleared(self, mqtt_client_with_mock, device_b):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_b)

        published_topics = {c.args[0] for c in mock_paho.publish.call_args_list}
        for topic in state_topics(device_b):
            assert topic in published_topics, f"State-Topic nicht gecleart: {topic}"


# ---------- state_topics() ----------


class TestStateTopics:
    def test_contains_state(self, device_a):
        slug = device_a.slug
        assert f"{MQTT_TOPIC_PREFIX}/{slug}/state" in state_topics(device_a)

    def test_contains_rolling_code(self, device_a):
        slug = device_a.slug
        assert f"{MQTT_TOPIC_PREFIX}/{slug}/rolling_code" in state_topics(device_a)

    def test_contains_last_command(self, device_a):
        slug = device_a.slug
        assert f"{MQTT_TOPIC_PREFIX}/{slug}/last_command" in state_topics(device_a)

    def test_contains_last_command_attr(self, device_a):
        slug = device_a.slug
        assert f"{MQTT_TOPIC_PREFIX}/{slug}/last_command_attr" in state_topics(device_a)

    def test_contains_device_address(self, device_a):
        slug = device_a.slug
        assert f"{MQTT_TOPIC_PREFIX}/{slug}/device_address" in state_topics(device_a)

    def test_total_count(self, device_a):
        """Genau 5 State-Topics pro Gerät (unabhängig vom Modus)."""
        assert len(state_topics(device_a)) == 5

    def test_same_count_mode_b(self, device_b):
        assert len(state_topics(device_b)) == 5

    def test_slug_derived_from_name(self, device_a):
        """Alle Topics enthalten den korrekt abgeleiteten Slug."""
        slug = device_a.slug
        for topic in state_topics(device_a):
            assert f"{MQTT_TOPIC_PREFIX}/{slug}/" in topic


class TestOnMessageSafetyNet:
    def test_handler_exception_does_not_propagate(self):
        """An exception in a command handler must not kill the paho loop thread."""
        from unittest.mock import MagicMock

        from somfy_rts.config import Config
        from somfy_rts.mqtt_client import MQTTClient

        client = MQTTClient(Config())
        client._handlers["somfy/x/set"] = MagicMock(side_effect=RuntimeError("boom"))
        msg = MagicMock()
        msg.topic = "somfy/x/set"
        msg.payload = b"OPEN"
        client._on_message(MagicMock(), None, msg)  # must not raise


# ---------- paho-mqtt Callback API v2 ----------


def _reason(packet: str, identifier: int):
    """Build a paho ReasonCode as delivered to v2 callbacks."""
    from paho.mqtt.packettypes import PacketTypes
    from paho.mqtt.reasoncodes import ReasonCode

    return ReasonCode(getattr(PacketTypes, packet), identifier=identifier)


class TestCallbackApiV2:
    def test_client_uses_callback_api_v2_without_deprecation_warning(self):
        import warnings

        from somfy_rts.config import Config

        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            client = MQTTClient(Config())
        import paho.mqtt.client as mqtt
        assert client._client._callback_api_version == mqtt.CallbackAPIVersion.VERSION2

    def test_on_connect_success_publishes_online_and_resubscribes(self, mqtt_client_with_mock):
        client, mock_paho = mqtt_client_with_mock
        client._handlers["somfy/x/set"] = MagicMock()
        client._on_connect(mock_paho, None, MagicMock(), _reason("CONNACK", 0), None)
        mock_paho.publish.assert_any_call("cul2mqtt/status", "online", retain=True)
        mock_paho.subscribe.assert_any_call("somfy/x/set")

    def test_on_connect_failure_does_not_subscribe(self, mqtt_client_with_mock, caplog):
        client, mock_paho = mqtt_client_with_mock
        client._handlers["somfy/x/set"] = MagicMock()
        client._on_connect(mock_paho, None, MagicMock(), _reason("CONNACK", 135), None)
        mock_paho.subscribe.assert_not_called()
        assert "Not authorized" in caplog.text

    def test_on_disconnect_unexpected_logs_warning(self, mqtt_client_with_mock, caplog):
        client, mock_paho = mqtt_client_with_mock
        client._on_disconnect(mock_paho, None, MagicMock(), _reason("DISCONNECT", 128), None)
        assert "MQTT-Verbindung verloren" in caplog.text

    def test_on_disconnect_normal_is_silent(self, mqtt_client_with_mock, caplog):
        client, mock_paho = mqtt_client_with_mock
        client._on_disconnect(mock_paho, None, MagicMock(), _reason("DISCONNECT", 0), None)
        assert "MQTT-Verbindung verloren" not in caplog.text


# ---------- Reconnect behaviour and logging ----------


class TestReconnect:
    def test_connect_starts_in_background_and_never_raises(self, mqtt_client_with_mock):
        """connect() must not block or raise when the broker is unreachable."""
        client, mock_paho = mqtt_client_with_mock
        mock_paho.connect.side_effect = ConnectionRefusedError("refused")
        client.connect()
        mock_paho.connect_async.assert_called_once()
        mock_paho.loop_start.assert_called_once()
        mock_paho.reconnect_delay_set.assert_called_once_with(min_delay=1, max_delay=60)
        mock_paho.connect.assert_not_called()

    def test_connect_fail_logs_warning_with_broker_and_attempt(
        self, mqtt_client_with_mock, caplog
    ):
        client, mock_paho = mqtt_client_with_mock
        client._on_connect_fail(mock_paho, None)
        client._on_connect_fail(mock_paho, None)
        assert "core-mosquitto:1883 nicht erreichbar" in caplog.text
        assert "Versuch 2" in caplog.text

    def test_reconnect_after_outage_logs_duration_and_attempts(
        self, mqtt_client_with_mock, caplog, monkeypatch
    ):
        import logging

        import somfy_rts.mqtt_client as mod

        client, mock_paho = mqtt_client_with_mock
        now = [1000.0]
        monkeypatch.setattr(mod.time, "monotonic", lambda: now[0])
        client._ever_connected = True  # outage happens during operation
        client._on_disconnect(mock_paho, None, MagicMock(), _reason("DISCONNECT", 128), None)
        now[0] += 5
        client._on_connect_fail(mock_paho, None)
        now[0] += 40
        with caplog.at_level(logging.INFO):
            client._on_connect(mock_paho, None, MagicMock(), _reason("CONNACK", 0), None)
        assert "MQTT wieder verbunden nach 45 s (1 fehlgeschlagene Versuche)" in caplog.text
        # outage state is reset — the next connect is reported as a normal connect
        caplog.clear()
        with caplog.at_level(logging.INFO):
            client._on_connect(mock_paho, None, MagicMock(), _reason("CONNACK", 0), None)
        assert "wieder verbunden" not in caplog.text

    def test_lost_connection_logs_warning(self, mqtt_client_with_mock, caplog):
        client, mock_paho = mqtt_client_with_mock
        client._on_disconnect(mock_paho, None, MagicMock(), _reason("DISCONNECT", 128), None)
        assert "MQTT-Verbindung verloren" in caplog.text

    def test_disconnect_stops_loop_after_disconnecting(self, mqtt_client_with_mock):
        client, mock_paho = mqtt_client_with_mock
        order: list[str] = []
        mock_paho.disconnect.side_effect = lambda *a, **k: order.append("disconnect")
        mock_paho.loop_stop.side_effect = lambda *a, **k: order.append("loop_stop")
        client.disconnect()
        assert order == ["disconnect", "loop_stop"]

    def test_first_connect_after_failed_attempts_is_not_called_reconnect(
        self, mqtt_client_with_mock, caplog, monkeypatch
    ):
        import logging

        import somfy_rts.mqtt_client as mod

        client, mock_paho = mqtt_client_with_mock
        now = [500.0]
        monkeypatch.setattr(mod.time, "monotonic", lambda: now[0])
        client._on_connect_fail(mock_paho, None)
        now[0] += 9
        with caplog.at_level(logging.INFO):
            client._on_connect(mock_paho, None, MagicMock(), _reason("CONNACK", 0), None)
        assert "MQTT verbunden mit core-mosquitto:1883 nach 9 s (1 fehlgeschlagene Versuche)" in caplog.text
        assert "wieder verbunden" not in caplog.text


# ---------- Republish retained state after reconnect / HA restart ----------


class TestRepublish:
    def _published(self, mock_paho) -> list[tuple[str, str]]:
        return [(c.args[0], c.args[1]) for c in mock_paho.publish.call_args_list]

    def test_reconnect_republishes_discovery_and_state(self, mqtt_client_with_mock, device_a):
        client, mock_paho = mqtt_client_with_mock
        client.register_device(device_a, MagicMock())
        client.publish_state(device_a, "open")
        before = set(self._published(mock_paho))
        mock_paho.publish.reset_mock()
        client._on_connect(mock_paho, None, MagicMock(), _reason("CONNACK", 0), None)
        after = set(self._published(mock_paho))
        assert before <= after  # every retained message is sent again

    def test_cleared_topics_are_not_republished(self, mqtt_client_with_mock, device_a):
        client, mock_paho = mqtt_client_with_mock
        client.register_device(device_a, MagicMock())
        client.unregister_device(device_a)
        mock_paho.publish.reset_mock()
        client._on_connect(mock_paho, None, MagicMock(), _reason("CONNACK", 0), None)
        republished = {t for t, _ in self._published(mock_paho)}
        assert not republished & set(discovery_topics(device_a))

    def test_lwt_is_not_cached(self, mqtt_client_with_mock):
        client, mock_paho = mqtt_client_with_mock
        client.disconnect()
        mock_paho.publish.reset_mock()
        client._on_connect(mock_paho, None, MagicMock(), _reason("CONNACK", 0), None)
        assert self._published(mock_paho) == [("cul2mqtt/status", "online")]

    def test_ha_birth_message_triggers_republish(self, mqtt_client_with_mock, device_a):
        client, mock_paho = mqtt_client_with_mock
        client.register_device(device_a, MagicMock())
        mock_paho.publish.reset_mock()
        msg = MagicMock()
        msg.topic = "homeassistant/status"
        msg.payload = b"online"
        client._on_message(mock_paho, None, msg)
        republished = {t for t, _ in self._published(mock_paho)}
        assert set(discovery_topics(device_a)) <= republished

    def test_ha_offline_message_does_not_republish(self, mqtt_client_with_mock, device_a):
        client, mock_paho = mqtt_client_with_mock
        client.register_device(device_a, MagicMock())
        mock_paho.publish.reset_mock()
        msg = MagicMock()
        msg.topic = "homeassistant/status"
        msg.payload = b"offline"
        client._on_message(mock_paho, None, msg)
        mock_paho.publish.assert_not_called()

    def test_ha_status_is_subscribed_on_connect(self, mqtt_client_with_mock):
        client, mock_paho = mqtt_client_with_mock
        client._on_connect(mock_paho, None, MagicMock(), _reason("CONNACK", 0), None)
        subscribed = {c.args[0] for c in mock_paho.subscribe.call_args_list}
        assert "homeassistant/status" in subscribed

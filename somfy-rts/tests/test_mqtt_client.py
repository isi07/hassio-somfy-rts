"""Tests for mqtt_client.py — discovery_topics() and unregister_device()."""

from unittest.mock import MagicMock, call, patch

import pytest

from somfy_rts.config import DeviceConfig
from somfy_rts.mqtt_client import HA_DISCOVERY, MQTTClient, discovery_topics


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

    def test_total_count(self, device_a):
        """Mode A has exactly 6 discovery topics."""
        assert len(discovery_topics(device_a)) == 6

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

    def test_total_count(self, device_b):
        """Mode B has exactly 7 discovery topics."""
        assert len(discovery_topics(device_b)) == 7

    def test_no_cover_topic(self, device_b):
        """Mode B must not include a cover topic."""
        topics = discovery_topics(device_b)
        uid = device_b.unique_id_base
        assert f"{HA_DISCOVERY}/cover/{uid}/config" not in topics

    def test_no_device_address_sensor(self, device_b):
        """Mode B must not include the device_address sensor topic."""
        topics = discovery_topics(device_b)
        uid = device_b.unique_id_base
        assert f"{HA_DISCOVERY}/sensor/{uid}_device_address/config" not in topics


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

    def test_exactly_six_topics_cleared(self, mqtt_client_with_mock, device_a):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_a)

        cleared = [
            c for c in mock_paho.publish.call_args_list
            if c.args[0] in discovery_topics(device_a)
        ]
        assert len(cleared) == 6


# ---------- unregister_device() — Modus B ----------


class TestUnregisterDeviceModeB:
    def test_publishes_empty_payload_on_all_topics(self, mqtt_client_with_mock, device_b):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_b)

        published_topics = {c.args[0] for c in mock_paho.publish.call_args_list}
        expected = set(discovery_topics(device_b))
        assert expected.issubset(published_topics)

    def test_exactly_seven_topics_cleared(self, mqtt_client_with_mock, device_b):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_b)

        cleared = [
            c for c in mock_paho.publish.call_args_list
            if c.args[0] in discovery_topics(device_b)
        ]
        assert len(cleared) == 7

    def test_no_cover_topic_published(self, mqtt_client_with_mock, device_b):
        client, mock_paho = mqtt_client_with_mock
        client.unregister_device(device_b)

        uid = device_b.unique_id_base
        cover_topic = f"{HA_DISCOVERY}/cover/{uid}/config"
        published_topics = {c.args[0] for c in mock_paho.publish.call_args_list}
        assert cover_topic not in published_topics

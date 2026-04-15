"""Tests for device.py — command handling and awning command mapping.

Layer-1 (HA semantics):   OPEN, CLOSE, STOP  — received by Mode A _handle_command
Layer-2 (RTS protocol):   UP,   DOWN,  MY    — received by Mode B _handle_command,
                                                sent to build_rts_sequence()
resolve_rts_action() translates Layer 1 → Layer 2 per device_profiles.json command_map.
"""

import pytest
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def isolated_codes(tmp_codes_path):  # noqa: PT004 — side-effect fixture
    """Every test gets an isolated somfy_codes.json."""


def _make_device(device_type: str, mode: str = "A", address: str = "A00001"):
    """Build a Device instance with mock gateway and mqtt client."""
    from somfy_rts.config import DeviceConfig
    from somfy_rts.device import Device

    cfg = DeviceConfig(name=f"Test {device_type}", type=device_type, address=address, mode=mode)
    gw = MagicMock()
    gw.is_connected = True
    mqtt = MagicMock()
    return Device(cfg, gw, mqtt), gw, mqtt


class TestAwningCommandMap:
    """Awning: OPEN→DOWN (Ausfahren=ctrl 0x4=0x40), CLOSE→UP (Einfahren=ctrl 0x2=0x20)."""

    def test_awning_mode_a_open_sends_rts_down(self, tmp_codes_path):
        """Mode A: HA OPEN → resolve → DOWN → Byte1=0x40 (Ausfahren)."""
        dev, gw, _ = _make_device("awning", mode="A")
        dev._handle_command("OPEN")
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        assert sent[0] == "Yr1"
        telegram = sent[1]
        assert telegram[4:6] == "40", f"Expected DOWN (0x40), got {telegram[4:6]!r}: {telegram}"

    def test_awning_mode_a_close_sends_rts_up(self, tmp_codes_path):
        """Mode A: HA CLOSE → resolve → UP → Byte1=0x20 (Einfahren)."""
        dev, gw, _ = _make_device("awning", mode="A")
        dev._handle_command("CLOSE")
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        telegram = sent[1]
        assert telegram[4:6] == "20", f"Expected UP (0x20), got {telegram[4:6]!r}: {telegram}"

    def test_awning_mode_a_stop_sends_rts_my(self, tmp_codes_path):
        """Mode A: HA STOP → resolve → MY → Byte1=0x10."""
        dev, gw, _ = _make_device("awning", mode="A")
        dev._handle_command("STOP")
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        telegram = sent[1]
        assert telegram[4:6] == "10", f"Expected MY (0x10), got {telegram[4:6]!r}: {telegram}"

    def test_awning_mode_a_open_reports_state_open(self, tmp_codes_path):
        """Mode A: HA OPEN publishes state='open' (cover is extended = open)."""
        dev, _, mqtt = _make_device("awning", mode="A")
        dev._handle_command("OPEN")
        mqtt.publish_state.assert_called_with(dev._device, "open")

    def test_awning_mode_a_close_reports_state_closed(self, tmp_codes_path):
        """Mode A: HA CLOSE publishes state='closed' (cover is retracted = closed)."""
        dev, _, mqtt = _make_device("awning", mode="A")
        dev._handle_command("CLOSE")
        mqtt.publish_state.assert_called_with(dev._device, "closed")

    def test_awning_mode_a_last_command_is_layer2_action(self, tmp_codes_path):
        """Mode A: last_command diagnostic shows Layer-2 action (DOWN), not HA command (OPEN)."""
        dev, _, mqtt = _make_device("awning", mode="A")
        dev._handle_command("OPEN")
        diagnostic_calls = {
            c.args[1]: c.args[2]
            for c in mqtt.publish_diagnostic.call_args_list
        }
        assert diagnostic_calls.get("last_command") == "DOWN"

    def test_awning_mode_b_down_sends_rts_down(self, tmp_codes_path):
        """Mode B: 'auf' button injects Layer-2 DOWN directly (no command_map applied)."""
        dev, gw, _ = _make_device("awning", mode="B")
        # Mode B: mqtt_client reads buttons["open"]["rts"] = "DOWN" → injects "DOWN"
        dev._handle_command("DOWN")
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        telegram = sent[1]
        assert telegram[4:6] == "40", f"Expected 0x40 (DOWN), got {telegram[4:6]!r}: {telegram}"

    def test_awning_mode_b_no_double_mapping(self, tmp_codes_path):
        """Mode B: command_map NOT applied — DOWN stays DOWN (not re-translated to UP)."""
        dev, gw, _ = _make_device("awning", mode="B")
        # If command_map were applied: DOWN → UP (wrong!). Must stay DOWN → 0x40.
        dev._handle_command("DOWN")
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        telegram = sent[1]
        assert telegram[4:6] == "40", (
            f"Double-mapping detected! Expected 0x40 (DOWN), got {telegram[4:6]!r}. "
            f"command_map must NOT apply in Mode B."
        )


class TestShutterCommandMap:
    """Shutter: OPEN→UP (0x20), CLOSE→DOWN (0x40), STOP→MY (0x10)."""

    def test_shutter_mode_a_open_sends_rts_up(self, tmp_codes_path):
        """Shutter: HA OPEN → UP → 0x20."""
        dev, gw, _ = _make_device("shutter", mode="A")
        dev._handle_command("OPEN")
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        telegram = sent[1]
        assert telegram[4:6] == "20"

    def test_shutter_mode_a_close_sends_rts_down(self, tmp_codes_path):
        """Shutter: HA CLOSE → DOWN → 0x40."""
        dev, gw, _ = _make_device("shutter", mode="A")
        dev._handle_command("CLOSE")
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        telegram = sent[1]
        assert telegram[4:6] == "40"

    def test_shutter_mode_a_stop_sends_rts_my(self, tmp_codes_path):
        """Shutter: HA STOP → MY → 0x10."""
        dev, gw, _ = _make_device("shutter", mode="A")
        dev._handle_command("STOP")
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        telegram = sent[1]
        assert telegram[4:6] == "10"


class TestResolveRtsAction:
    """Unit tests for the public resolve_rts_action() helper (Layer 1 → Layer 2)."""

    def test_awning_open_maps_to_down(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("OPEN", "awning") == "DOWN"

    def test_awning_close_maps_to_up(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("CLOSE", "awning") == "UP"

    def test_awning_stop_maps_to_my(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("STOP", "awning") == "MY"

    def test_awning_prog_unchanged(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("PROG", "awning") == "PROG"

    def test_shutter_open_maps_to_up(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("OPEN", "shutter") == "UP"

    def test_shutter_close_maps_to_down(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("CLOSE", "shutter") == "DOWN"

    def test_shutter_stop_maps_to_my(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("STOP", "shutter") == "MY"

    def test_layer2_down_passthrough(self):
        """Layer-2 terms (already translated) pass through unchanged."""
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("DOWN", "awning") == "DOWN"

    def test_layer2_up_passthrough(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("UP", "shutter") == "UP"

    def test_unknown_type_open_passthrough(self):
        """Unknown device type has no command_map — OPEN passes through unchanged."""
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("OPEN", "unknown_type") == "OPEN"

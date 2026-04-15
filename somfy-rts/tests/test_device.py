"""Tests for device.py — command handling and awning command mapping."""

import json
import pytest
from unittest.mock import MagicMock, call, patch


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
    """Awning inverts OPEN/CLOSE: Ausfahren (↓) = RTS CLOSE, Einfahren (↑) = RTS OPEN."""

    def test_awning_mode_a_open_sends_rts_close(self, tmp_codes_path):
        """Mode A: HA OPEN → RTS CLOSE (Ausfahren = physikalisch runter)."""
        dev, gw, _ = _make_device("awning", mode="A")
        dev._handle_command("OPEN")
        # Gateway must have received Yr1 + telegram with Byte1=40 (CLOSE ctrl=0x4)
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        assert sent[0] == "Yr1"
        telegram = sent[1]
        assert telegram[4:6] == "40", f"Expected CLOSE (0x40), got {telegram[4:6]!r}: {telegram}"

    def test_awning_mode_a_close_sends_rts_open(self, tmp_codes_path):
        """Mode A: HA CLOSE → RTS OPEN (Einfahren = physikalisch rauf)."""
        dev, gw, _ = _make_device("awning", mode="A")
        dev._handle_command("CLOSE")
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        telegram = sent[1]
        assert telegram[4:6] == "20", f"Expected OPEN (0x20), got {telegram[4:6]!r}: {telegram}"

    def test_awning_mode_a_stop_is_unchanged(self, tmp_codes_path):
        """STOP is not in command_map and passes through unchanged."""
        dev, gw, _ = _make_device("awning", mode="A")
        dev._handle_command("STOP")
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        telegram = sent[1]
        assert telegram[4:6] == "10", f"Expected STOP (0x10), got {telegram[4:6]!r}: {telegram}"

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

    def test_awning_mode_a_last_command_is_rts_action(self, tmp_codes_path):
        """Mode A: last_command diagnostic shows the actual RTS action (CLOSE), not HA command."""
        dev, _, mqtt = _make_device("awning", mode="A")
        dev._handle_command("OPEN")
        # publish_diagnostic called with "last_command" = "CLOSE" (the RTS action)
        diagnostic_calls = {
            c.args[1]: c.args[2]
            for c in mqtt.publish_diagnostic.call_args_list
        }
        assert diagnostic_calls.get("last_command") == "CLOSE"

    def test_awning_mode_b_auf_sends_rts_close(self, tmp_codes_path):
        """Mode B: 'auf' button injects RTS CLOSE directly (no double-mapping)."""
        dev, gw, _ = _make_device("awning", mode="B")
        # Mode B: mqtt_client already resolved rts field → injects RTS action directly
        dev._handle_command("CLOSE")
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        telegram = sent[1]
        # No command_map applied in Mode B — CLOSE stays CLOSE
        assert telegram[4:6] == "40", f"Expected 0x40, got {telegram[4:6]!r}: {telegram}"

    def test_awning_mode_b_no_double_mapping(self, tmp_codes_path):
        """Mode B: command_map is NOT applied — prevents double-inversion of already-translated actions."""
        dev, gw, _ = _make_device("awning", mode="B")
        # mqtt_client already inverted: 'auf' → CLOSE. If command_map applied again → OPEN (wrong!)
        dev._handle_command("CLOSE")
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        telegram = sent[1]
        assert telegram[4:6] == "40", (
            f"Double-mapping detected! Expected 0x40 (CLOSE), got {telegram[4:6]!r}. "
            f"command_map must NOT apply in Mode B."
        )


class TestShutterCommandMap:
    """Shutter has no command_map — OPEN/CLOSE pass through unchanged."""

    def test_shutter_mode_a_open_sends_rts_open(self, tmp_codes_path):
        """Shutter: HA OPEN → RTS OPEN (0x20) — no translation."""
        dev, gw, _ = _make_device("shutter", mode="A")
        dev._handle_command("OPEN")
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        telegram = sent[1]
        assert telegram[4:6] == "20"

    def test_shutter_mode_a_close_sends_rts_close(self, tmp_codes_path):
        """Shutter: HA CLOSE → RTS CLOSE (0x40) — no translation."""
        dev, gw, _ = _make_device("shutter", mode="A")
        dev._handle_command("CLOSE")
        sent = [c.args[0] for c in gw.send_raw.call_args_list]
        telegram = sent[1]
        assert telegram[4:6] == "40"


class TestResolveRtsAction:
    """Unit tests for the public resolve_rts_action() helper."""

    def test_awning_open_maps_to_close(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("OPEN", "awning") == "CLOSE"

    def test_awning_close_maps_to_open(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("CLOSE", "awning") == "OPEN"

    def test_awning_stop_unchanged(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("STOP", "awning") == "STOP"

    def test_awning_prog_unchanged(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("PROG", "awning") == "PROG"

    def test_shutter_open_unchanged(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("OPEN", "shutter") == "OPEN"

    def test_shutter_close_unchanged(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("CLOSE", "shutter") == "CLOSE"

    def test_unknown_type_passthrough(self):
        from somfy_rts.device import resolve_rts_action
        assert resolve_rts_action("OPEN", "unknown_type") == "OPEN"

"""Tests for wizard.py — PairingWizard state machine."""

import pytest


class TestAddressGeneration:
    def test_address_starts_with_prefix(self, tmp_codes_path, mock_gateway):
        from somfy_rts.wizard import PairingWizard
        wizard = PairingWizard(mock_gateway, address_prefix="B100")
        addr = wizard.start("Testgerät", "shutter")
        assert addr.startswith("B100")

    def test_address_is_six_chars(self, tmp_codes_path, mock_gateway):
        from somfy_rts.wizard import PairingWizard
        wizard = PairingWizard(mock_gateway, address_prefix="A000")
        addr = wizard.start("Testgerät", "shutter")
        assert len(addr) == 6

    def test_address_is_uppercase_hex(self, tmp_codes_path, mock_gateway):
        from somfy_rts.wizard import PairingWizard
        wizard = PairingWizard(mock_gateway, address_prefix="a000")
        addr = wizard.start("Testgerät", "shutter")
        assert addr == addr.upper()
        int(addr, 16)  # raises ValueError if not valid hex

    def test_sequential_addresses_are_unique(self, tmp_codes_path, mock_gateway):
        from somfy_rts.wizard import PairingWizard
        addr1 = PairingWizard(mock_gateway, "A000").start("Gerät 1", "shutter")
        addr2 = PairingWizard(mock_gateway, "A000").start("Gerät 2", "shutter")
        assert addr1 != addr2

    def test_prefix_locked_after_first_device(self, tmp_codes_path, mock_gateway):
        import json
        from somfy_rts.wizard import PairingWizard
        PairingWizard(mock_gateway, "A000").start("Gerät 1", "shutter")
        with open(tmp_codes_path, encoding="utf-8") as f:
            store = json.load(f)
        assert store["settings"]["prefix_locked"] is True

    def test_prefix_stored_in_settings(self, tmp_codes_path, mock_gateway):
        import json
        from somfy_rts.wizard import PairingWizard
        PairingWizard(mock_gateway, "C200").start("Gerät 1", "shutter")
        with open(tmp_codes_path, encoding="utf-8") as f:
            store = json.load(f)
        assert store["settings"]["address_prefix"] == "C200"

    def test_device_type_saved_in_codes(self, tmp_codes_path, mock_gateway):
        import json
        from somfy_rts.wizard import PairingWizard
        PairingWizard(mock_gateway, "A000").start("Markise", "awning")
        with open(tmp_codes_path, encoding="utf-8") as f:
            store = json.load(f)
        device = store["devices"][0]
        assert device["device_type"] == "awning"

    def test_device_type_default_is_shutter(self, tmp_codes_path, mock_gateway):
        import json
        from somfy_rts.wizard import PairingWizard
        PairingWizard(mock_gateway, "A000").start("Rollladen")
        with open(tmp_codes_path, encoding="utf-8") as f:
            store = json.load(f)
        device = store["devices"][0]
        assert device["device_type"] == "shutter"


class TestStateTransitions:
    def test_initial_state_is_idle(self, mock_gateway):
        from somfy_rts.wizard import PairingWizard, WizardState
        wizard = PairingWizard(mock_gateway)
        assert wizard.state == WizardState.IDLE

    def test_start_transitions_to_addr_ready(self, tmp_codes_path, mock_gateway):
        from somfy_rts.wizard import PairingWizard, WizardState
        wizard = PairingWizard(mock_gateway)
        wizard.start("Testgerät", "shutter")
        assert wizard.state == WizardState.ADDR_READY

    def test_send_prog_transitions_to_prog_sent(self, tmp_codes_path, mock_gateway):
        from somfy_rts.wizard import PairingWizard, WizardState
        wizard = PairingWizard(mock_gateway)
        wizard.start("Testgerät", "shutter")
        wizard.send_prog()
        assert wizard.state == WizardState.PROG_SENT

    def test_confirm_transitions_to_confirmed(self, tmp_codes_path, mock_gateway):
        from somfy_rts.wizard import PairingWizard, WizardState
        wizard = PairingWizard(mock_gateway)
        wizard.start("Testgerät", "shutter")
        wizard.send_prog()
        wizard.confirm()
        assert wizard.state == WizardState.CONFIRMED

    def test_send_prog_without_start_raises(self, mock_gateway):
        from somfy_rts.wizard import PairingWizard
        wizard = PairingWizard(mock_gateway)
        with pytest.raises(RuntimeError, match="ADDR_READY"):
            wizard.send_prog()

    def test_confirm_without_send_prog_raises(self, tmp_codes_path, mock_gateway):
        from somfy_rts.wizard import PairingWizard
        wizard = PairingWizard(mock_gateway)
        wizard.start("Testgerät", "shutter")
        with pytest.raises(RuntimeError, match="PROG_SENT"):
            wizard.confirm()

    def test_get_device_config_without_confirm_raises(self, tmp_codes_path, mock_gateway):
        from somfy_rts.wizard import PairingWizard
        wizard = PairingWizard(mock_gateway)
        wizard.start("Testgerät", "shutter")
        with pytest.raises(RuntimeError, match="nicht bestätigt"):
            wizard.get_device_config()


class TestDeviceConfig:
    def test_config_contains_required_keys(self, tmp_codes_path, mock_gateway):
        from somfy_rts.wizard import PairingWizard
        wizard = PairingWizard(mock_gateway)
        wizard.start("Testgerät", "awning")
        wizard.send_prog()
        wizard.confirm()
        cfg = wizard.get_device_config()
        assert cfg["name"] == "Testgerät"
        assert cfg["type"] == "awning"
        assert len(cfg["address"]) == 6
        assert cfg["mode"] == "A"

    def test_send_prog_calls_gateway(self, tmp_codes_path, mock_gateway):
        from somfy_rts.wizard import PairingWizard
        wizard = PairingWizard(mock_gateway)
        wizard.start("Testgerät", "shutter")
        wizard.send_prog()
        assert mock_gateway.send_raw.called
        # Yr1 and the telegram — at least 2 calls
        assert mock_gateway.send_raw.call_count >= 2

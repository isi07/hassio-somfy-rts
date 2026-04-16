"""Tests for rts.py — culfw telegram builder.

build_rts_sequence() only accepts Layer-2 (RTS protocol) action names:
  UP, DOWN, MY, PROG, MY_UP, MY_DOWN

Layer-1 (HA semantics) names (OPEN, CLOSE, STOP) must be translated first
via resolve_rts_action() in device.py before reaching this module.
"""

import re
import pytest


@pytest.fixture(autouse=True)
def isolated_codes(tmp_codes_path):  # noqa: PT004 — side-effect fixture
    """Every test in this module gets an isolated somfy_codes.json."""


class TestTelegramFormat:
    def test_returns_two_commands(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A1B2C3", "UP")
        assert len(seq.commands) == 2

    def test_first_command_is_yr1(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A1B2C3", "UP")
        assert seq.commands[0] == "Yr1"

    def test_telegram_starts_with_ysa0(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A1B2C3", "UP")
        assert seq.frame.startswith("YsA0")

    def test_telegram_structure(self, tmp_codes_path):
        """YsA0 + CMD(2) + RC(4) + ADDR(6) = 16 chars total."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A1B2C3", "UP")
        # YsA0 = 4, CMD = 2, RC = 4, ADDR = 6 → total 16
        assert len(seq.frame) == 16
        assert re.fullmatch(r"YsA0[0-9A-F]{12}", seq.frame), seq.frame

    def test_address_is_uppercase_in_telegram(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("a1b2c3", "UP")
        assert seq.frame.endswith("A1B2C3")

    def test_address_length_six_chars(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A1B2C3", "UP")
        assert seq.frame[-6:] == "A1B2C3"


class TestCmdBytes:
    def _cmd_from_telegram(self, telegram: str) -> str:
        """Extract CMD byte hex chars (positions 4-5 after 'YsA0').

        Per Somfy RTS protocol: Byte 1 = (ctrl << 4) | cks.
        ctrl is the command nibble in the HIGH nibble; culfw fills cks.
          UP   ctrl=0x2 → Byte 1 = 0x20
          DOWN ctrl=0x4 → Byte 1 = 0x40
          MY   ctrl=0x1 → Byte 1 = 0x10
        """
        return telegram[4:6]

    def test_up_cmd_byte_is_20(self, tmp_codes_path):
        """UP: ctrl=0x2 → Byte 1 = 0x20 (ctrl in high nibble)."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A00001", "UP")
        assert self._cmd_from_telegram(seq.frame) == "20"

    def test_down_cmd_byte_is_40(self, tmp_codes_path):
        """DOWN: ctrl=0x4 → Byte 1 = 0x40."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A00001", "DOWN")
        assert self._cmd_from_telegram(seq.frame) == "40"

    def test_my_cmd_byte_is_10(self, tmp_codes_path):
        """MY: ctrl=0x1 → Byte 1 = 0x10."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A00001", "MY")
        assert self._cmd_from_telegram(seq.frame) == "10"

    def test_prog_cmd_byte_is_80(self, tmp_codes_path):
        """PROG: ctrl=0x8 → Byte 1 = 0x80."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A00001", "PROG")
        assert self._cmd_from_telegram(seq.frame) == "80"

    def test_my_up_cmd_byte_is_30(self, tmp_codes_path):
        """MY_UP: ctrl=0x3 → Byte 1 = 0x30."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A00001", "MY_UP")
        assert self._cmd_from_telegram(seq.frame) == "30"

    def test_my_down_cmd_byte_is_50(self, tmp_codes_path):
        """MY_DOWN: ctrl=0x5 → Byte 1 = 0x50."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A00001", "MY_DOWN")
        assert self._cmd_from_telegram(seq.frame) == "50"

    def test_layer1_open_raises_value_error(self, tmp_codes_path):
        """Layer-1 name 'OPEN' is rejected — must be translated to 'UP' first."""
        from somfy_rts.rts import build_rts_sequence
        with pytest.raises(ValueError, match="Unbekannter RTS-Befehl"):
            build_rts_sequence("A00001", "OPEN")

    def test_layer1_close_raises_value_error(self, tmp_codes_path):
        """Layer-1 name 'CLOSE' is rejected — must be translated to 'DOWN' first."""
        from somfy_rts.rts import build_rts_sequence
        with pytest.raises(ValueError, match="Unbekannter RTS-Befehl"):
            build_rts_sequence("A00001", "CLOSE")

    def test_layer1_stop_raises_value_error(self, tmp_codes_path):
        """Layer-1 name 'STOP' is rejected — must be translated to 'MY' first."""
        from somfy_rts.rts import build_rts_sequence
        with pytest.raises(ValueError, match="Unbekannter RTS-Befehl"):
            build_rts_sequence("A00001", "STOP")

    def test_unknown_action_raises_value_error(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        with pytest.raises(ValueError, match="Unbekannter RTS-Befehl"):
            build_rts_sequence("A00001", "FLY")

    def test_action_is_case_insensitive(self, tmp_codes_path):
        """Lowercase 'up' maps to same byte (0x20) as uppercase 'UP'."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A00001", "up")
        assert self._cmd_from_telegram(seq.frame) == "20"


class TestRepeat:
    def test_default_repeat_is_1(self, tmp_codes_path):
        """Default repeat produces 'Yr1' as first command."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A00001", "UP")
        assert seq.commands[0] == "Yr1"
        assert seq.repeat == 1

    def test_repeat_4_produces_yr4(self, tmp_codes_path):
        """repeat=4 (PROG Anlern) produces 'Yr4' as first command."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A00001", "PROG", repeat=4)
        assert seq.commands[0] == "Yr4"
        assert seq.repeat == 4

    def test_repeat_8_produces_yr8(self, tmp_codes_path):
        """repeat=8 (PROG Lang) produces 'Yr8' as first command."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A00001", "PROG", repeat=8)
        assert seq.commands[0] == "Yr8"
        assert seq.repeat == 8

    def test_repeat_stored_in_sequence(self, tmp_codes_path):
        """RTSSequence.repeat reflects the repeat parameter."""
        from somfy_rts.rts import build_rts_sequence
        for n in (1, 4, 8):
            seq = build_rts_sequence("A00001", "PROG", repeat=n)
            assert seq.repeat == n

    def test_repeat_does_not_affect_telegram(self, tmp_codes_path):
        """repeat only changes Yr{n} — the YsA0 telegram content stays identical."""
        from somfy_rts.rts import build_rts_sequence
        seq1 = build_rts_sequence("A00001", "PROG", repeat=1)
        seq4 = build_rts_sequence("A00001", "PROG", repeat=4)
        # Both telegrams start with YsA0 and have the same CMD byte (0x80 for PROG)
        assert seq1.commands[1][4:6] == "80"
        assert seq4.commands[1][4:6] == "80"

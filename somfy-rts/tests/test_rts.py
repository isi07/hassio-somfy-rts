"""Tests for rts.py — culfw telegram builder."""

import re
import pytest


@pytest.fixture(autouse=True)
def isolated_codes(tmp_codes_path):  # noqa: PT004 — side-effect fixture
    """Every test in this module gets an isolated somfy_codes.json."""


class TestTelegramFormat:
    def test_returns_two_commands(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A1B2C3", "OPEN")
        assert len(seq.commands) == 2

    def test_first_command_is_yr1(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A1B2C3", "OPEN")
        assert seq.commands[0] == "Yr1"

    def test_telegram_starts_with_ysa0(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A1B2C3", "OPEN")
        assert seq.frame.startswith("YsA0")

    def test_telegram_structure(self, tmp_codes_path):
        """YsA0 + CMD(2) + RC(4) + ADDR(6) = 16 chars total."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A1B2C3", "OPEN")
        # YsA0 = 4, CMD = 2, RC = 4, ADDR = 6 → total 16
        assert len(seq.frame) == 16
        assert re.fullmatch(r"YsA0[0-9A-F]{12}", seq.frame), seq.frame

    def test_address_is_uppercase_in_telegram(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("a1b2c3", "OPEN")
        assert seq.frame.endswith("A1B2C3")

    def test_address_length_six_chars(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A1B2C3", "OPEN")
        assert seq.frame[-6:] == "A1B2C3"


class TestCmdBytes:
    def _cmd_from_telegram(self, telegram: str) -> str:
        """Extract CMD byte hex chars (positions 4-5 after 'YsA0').

        Per Somfy RTS protocol: Byte 1 = (ctrl << 4) | cks.
        ctrl is the command nibble in the HIGH nibble; culfw fills cks.
        So OPEN ctrl=0x2 → Byte 1 = 0x20, CLOSE ctrl=0x4 → 0x40, etc.
        """
        return telegram[4:6]

    def test_open_cmd_byte_is_20(self, tmp_codes_path):
        """OPEN: ctrl=0x2 → Byte 1 = 0x20 (ctrl in high nibble)."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A00001", "OPEN")
        assert self._cmd_from_telegram(seq.frame) == "20"

    def test_close_cmd_byte_is_40(self, tmp_codes_path):
        """CLOSE: ctrl=0x4 → Byte 1 = 0x40."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A00001", "CLOSE")
        assert self._cmd_from_telegram(seq.frame) == "40"

    def test_stop_cmd_byte_is_10(self, tmp_codes_path):
        """STOP: ctrl=0x1 → Byte 1 = 0x10."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A00001", "STOP")
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

    def test_unknown_action_raises_value_error(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        with pytest.raises(ValueError, match="Unbekannter RTS-Befehl"):
            build_rts_sequence("A00001", "FLY")

    def test_action_is_case_insensitive(self, tmp_codes_path):
        """Lowercase 'open' maps to same byte (0x20) as uppercase 'OPEN'."""
        from somfy_rts.rts import build_rts_sequence
        seq = build_rts_sequence("A00001", "open")
        assert self._cmd_from_telegram(seq.frame) == "20"

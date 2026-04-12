"""Tests for rts.py — culfw telegram builder."""

import re
import pytest


@pytest.fixture(autouse=True)
def isolated_codes(tmp_codes_path):  # noqa: PT004 — side-effect fixture
    """Every test in this module gets an isolated somfy_codes.json."""


class TestTelegramFormat:
    def test_returns_two_commands(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        result = build_rts_sequence("A1B2C3", "OPEN")
        assert len(result) == 2

    def test_first_command_is_yr1(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        result = build_rts_sequence("A1B2C3", "OPEN")
        assert result[0] == "Yr1"

    def test_telegram_starts_with_ysa0(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        _, telegram = build_rts_sequence("A1B2C3", "OPEN")
        assert telegram.startswith("YsA0")

    def test_telegram_structure(self, tmp_codes_path):
        """YsA0 + CMD(2) + RC(4) + ADDR(6) = 16 chars total."""
        from somfy_rts.rts import build_rts_sequence
        _, telegram = build_rts_sequence("A1B2C3", "OPEN")
        # YsA0 = 4, CMD = 2, RC = 4, ADDR = 6 → total 16
        assert len(telegram) == 16
        assert re.fullmatch(r"YsA0[0-9A-F]{12}", telegram), telegram

    def test_address_is_uppercase_in_telegram(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        _, telegram = build_rts_sequence("a1b2c3", "OPEN")
        assert telegram.endswith("A1B2C3")

    def test_address_length_six_chars(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        _, telegram = build_rts_sequence("A1B2C3", "OPEN")
        assert telegram[-6:] == "A1B2C3"


class TestCmdBytes:
    def _cmd_from_telegram(self, telegram: str) -> str:
        """Extract CMD hex chars (positions 4-5 after 'YsA0')."""
        return telegram[4:6]

    def test_open_cmd_is_02(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        _, t = build_rts_sequence("A00001", "OPEN")
        assert self._cmd_from_telegram(t) == "02"

    def test_close_cmd_is_04(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        _, t = build_rts_sequence("A00001", "CLOSE")
        assert self._cmd_from_telegram(t) == "04"

    def test_stop_cmd_is_01(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        _, t = build_rts_sequence("A00001", "STOP")
        assert self._cmd_from_telegram(t) == "01"

    def test_prog_cmd_is_08(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        _, t = build_rts_sequence("A00001", "PROG")
        assert self._cmd_from_telegram(t) == "08"

    def test_my_up_cmd_is_03(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        _, t = build_rts_sequence("A00001", "MY_UP")
        assert self._cmd_from_telegram(t) == "03"

    def test_my_down_cmd_is_05(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        _, t = build_rts_sequence("A00001", "MY_DOWN")
        assert self._cmd_from_telegram(t) == "05"

    def test_unknown_action_raises_value_error(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        with pytest.raises(ValueError, match="Unbekannter RTS-Befehl"):
            build_rts_sequence("A00001", "FLY")

    def test_action_is_case_insensitive(self, tmp_codes_path):
        from somfy_rts.rts import build_rts_sequence
        _, t = build_rts_sequence("A00001", "open")
        assert self._cmd_from_telegram(t) == "02"

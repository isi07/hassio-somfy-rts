"""Tests for rolling_code.py — atomic RC persistence."""

import json
import pytest


class TestIncrement:
    def test_code_increments_by_one(self, tmp_codes_path):
        from somfy_rts.rolling_code import get_and_increment
        _, rc1 = get_and_increment("A00001")
        _, rc2 = get_and_increment("A00001")
        assert rc2 == rc1 + 1

    def test_first_code_is_one(self, tmp_codes_path):
        """Fresh device starts at RC=0, first call returns (0, 1)."""
        from somfy_rts.rolling_code import get_and_increment
        old, new = get_and_increment("A00001")
        assert old == 0
        assert new == 1

    def test_different_addresses_are_independent(self, tmp_codes_path):
        from somfy_rts.rolling_code import get_and_increment
        get_and_increment("A00001")
        get_and_increment("A00001")
        _, rc_b = get_and_increment("B00001")
        assert rc_b == 1  # B00001 starts fresh


class TestAtomicPersistence:
    def test_file_exists_after_increment(self, tmp_codes_path):
        import os
        from somfy_rts.rolling_code import get_and_increment
        get_and_increment("A00001")
        assert os.path.exists(tmp_codes_path)

    def test_file_contains_valid_json(self, tmp_codes_path):
        from somfy_rts.rolling_code import get_and_increment
        get_and_increment("A00001")
        with open(tmp_codes_path, encoding="utf-8") as f:
            data = json.load(f)
        assert "devices" in data

    def test_code_persisted_correctly(self, tmp_codes_path):
        from somfy_rts.rolling_code import get_and_increment
        _, rc = get_and_increment("A00001")
        with open(tmp_codes_path, encoding="utf-8") as f:
            data = json.load(f)
        device = next(d for d in data["devices"] if d["address"] == "A00001")
        assert device["rolling_code"] == rc


class TestRestart:
    def test_code_survives_module_reload(self, tmp_codes_path):
        """Simulates app restart: load RC from file, increment again."""
        from somfy_rts.rolling_code import get_and_increment, get_current
        _, rc_before = get_and_increment("A00001")
        # get_current reads from file — simulates a fresh module load
        rc_persisted = get_current("A00001")
        assert rc_persisted == rc_before

    def test_increment_continues_from_persisted_value(self, tmp_codes_path):
        from somfy_rts.rolling_code import get_and_increment
        # Simulate several commands sent before "restart"
        for _ in range(5):
            get_and_increment("A00001")
        # Next call must continue from 5, not restart from 0
        _, rc = get_and_increment("A00001")
        assert rc == 6


class TestOverflow:
    def test_rollover_at_0xffff(self, tmp_codes_path):
        """RC 0xFFFF + 1 must wrap to 0x0000."""
        import somfy_rts.rolling_code as rc_module
        from somfy_rts.rolling_code import _find_or_create_device, _load, _save_atomic

        # Pre-seed the device at max code
        store = _load()
        entry = _find_or_create_device(store, "A00001", "test")
        entry["rolling_code"] = 0xFFFF
        _save_atomic(store)

        _, result = rc_module.get_and_increment("A00001")
        assert result == 0x0000

    def test_second_call_after_rollover_is_one(self, tmp_codes_path):
        import somfy_rts.rolling_code as rc_module
        from somfy_rts.rolling_code import _find_or_create_device, _load, _save_atomic

        store = _load()
        entry = _find_or_create_device(store, "A00001", "test")
        entry["rolling_code"] = 0xFFFF
        _save_atomic(store)

        rc_module.get_and_increment("A00001")  # → (0xFFFF, 0)
        _, result = rc_module.get_and_increment("A00001")  # → (0, 1)
        assert result == 1

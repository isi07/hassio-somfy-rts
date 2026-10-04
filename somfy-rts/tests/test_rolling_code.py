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


class TestSaveFailure:
    """(a) A failed write must abort — never return a code that was not persisted."""

    def test_write_error_raises(self, tmp_codes_path, monkeypatch):
        import os

        import somfy_rts.rolling_code as rc

        def _fail(src: str, dst: str) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", _fail)
        with pytest.raises(rc.RollingCodeStoreError):
            rc.get_and_increment("A00001")

    def test_write_error_leaves_no_tmp_file(self, tmp_codes_path, monkeypatch):
        import os

        import somfy_rts.rolling_code as rc

        monkeypatch.setattr(os, "replace", lambda s, d: (_ for _ in ()).throw(OSError("x")))
        with pytest.raises(rc.RollingCodeStoreError):
            rc.get_and_increment("A00001")
        leftovers = [p for p in os.listdir(os.path.dirname(tmp_codes_path))
                     if p.endswith(".tmp")]
        assert leftovers == []

    def test_previous_code_kept_after_write_error(self, tmp_codes_path, monkeypatch):
        import os

        import somfy_rts.rolling_code as rc

        rc.get_and_increment("A00001")  # RC=1 persisted
        real_replace = os.replace
        monkeypatch.setattr(os, "replace", lambda s, d: (_ for _ in ()).throw(OSError("x")))
        with pytest.raises(rc.RollingCodeStoreError):
            rc.get_and_increment("A00001")
        monkeypatch.setattr(os, "replace", real_replace)
        assert rc.get_current("A00001") == 1

    def test_fsync_called_before_replace(self, tmp_codes_path, monkeypatch):
        import os

        import somfy_rts.rolling_code as rc

        calls: list[str] = []
        real_fsync, real_replace = os.fsync, os.replace
        monkeypatch.setattr(os, "fsync", lambda fd: (calls.append("fsync"), real_fsync(fd))[1])
        monkeypatch.setattr(
            os, "replace", lambda s, d: (calls.append("replace"), real_replace(s, d))[1]
        )
        rc.get_and_increment("A00001")
        assert calls.index("fsync") < calls.index("replace")


class TestCorruptStore:
    """(c) A corrupt file must never be silently replaced by an empty store."""

    def _write(self, path: str, text: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_missing_file_still_initialises(self, tmp_codes_path):
        from somfy_rts.rolling_code import get_and_increment
        assert get_and_increment("A00001") == (0, 1)

    @pytest.mark.parametrize("content", ["{not json", "", "[]", '{"devices": 5}'])
    def test_corrupt_file_raises_and_is_not_overwritten(self, tmp_codes_path, content):
        import somfy_rts.rolling_code as rc

        self._write(tmp_codes_path, content)
        with pytest.raises(rc.RollingCodeStoreError):
            rc.get_and_increment("A00001")
        with open(tmp_codes_path, encoding="utf-8") as f:
            assert f.read() == content

    def test_corrupt_file_backed_up_once(self, tmp_codes_path):
        import glob

        import somfy_rts.rolling_code as rc

        self._write(tmp_codes_path, "{broken")
        for _ in range(3):
            with pytest.raises(rc.RollingCodeStoreError):
                rc._load()
        backups = glob.glob(tmp_codes_path + ".corrupt-*")
        assert len(backups) == 1
        with open(backups[0], encoding="utf-8") as f:
            assert f.read() == "{broken"

    def test_recovers_after_manual_repair(self, tmp_codes_path):
        import somfy_rts.rolling_code as rc

        self._write(tmp_codes_path, "{broken")
        with pytest.raises(rc.RollingCodeStoreError):
            rc._load()
        self._write(
            tmp_codes_path,
            json.dumps({"devices": [{"address": "A00001", "rolling_code": 41}]}),
        )
        assert rc.get_and_increment("A00001") == (41, 42)

    def test_store_error_is_oserror(self):
        from somfy_rts.rolling_code import RollingCodeStoreError
        assert issubclass(RollingCodeStoreError, OSError)


class TestThreadSafety:
    """(d) Concurrent increments from several threads must not lose updates."""

    def test_parallel_increments_are_unique(self, tmp_codes_path):
        import threading

        from somfy_rts.rolling_code import get_and_increment, get_current

        results: list[int] = []
        results_lock = threading.Lock()

        def worker() -> None:
            for _ in range(20):
                _, new = get_and_increment("A00001")
                with results_lock:
                    results.append(new)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sorted(results) == list(range(1, 81))
        assert get_current("A00001") == 80

    def test_store_lock_is_reentrant(self, tmp_codes_path):
        from somfy_rts.rolling_code import get_and_increment, store_lock

        with store_lock():
            assert get_and_increment("A00001") == (0, 1)


class TestAddressPrefix:
    def test_set_prefix_without_settings_block(self, tmp_codes_path):
        """Older files without a settings block must not raise KeyError."""
        from somfy_rts.rolling_code import get_settings, set_address_prefix

        with open(tmp_codes_path, "w", encoding="utf-8") as f:
            json.dump({"devices": []}, f)
        set_address_prefix("b100")
        assert get_settings() == {"address_prefix": "B100", "prefix_locked": True}

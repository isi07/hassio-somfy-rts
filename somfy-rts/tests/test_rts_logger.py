"""Tests for rts_logger.py — structured RTS frame logging."""

import io
import json
import logging
import os
import sys
import tempfile

import pytest


@pytest.fixture(autouse=True)
def reset_rts_logger():
    """Reset the module-level singleton and logger handlers between tests."""
    import somfy_rts.rts_logger as rts_logger_mod
    rts_logger_mod.rts_logger = None
    # Remove all handlers from the frames logger to avoid cross-test leakage
    frames_logger = logging.getLogger("somfy_rts.frames")
    frames_logger.handlers.clear()
    yield
    rts_logger_mod.rts_logger = None
    frames_logger.handlers.clear()


class TestTextFormat:
    def test_log_frame_writes_to_stdout(self, capsys):
        from somfy_rts.rts_logger import RTSLogger
        logger = RTSLogger(log_format="text")
        logger.log_frame(
            device_id="A00001",
            cmd="OPEN",
            rc_before=0,
            rc_after=1,
            frame="YsA002001AA00001",
            serial_bytes="59734130303230303141413030303031",
            success=True,
        )
        captured = capsys.readouterr()
        assert "CMD=OPEN" in captured.out
        assert "DEV=A00001" in captured.out
        assert "RC_PRE=0" in captured.out
        assert "RC_POST=1" in captured.out
        assert "FRAME=YsA002001AA00001" in captured.out
        assert "STATUS=OK" in captured.out

    def test_log_frame_error_status(self, capsys):
        from somfy_rts.rts_logger import RTSLogger
        logger = RTSLogger(log_format="text")
        logger.log_frame(
            device_id="A00001",
            cmd="CLOSE",
            rc_before=5,
            rc_after=6,
            frame="YsA004001AA00001",
            serial_bytes="",
            success=False,
            error="serial timeout",
        )
        captured = capsys.readouterr()
        assert "STATUS=ERR" in captured.out
        assert "ERR=serial timeout" in captured.out

    def test_log_rc_persist_text(self, capsys):
        from somfy_rts.rts_logger import RTSLogger
        logger = RTSLogger(log_format="text")
        logger.log_rc_persist("A00001", 42, "/data/somfy_codes.json")
        captured = capsys.readouterr()
        assert "RC_PERSIST" in captured.out
        assert "DEV=A00001" in captured.out
        assert "RC=002A" in captured.out

    def test_log_connect_text(self, capsys):
        from somfy_rts.rts_logger import RTSLogger
        logger = RTSLogger(log_format="text")
        logger.log_connect("/dev/ttyACM0", 9600)
        captured = capsys.readouterr()
        assert "GATEWAY_CONNECT" in captured.out
        assert "PORT=/dev/ttyACM0" in captured.out

    def test_log_disconnect_text(self, capsys):
        from somfy_rts.rts_logger import RTSLogger
        logger = RTSLogger(log_format="text")
        logger.log_disconnect("/dev/ttyACM0", reason="SIGTERM")
        captured = capsys.readouterr()
        assert "GATEWAY_DISCONNECT" in captured.out
        assert "REASON=SIGTERM" in captured.out


class TestJsonFormat:
    def _parse_json_output(self, capsys) -> dict:
        captured = capsys.readouterr()
        return json.loads(captured.out.strip())

    def test_log_frame_valid_json(self, capsys):
        from somfy_rts.rts_logger import RTSLogger
        logger = RTSLogger(log_format="json")
        logger.log_frame(
            device_id="A00001",
            cmd="OPEN",
            rc_before=10,
            rc_after=11,
            frame="YsA00200000AA00001",
            serial_bytes="abc",
            success=True,
        )
        data = self._parse_json_output(capsys)
        assert data["device_id"] == "A00001"
        assert data["command"] == "OPEN"
        assert data["rolling_code_before"] == 10
        assert data["rolling_code_after"] == 11
        assert data["frame_raw"] == "YsA00200000AA00001"
        assert data["status"] == "OK"
        assert data["level"] == "INFO"
        assert "timestamp" in data

    def test_log_frame_error_status_json(self, capsys):
        from somfy_rts.rts_logger import RTSLogger
        logger = RTSLogger(log_format="json")
        logger.log_frame(
            device_id="B00002",
            cmd="STOP",
            rc_before=3,
            rc_after=4,
            frame="YsA001",
            serial_bytes="",
            success=False,
            error="port not found",
        )
        data = self._parse_json_output(capsys)
        assert data["status"] == "ERR"
        assert data["level"] == "ERROR"
        assert data["error"] == "port not found"

    def test_log_rc_persist_json(self, capsys):
        from somfy_rts.rts_logger import RTSLogger
        logger = RTSLogger(log_format="json")
        logger.log_rc_persist("A00001", 99, "/data/somfy_codes.json")
        data = self._parse_json_output(capsys)
        assert data["event"] == "RC_PERSIST"
        assert data["device_id"] == "A00001"
        assert data["rolling_code"] == 99
        assert data["path"] == "/data/somfy_codes.json"

    def test_log_connect_json(self, capsys):
        from somfy_rts.rts_logger import RTSLogger
        logger = RTSLogger(log_format="json")
        logger.log_connect("sim://localhost", 0)
        data = self._parse_json_output(capsys)
        assert data["event"] == "GATEWAY_CONNECT"
        assert data["port"] == "sim://localhost"
        assert data["baudrate"] == 0

    def test_log_disconnect_json(self, capsys):
        from somfy_rts.rts_logger import RTSLogger
        logger = RTSLogger(log_format="json")
        logger.log_disconnect("/dev/ttyACM0")
        data = self._parse_json_output(capsys)
        assert data["event"] == "GATEWAY_DISCONNECT"
        assert data["port"] == "/dev/ttyACM0"


class TestFileLogging:
    def test_file_created_when_enabled(self, tmp_path, monkeypatch):
        log_file = tmp_path / "rts_frames.log"
        monkeypatch.setattr("somfy_rts.rts_logger._LOG_FILE", str(log_file))
        from somfy_rts.rts_logger import RTSLogger
        logger = RTSLogger(log_format="text", file_logging=True)
        logger.log_frame(
            device_id="A00001",
            cmd="OPEN",
            rc_before=0,
            rc_after=1,
            frame="YsA002",
            serial_bytes="",
            success=True,
        )
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "CMD=OPEN" in content

    def test_no_file_when_disabled(self, tmp_path, monkeypatch):
        log_file = tmp_path / "rts_frames.log"
        monkeypatch.setattr("somfy_rts.rts_logger._LOG_FILE", str(log_file))
        from somfy_rts.rts_logger import RTSLogger
        RTSLogger(log_format="text", file_logging=False)
        assert not log_file.exists()


class TestSingleton:
    def test_init_sets_singleton(self):
        import somfy_rts.rts_logger as mod
        from somfy_rts.rts_logger import init
        assert mod.rts_logger is None
        init(log_format="text")
        assert mod.rts_logger is not None

    def test_init_returns_instance(self):
        from somfy_rts.rts_logger import RTSLogger, init
        instance = init(log_format="json")
        assert isinstance(instance, RTSLogger)

    def test_propagate_false(self):
        from somfy_rts.rts_logger import RTSLogger
        logger = RTSLogger()
        frames_logger = logging.getLogger("somfy_rts.frames")
        assert frames_logger.propagate is False

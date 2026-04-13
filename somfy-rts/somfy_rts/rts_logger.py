"""Structured RTS frame logger — records every culfw transmission.

Provides two output formats:
  text: human-readable single-line log (matches existing log style)
  json: machine-readable JSON per frame (for log aggregators / debugging)

Optional file logging writes to /share/somfy_rts/rts_frames.log
(RotatingFileHandler, 5 MB, 3 backups).

Usage:
    from .rts_logger import init as init_rts_logger, rts_logger
    init_rts_logger(log_format="json", file_logging=True)
    # rts_logger is now available as module-level singleton
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from typing import Optional

_LOG_FILE = "/share/somfy_rts/rts_frames.log"
_LOG_FILE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_LOG_FILE_BACKUP_COUNT = 3

# Module-level singleton — None until init() is called
rts_logger: Optional["RTSLogger"] = None


class RTSLogger:
    """Structured logger for RTS frames and gateway lifecycle events.

    Args:
        log_format:   "text" for human-readable lines, "json" for JSON objects.
        file_logging: If True, also write to /share/somfy_rts/rts_frames.log.
    """

    def __init__(self, log_format: str = "text", file_logging: bool = False) -> None:
        self._format = log_format.lower()
        self._logger = logging.getLogger("somfy_rts.frames")
        self._logger.setLevel(logging.DEBUG)
        # Prevent double-printing when root logger also has a StreamHandler
        self._logger.propagate = False

        if not self._logger.handlers:
            stdout_handler = logging.StreamHandler(sys.stdout)
            stdout_handler.setLevel(logging.DEBUG)
            stdout_handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(stdout_handler)

        if file_logging:
            try:
                file_handler = logging.handlers.RotatingFileHandler(
                    _LOG_FILE,
                    maxBytes=_LOG_FILE_MAX_BYTES,
                    backupCount=_LOG_FILE_BACKUP_COUNT,
                    encoding="utf-8",
                )
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(logging.Formatter("%(message)s"))
                self._logger.addHandler(file_handler)
            except OSError as e:
                logging.getLogger(__name__).warning(
                    "RTS frame log file unavailable: %s", e
                )

    # ---------- Public logging methods ----------

    def log_frame(
        self,
        device_id: str,
        cmd: str,
        rc_before: int,
        rc_after: int,
        frame: str,
        serial_bytes: str,
        success: bool,
        error: str = "",
    ) -> None:
        """Log a single RTS frame transmission.

        Args:
            device_id:    6-char hex device address (e.g. "A00001").
            cmd:          Action string (e.g. "OPEN", "CLOSE", "PROG").
            rc_before:    Rolling code value before increment.
            rc_after:     Rolling code value after increment (used in frame).
            frame:        Raw culfw telegram string (e.g. "YsA002001AA1B2C3").
            serial_bytes: Hex representation of bytes sent over serial.
            success:      True if transmission succeeded without exception.
            error:        Error message if success is False.
        """
        ts = _iso_now()
        status = "OK" if success else "ERR"

        if self._format == "json":
            payload = json.dumps(
                {
                    "timestamp": ts,
                    "level": "INFO" if success else "ERROR",
                    "device_id": device_id.upper(),
                    "command": cmd.upper(),
                    "rolling_code_before": rc_before,
                    "rolling_code_after": rc_after,
                    "frame_raw": frame,
                    "serial_bytes": serial_bytes,
                    "status": status,
                    "error": error,
                },
                ensure_ascii=False,
            )
        else:
            payload = (
                f"{ts} [INFO] [somfy_rts] "
                f"CMD={cmd.upper():<8} DEV={device_id.upper()} "
                f"RC_PRE={rc_before:04X} RC_POST={rc_after:04X} "
                f"FRAME={frame} STATUS={status}"
            )
            if error:
                payload += f" ERR={error}"

        self._logger.info(payload)

    def log_rc_persist(self, device_id: str, rc_value: int, path: str) -> None:
        """Log an atomic rolling code persistence event.

        Args:
            device_id: 6-char hex device address.
            rc_value:  Rolling code value that was saved.
            path:      File path where the code was persisted.
        """
        ts = _iso_now()

        if self._format == "json":
            payload = json.dumps(
                {
                    "timestamp": ts,
                    "level": "DEBUG",
                    "event": "RC_PERSIST",
                    "device_id": device_id.upper(),
                    "rolling_code": rc_value,
                    "path": path,
                },
                ensure_ascii=False,
            )
        else:
            payload = (
                f"{ts} [DEBUG] [somfy_rts] "
                f"RC_PERSIST DEV={device_id.upper()} RC={rc_value:04X} PATH={path}"
            )

        self._logger.debug(payload)

    def log_connect(self, port: str, baudrate: int) -> None:
        """Log a successful gateway connection.

        Args:
            port:     Serial port or connection identifier.
            baudrate: Baud rate used for the connection.
        """
        ts = _iso_now()

        if self._format == "json":
            payload = json.dumps(
                {
                    "timestamp": ts,
                    "level": "INFO",
                    "event": "GATEWAY_CONNECT",
                    "port": port,
                    "baudrate": baudrate,
                },
                ensure_ascii=False,
            )
        else:
            payload = (
                f"{ts} [INFO] [somfy_rts] "
                f"GATEWAY_CONNECT PORT={port} BAUD={baudrate}"
            )

        self._logger.info(payload)

    def log_disconnect(self, port: str, reason: str = "") -> None:
        """Log a gateway disconnection.

        Args:
            port:   Serial port or connection identifier.
            reason: Optional reason string (e.g. "SIGTERM", error message).
        """
        ts = _iso_now()

        if self._format == "json":
            payload = json.dumps(
                {
                    "timestamp": ts,
                    "level": "INFO",
                    "event": "GATEWAY_DISCONNECT",
                    "port": port,
                    "reason": reason,
                },
                ensure_ascii=False,
            )
        else:
            payload = f"{ts} [INFO] [somfy_rts] GATEWAY_DISCONNECT PORT={port}"
            if reason:
                payload += f" REASON={reason}"

        self._logger.info(payload)


# ---------- Module-level init ----------

def init(log_format: str = "text", file_logging: bool = False) -> "RTSLogger":
    """Initialize the module-level rts_logger singleton.

    Args:
        log_format:   "text" or "json".
        file_logging: If True, also log to /share/somfy_rts/rts_frames.log.

    Returns:
        The initialized RTSLogger instance.
    """
    global rts_logger  # noqa: PLW0603
    rts_logger = RTSLogger(log_format=log_format, file_logging=file_logging)
    return rts_logger


# ---------- Internal helpers ----------

def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

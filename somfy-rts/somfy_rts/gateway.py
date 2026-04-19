"""Gateway-Abstraktion: BaseGateway (ABC) und CULGateway (NanoCUL/culfw).

Erweiterbar für zukünftige Gateways (z.B. SIGNALduino) durch Ableitung von BaseGateway.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional

import serial

logger = logging.getLogger(__name__)

CMD_VERSION = b"V\n"


class GatewayError(Exception):
    """Wird bei Verbindungs- oder Übertragungsfehlern des Gateways geworfen."""


class BaseGateway(ABC):
    """Abstrakte Basisklasse für alle Somfy RTS Gateways."""

    @abstractmethod
    def connect(self) -> None:
        """Verbindung zum Gateway herstellen."""

    @abstractmethod
    def disconnect(self) -> None:
        """Verbindung trennen."""

    @abstractmethod
    def send_raw(self, command: str) -> None:
        """Einen rohen Befehl senden (ohne Zeilenumbruch)."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True wenn das Gateway verbunden und betriebsbereit ist."""

    @property
    @abstractmethod
    def port_name(self) -> str:
        """Bezeichner des Ports/Kanals (z.B. '/dev/ttyUSB0')."""


class CULGateway(BaseGateway):
    """NanoCUL Gateway über pyserial (culfw-Firmware, 433,42 MHz).

    Kommunikationsprotokoll: ASCII-Befehle, Newline-terminiert.
    Frequenz 433,42 MHz wird durch culfw-Firmware und Hardware sichergestellt —
    wir senden nur Roh-Strings, culfw übernimmt Checksumme und Verschlüsselung.
    """

    def __init__(self, port: str, baud_rate: int = 9600) -> None:
        self._port = port
        self._baud_rate = baud_rate
        self._serial: Optional[serial.Serial] = None

    def connect(self) -> None:
        """Öffnet die serielle Verbindung und verifiziert culfw-Firmware."""
        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2.0,
            )
            time.sleep(0.5)  # Wait for culfw to initialize
            self._flush()
            version = self._query_version()
            # Enable Somfy RTS mode in culfw
            self._serial.write(b"X21\n")
            self._serial.flush()
            time.sleep(0.5)  # Wait until CUL is ready to receive RTS commands
            logger.info("NanoCUL verbunden auf %s — %s (RTS Modus aktiv)", self._port, version)
            from .rts_logger import rts_logger  # noqa: PLC0415
            if rts_logger is not None:
                rts_logger.log_connect(self._port, self._baud_rate)
        except serial.SerialException as e:
            raise GatewayError(f"Kann {self._port} nicht öffnen: {e}") from e

    def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("NanoCUL getrennt.")
            from .rts_logger import rts_logger  # noqa: PLC0415
            if rts_logger is not None:
                rts_logger.log_disconnect(self._port)

    def send_raw(self, command: str) -> None:
        """Sendet einen culfw-Befehl (fügt Newline an).

        Bei I/O-Fehler wird einmalig ein Reconnect versucht. Die Original-Exception
        wird danach trotzdem weitergeworfen — STATUS=ERR bleibt im Frame-Log erhalten.
        """
        if not self._serial or not self._serial.is_open:
            raise GatewayError("CUL nicht verbunden.")
        raw = (command + "\n").encode("ascii")
        logger.info("CUL TX: %s", command)
        try:
            self._serial.write(raw)
            self._serial.flush()
        except (OSError, serial.SerialException) as exc:
            logger.warning("CUL: I/O Fehler — versuche Reconnect... (%s)", exc)
            try:
                self._serial.close()
            except Exception:
                pass
            time.sleep(2)
            try:
                self.connect()
                logger.info("CUL: Reconnect erfolgreich.")
            except GatewayError as reconnect_exc:
                logger.error("CUL: Reconnect fehlgeschlagen: %s", reconnect_exc)
            raise GatewayError(f"I/O Fehler beim Senden: {exc}") from exc

    @property
    def is_connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    @property
    def port_name(self) -> str:
        return self._port

    def _query_version(self) -> str:
        self._serial.write(CMD_VERSION)
        self._serial.flush()
        return (
            self._serial.readline().decode("ascii", errors="replace").strip()
            or "unbekannte Version"
        )

    def _flush(self) -> None:
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()


class SimGateway(BaseGateway):
    """Hardware-free simulation gateway for testing and development.

    Records all sent commands in memory. Does not require a NanoCUL device.
    Useful for CI, unit tests, and dry-run scenarios.
    """

    def __init__(self, port: str = "sim://localhost") -> None:
        self._port = port
        self._connected = False
        self.sent_commands: list[str] = []

    def connect(self) -> None:
        """Simulate a gateway connection."""
        self._connected = True
        logger.info("[SIM] Gateway verbunden auf %s", self._port)
        from .rts_logger import rts_logger  # noqa: PLC0415
        if rts_logger is not None:
            rts_logger.log_connect(self._port, 0)

    def disconnect(self) -> None:
        """Simulate a gateway disconnection."""
        if self._connected:
            self._connected = False
            logger.info("[SIM] Gateway getrennt.")
            from .rts_logger import rts_logger  # noqa: PLC0415
            if rts_logger is not None:
                rts_logger.log_disconnect(self._port)

    def send_raw(self, command: str) -> None:
        """Record a command without transmitting over serial.

        Args:
            command: culfw command string (without newline).
        """
        if not self._connected:
            raise GatewayError("SimGateway nicht verbunden.")
        self.sent_commands.append(command)
        logger.info("[SIM] TX: %s", command)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def port_name(self) -> str:
        return self._port

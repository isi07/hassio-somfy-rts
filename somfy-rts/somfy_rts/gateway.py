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

    def __init__(self, port: str, baud_rate: int = 9600):
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
        except serial.SerialException as e:
            raise GatewayError(f"Kann {self._port} nicht öffnen: {e}") from e

    def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("NanoCUL getrennt.")

    def send_raw(self, command: str) -> None:
        """Sendet einen culfw-Befehl (fügt Newline an)."""
        if not self._serial or not self._serial.is_open:
            raise GatewayError("CUL nicht verbunden.")
        raw = (command + "\n").encode("ascii")
        logger.debug("CUL TX: %r", raw)
        self._serial.write(raw)
        self._serial.flush()

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

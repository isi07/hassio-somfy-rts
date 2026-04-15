"""RTS-Protokoll: baut culfw-Befehlssequenz für Somfy RTS Telegramme.

culfw Befehlsformat (433,42 MHz):
  1. Yr1                          → Wiederholungen auf 1 setzen
  2. YsA0<CMD><RC><ADDR>          → RTS Telegramm senden

  Felder:
    A0    = festes culfw-Präfix (Timing/Flags)
    CMD   = 1 Byte Hex (2 Zeichen), z.B. "02" für Auf
    RC    = Rolling Code, 4 Hex-Zeichen (16-Bit Big-Endian)
    ADDR  = Geräteadresse, 6 Hex-Zeichen (3 Byte)

  Checksumme und Verschlüsselung übernimmt culfw intern.

WICHTIG: repeat=1 (Yr1) ist PFLICHT für Centralis uno RTS —
         der Motor ignoriert Telegramme mit repeat>1.

WICHTIG: Rolling Code wird ATOMAR persistiert BEVOR build_rts_sequence()
         zurückkehrt. Erst dann sendet der Aufrufer die Befehle.
"""

import logging
from dataclasses import dataclass

from .rolling_code import get_and_increment

logger = logging.getLogger(__name__)


@dataclass
class RTSSequence:
    """Result of build_rts_sequence() — culfw commands plus metadata for frame logging."""

    commands: list[str]  # ["Yr1", "YsA0..."]
    frame: str           # telegram string = commands[1]
    rc_before: int       # rolling code before increment
    rc_after: int        # rolling code after increment (value encoded in frame)


def log_rts_frame(
    seq: RTSSequence,
    device_id: str,
    action: str,
    success: bool,
    error: str = "",
) -> None:
    """Call rts_logger.log_frame() after the send_raw() loop completes.

    Args:
        seq:       RTSSequence returned by build_rts_sequence().
        device_id: 6-char hex device address (e.g. "A1B2C3").
        action:    Command string (e.g. "OPEN", "CLOSE").
        success:   True if all send_raw() calls succeeded without exception.
        error:     Exception message when success is False.
    """
    from .rts_logger import rts_logger  # noqa: PLC0415
    if rts_logger is not None:
        rts_logger.log_frame(
            device_id=device_id.upper(),
            cmd=action.upper(),
            rc_before=seq.rc_before,
            rc_after=seq.rc_after,
            frame=seq.frame,
            serial_bytes=(seq.frame + "\n").encode("ascii").hex(),
            success=success,
            error=error,
        )

# CMD-Bytes: 1 Byte = 2 Hex-Zeichen im Befehlsstring
RTS_CMD: dict[str, int] = {
    "OPEN":     0x2,  # Auf / Hoch
    "CLOSE":    0x4,  # Ab / Runter
    "STOP":     0x1,  # My / Stop
    "PROG":     0x8,  # Programmiermodus (Anlern-Wizard)
    "MY_UP":    0x3,  # My + Auf
    "MY_DOWN":  0x5,  # My + Ab
}


def build_rts_sequence(address: str, action: str, device_name: str = "") -> RTSSequence:
    """Baut die culfw-Befehlssequenz für ein einzelnes RTS-Telegramm.

    Rolling Code wird ATOMAR in /data/somfy_codes.json gespeichert,
    bevor diese Funktion zurückkehrt. Der Aufrufer sendet die Befehle
    sofort danach über das Gateway und ruft log_rts_frame() auf.

    Args:
        address:     6-stellige Hex-Adresse des virtuellen Senders (z.B. "A1B2C3")
        action:      Befehl: "OPEN", "CLOSE", "STOP", "PROG", "MY_UP", "MY_DOWN"
        device_name: Optionaler Gerätename für somfy_codes.json

    Returns:
        RTSSequence mit commands ["Yr1", "YsA0..."] und RC-Metadaten für den Frame-Logger.

    Raises:
        ValueError: Bei unbekanntem action-Wert.
    """
    cmd_byte = RTS_CMD.get(action.upper())
    if cmd_byte is None:
        raise ValueError(
            f"Unbekannter RTS-Befehl: {action!r}. Erlaubt: {list(RTS_CMD)}"
        )

    # Rolling Code inkrementieren und ATOMAR speichern (vor dem Senden!)
    rc_before, rolling_code = get_and_increment(address, device_name)

    telegram = f"YsA0{cmd_byte:02X}{rolling_code:04X}{address.upper()}"

    logger.info(
        "RTS: '%s' | Aktion=%-8s | CMD=0x%02X | RC=%5d (0x%04X) | → %s",
        device_name or address,
        action,
        cmd_byte,
        rolling_code,
        rolling_code,
        telegram,
    )

    # Yr1 MUSS vor dem Telegramm gesendet werden
    return RTSSequence(
        commands=["Yr1", telegram],
        frame=telegram,
        rc_before=rc_before,
        rc_after=rolling_code,
    )

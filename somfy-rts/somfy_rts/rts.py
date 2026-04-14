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

from .rolling_code import get_and_increment

logger = logging.getLogger(__name__)

# CMD-Bytes: 1 Byte = 2 Hex-Zeichen im Befehlsstring
RTS_CMD: dict[str, int] = {
    "OPEN":     0x2,  # Auf / Hoch
    "CLOSE":    0x4,  # Ab / Runter
    "STOP":     0x1,  # My / Stop
    "PROG":     0x8,  # Programmiermodus (Anlern-Wizard)
    "MY_UP":    0x3,  # My + Auf
    "MY_DOWN":  0x5,  # My + Ab
}


def build_rts_sequence(address: str, action: str, device_name: str = "") -> list[str]:
    """Baut die culfw-Befehlssequenz für ein einzelnes RTS-Telegramm.

    Rolling Code wird ATOMAR in /data/somfy_codes.json gespeichert,
    bevor diese Funktion zurückkehrt. Der Aufrufer sendet die Befehle
    sofort danach über das Gateway.

    Args:
        address:     6-stellige Hex-Adresse des virtuellen Senders (z.B. "A1B2C3")
        action:      Befehl: "OPEN", "CLOSE", "STOP", "PROG", "MY_UP", "MY_DOWN"
        device_name: Optionaler Gerätename für somfy_codes.json

    Returns:
        ["Yr1", "YsA0<CMD><RC><ADDR>"] — beide Strings ohne Newline senden.

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

    from .rts_logger import rts_logger  # noqa: PLC0415
    if rts_logger is not None:
        serial_bytes = (telegram + "\n").encode("ascii").hex()
        rts_logger.log_frame(
            device_id=address.upper(),
            cmd=action.upper(),
            rc_before=rc_before,
            rc_after=rolling_code,
            frame=telegram,
            serial_bytes=serial_bytes,
            success=True,
        )

    # Yr1 MUSS vor dem Telegramm gesendet werden
    return ["Yr1", telegram]

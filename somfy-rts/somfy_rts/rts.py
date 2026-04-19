"""RTS-Protokoll: baut culfw-Befehlssequenz für Somfy RTS Telegramme.

culfw Befehlsformat (433,42 MHz):
  1. Yr{n}                        → Wiederholungen setzen (Standard: 1, PROG-Anlern: 4, PROG-Lang: 14)
  2. YsA0<CMD><RC><ADDR>          → RTS Telegramm senden

  Felder:
    A0    = festes culfw-Präfix (Timing/Flags)
    CMD   = 1 Byte Hex (2 Zeichen) = Byte 1 des Somfy-Frames
            Byte 1 = (ctrl << 4) | cks
            ctrl = Befehlsnibble (High-Nibble), z.B. 0x2 für UP
            cks  = Prüfsummennibble (Low-Nibble), von culfw intern berechnet
            → culfw erwartet ctrl im High-Nibble, cks=0; z.B. "20" für UP
    RC    = Rolling Code, 4 Hex-Zeichen (16-Bit Big-Endian)
    ADDR  = Geräteadresse, 6 Hex-Zeichen (3 Byte)

  Schicht 2 (RTS-Protokoll-Befehle, Eingabe für build_rts_sequence):
    UP, DOWN, MY, PROG, MY_UP, MY_DOWN
  Schicht 1 (HA-Semantik) wird von resolve_rts_action() in Schicht 2 übersetzt:
    OPEN → UP, CLOSE → DOWN, STOP → MY  (Ausnahme awning: OPEN→DOWN, CLOSE→UP)

  Checksumme und Verschlüsselung übernimmt culfw intern.

WICHTIG: repeat=1 (Yr1) ist PFLICHT für Centralis uno RTS bei normalen Befehlen —
         der Motor ignoriert Telegramme mit repeat>1.
         Ausnahme: PROG-Befehle können repeat=4 (Anlern) oder repeat=14 (Lang/Anlernmodus)
         verwenden — diese Werte werden von culfw korrekt verarbeitet.
WARNUNG: Yr16+ kann die NanoCUL USB-Verbindung zum Absturz bringen — nicht überschreiten!

WICHTIG: Rolling Code wird ATOMAR persistiert BEVOR build_rts_sequence()
         zurückkehrt. Erst dann sendet der Aufrufer die Befehle.
"""

import logging
from dataclasses import dataclass

from .rolling_code import get_and_increment

logger = logging.getLogger(__name__)


@dataclass
class RTSSequence:
    """Result of build_rts_sequence() — culfw commands plus metadata for frame logging.

    commands[0] is f"Yr{repeat}" (e.g. "Yr1", "Yr4", "Yr14").
    commands[1] is the RTS telegram string ("YsA0...").
    """

    commands: list[str]  # [f"Yr{repeat}", "YsA0..."]
    frame: str           # telegram string = commands[1]
    rc_before: int       # rolling code before increment
    rc_after: int        # rolling code after increment (value encoded in frame)
    repeat: int = 1      # culfw repeat count (Yr{repeat})


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
            repeat=seq.repeat,
        )

# Somfy RTS ctrl-Nibble-Werte (High-Nibble von Byte 1, laut Protokoll-Spec)
# Schlüssel = Schicht-2-Begriffe (RTS-Protokoll): UP, DOWN, MY, PROG, MY_UP, MY_DOWN
RTS_CTRL_NIBBLE: dict[str, int] = {
    "UP":      0x2,  # Hochfahren / Einfahren (Rollladen hoch, Markise ein)
    "DOWN":    0x4,  # Runterfahren / Ausfahren (Rollladen runter, Markise aus)
    "MY":      0x1,  # MY / Stop
    "PROG":    0x8,  # Programmiermodus (Anlern-Wizard)
    "MY_UP":   0x3,  # MY + Hoch (Jalousie)
    "MY_DOWN": 0x5,  # MY + Runter (Jalousie)
}

# Telegram-Byte-Werte: ctrl ins High-Nibble schieben, cks=0 (culfw berechnet cks intern)
# Byte 1 = (ctrl << 4) | cks  →  UP: 0x2<<4 = 0x20, DOWN: 0x4<<4 = 0x40, MY: 0x1<<4 = 0x10, ...
RTS_CMD: dict[str, int] = {k: v << 4 for k, v in RTS_CTRL_NIBBLE.items()}


def build_rts_sequence(
    address: str,
    action: str,
    device_name: str = "",
    repeat: int = 1,
) -> RTSSequence:
    """Baut die culfw-Befehlssequenz für ein einzelnes RTS-Telegramm.

    Rolling Code wird ATOMAR in /data/somfy_codes.json gespeichert,
    bevor diese Funktion zurückkehrt. Der Aufrufer sendet die Befehle
    sofort danach über das Gateway und ruft log_rts_frame() auf.

    Args:
        address:     6-stellige Hex-Adresse des virtuellen Senders (z.B. "A1B2C3")
        action:      Schicht-2-Befehl: "UP", "DOWN", "MY", "PROG", "MY_UP", "MY_DOWN"
                     (Schicht-1-Befehle OPEN/CLOSE/STOP müssen vorher via
                     resolve_rts_action() übersetzt werden)
        device_name: Optionaler Gerätename für somfy_codes.json
        repeat:      culfw Wiederholungsanzahl für Yr{repeat}-Kommando (Standard: 1).
                     Normalbefehle: 1. PROG Anlern (Yr4): 4. PROG Lang (Yr14): 14.
                     WARNUNG: Yr16+ crasht NanoCUL — nicht überschreiten!

    Returns:
        RTSSequence mit commands [f"Yr{repeat}", "YsA0..."] und RC-Metadaten.

    Raises:
        ValueError: Bei unbekanntem action-Wert (Schicht-2-Prüfung).
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
        "RTS: '%s' | %-7s | Byte1=0x%02X (ctrl=0x%X) | RC=%d | Yr%d | %s",
        device_name or address,
        action,
        cmd_byte,
        cmd_byte >> 4,
        rolling_code,
        repeat,
        telegram,
    )

    return RTSSequence(
        commands=[f"Yr{repeat}", telegram],
        frame=telegram,
        rc_before=rc_before,
        rc_after=rolling_code,
        repeat=repeat,
    )

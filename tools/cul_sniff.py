#!/usr/bin/env python3
"""Read-only CUL serial sniffer — logs every raw line the stick reports.

Diagnostic tool for the Somfy RTS receive-side investigation. It is NOT part of
the add-on and never transmits an RTS frame (it cannot desynchronise a rolling
code). It only sends ``V`` (version) and one ``X<flags>`` report command.

Stop the Somfy RTS add-on first — the serial port can only be opened once.

Usage:
    python tools/cul_sniff.py /dev/ttyACM0
    python tools/cul_sniff.py /dev/ttyACM0 --report 25 --logfile sniff.log

Report flags (culfw ``X<RR>``, hex): bit0 known messages, bit1 every repeat,
bit2 also messages with bad parity/checksum, bit5 RSSI. The add-on uses 21.

What to do while it runs:
    1. Note the VERSION line (firmware build, e.g. a-culfw vs. culfw).
    2. Press UP / DOWN / MY on an original Somfy remote, several times, close
       to the stick → does any line appear at all? Run once with --report 21
       and once with --report 25 (also report bad-checksum data).
    3. Expected from the culfw/a-culfw sources: no Somfy line, because culfw
       has no Somfy RTS decoder; ``Ys…`` lines are only echoes of the stick's
       own transmissions, which this tool never triggers.
"""

import argparse
import logging
import sys
import time

import serial

DEFAULT_BAUDRATE = 9600
DEFAULT_REPORT_FLAGS = "21"
READ_TIMEOUT_S = 1.0
INIT_DELAY_S = 0.5

logger = logging.getLogger("cul_sniff")


def _classify(line: str) -> str:
    """Return a short label for a culfw output line.

    Args:
        line: One stripped line from the serial port.

    Returns:
        Human-readable category used in the log.
    """
    if line.startswith(("Ys", "YS")):
        return "SOMFY-FRAME/ECHO"
    if line.startswith(("Yr:", "Yt:")):
        return "SOMFY-SETTING"
    if line.startswith("V "):
        return "VERSION"
    if line.startswith("LOVF"):
        return "TX-CREDIT-EXHAUSTED"
    return "OTHER"


def main() -> int:
    """Open the port, enable reporting and log lines until Ctrl+C.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("port", help="serial port, e.g. /dev/ttyACM0")
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE)
    parser.add_argument(
        "--report", default=DEFAULT_REPORT_FLAGS,
        help="culfw X report flags as 2 hex digits (default: 21)",
    )
    parser.add_argument("--logfile", help="also append raw lines to this file")
    args = parser.parse_args()

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if args.logfile:
        handlers.append(logging.FileHandler(args.logfile, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )

    try:
        ser = serial.Serial(args.port, args.baudrate, timeout=READ_TIMEOUT_S)
    except serial.SerialException as exc:
        logger.error("Cannot open %s: %s", args.port, exc)
        return 1

    with ser:
        time.sleep(INIT_DELAY_S)
        ser.reset_input_buffer()
        ser.write(b"V\n")
        ser.write(f"X{args.report}\n".encode("ascii"))
        ser.flush()
        logger.info("Listening on %s (X%s) — Ctrl+C to stop", args.port, args.report)
        try:
            while True:
                raw = ser.readline()
                if not raw:
                    continue
                line = raw.decode("ascii", errors="replace").strip()
                logger.info("%-20s %s", _classify(line), line)
        except KeyboardInterrupt:
            logger.info("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

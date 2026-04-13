"""Atomare Rolling Code Verwaltung — persistiert in /data/somfy_codes.json.

KRITISCH: Der Rolling Code MUSS atomar gespeichert werden BEVOR der RTS-Befehl
gesendet wird. Bei Stromausfall während des Sendens ist der Code bereits sicher
persistiert und der Motor kann beim nächsten Befehl reagieren.

Atomares Schreiben via tempfile + os.replace() (POSIX-garantiert atomar).
"""

import copy
import json
import logging
import os
import tempfile
from typing import Any, Dict

logger = logging.getLogger(__name__)

CODES_PATH = os.environ.get("SOMFY_CODES_PATH", "/data/somfy_codes.json")

_EMPTY_STORE: Dict[str, Any] = {
    "devices": [],
    "groups": [],
    "settings": {
        "address_prefix": "A000",
        "prefix_locked": False,
    },
}


# ---------- interne Hilfsfunktionen ----------

def _load() -> Dict[str, Any]:
    try:
        with open(CODES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.info("somfy_codes.json nicht gefunden — initialisiere.")
        return copy.deepcopy(_EMPTY_STORE)
    except json.JSONDecodeError as e:
        logger.error("Fehler beim Lesen von somfy_codes.json: %s — setze zurück.", e)
        return copy.deepcopy(_EMPTY_STORE)


def _save_atomic(store: Dict[str, Any]) -> None:
    """Schreibt store atomar in CODES_PATH (tempfile + os.replace)."""
    dir_ = os.path.dirname(os.path.abspath(CODES_PATH))
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=dir_, delete=False, suffix=".tmp", encoding="utf-8"
        ) as tmp:
            json.dump(store, tmp, indent=2, ensure_ascii=False)
            tmp_path = tmp.name
        os.replace(tmp_path, CODES_PATH)
    except OSError as e:
        logger.error("Kann somfy_codes.json nicht speichern: %s", e)


def _find_or_create_device(store: Dict, address: str, name: str) -> Dict:
    addr = address.upper()
    for dev in store["devices"]:
        if dev.get("address", "").upper() == addr:
            return dev
    entry: Dict[str, Any] = {"address": addr, "name": name, "rolling_code": 0}
    store["devices"].append(entry)
    return entry


# ---------- öffentliche API ----------

def get_and_increment(address: str, name: str = "") -> tuple[int, int]:
    """Inkrementiert den Rolling Code für address, speichert ATOMAR und gibt beide Codes zurück.

    Diese Funktion persistiert BEVOR sie zurückkehrt. Der Aufrufer sendet
    anschließend den RTS-Befehl mit dem neuen Code.

    Args:
        address: 6-stellige Hex-Adresse (Groß- oder Kleinschreibung)
        name: Gerätename (nur für somfy_codes.json lesbar)

    Returns:
        Tuple (old_code, new_code): alter Code vor Inkrement, neuer Code nach Inkrement
        (neuer Code = 1–65535, 16-Bit Rollover)
    """
    store = _load()
    entry = _find_or_create_device(store, address, name)

    old_code = entry["rolling_code"]
    new_code = (old_code + 1) % 0x10000  # 16-Bit Rollover
    entry["rolling_code"] = new_code
    if name:
        entry["name"] = name

    _save_atomic(store)  # ATOMAR PERSISTIEREN, bevor RTS gesendet wird
    logger.debug("RC %s: %d → %d", address.upper(), old_code, new_code)

    # Structured frame logging (optional — only active after init())
    from .rts_logger import rts_logger  # noqa: PLC0415
    if rts_logger is not None:
        rts_logger.log_rc_persist(address.upper(), new_code, CODES_PATH)

    return old_code, new_code


def get_current(address: str) -> int:
    """Gibt den aktuellen (letzten gesendeten) Rolling Code zurück — ohne Änderung."""
    addr = address.upper()
    for dev in _load()["devices"]:
        if dev.get("address", "").upper() == addr:
            return dev.get("rolling_code", 0)
    return 0


def get_settings() -> Dict[str, Any]:
    """Gibt den settings-Block aus somfy_codes.json zurück."""
    return _load().get("settings", copy.deepcopy(_EMPTY_STORE["settings"]))


def set_address_prefix(prefix: str, lock: bool = True) -> None:
    """Setzt den Adress-Präfix und sperrt ihn optional nach dem ersten Gerät."""
    store = _load()
    store["settings"]["address_prefix"] = prefix.upper()
    store["settings"]["prefix_locked"] = lock
    _save_atomic(store)
    logger.info("Adress-Präfix gesetzt: %s (locked=%s)", prefix.upper(), lock)

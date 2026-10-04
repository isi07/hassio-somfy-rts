"""Atomare Rolling Code Verwaltung — persistiert in /data/somfy_codes.json.

KRITISCH: Der Rolling Code MUSS atomar gespeichert werden BEVOR der RTS-Befehl
gesendet wird. Bei Stromausfall während des Sendens ist der Code bereits sicher
persistiert und der Motor kann beim nächsten Befehl reagieren.

Atomic write: tempfile + flush + fsync + os.replace() + directory fsync.
Any write failure raises RollingCodeStoreError — callers must not transmit then.

A missing file (first start) yields an empty store. An existing but unreadable or
structurally invalid file is NEVER replaced: a one-time copy is saved as
``<file>.corrupt-<timestamp>`` and every load raises RollingCodeStoreError until
the file is repaired manually.

All load-modify-save cycles must hold store_lock() — the MQTT callback thread
(paho) and the aiohttp event loop access the store concurrently.
"""

import copy
import json
import logging
import os
import shutil
import tempfile
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

CODES_PATH = os.environ.get("SOMFY_CODES_PATH", "/data/somfy_codes.json")

_EMPTY_STORE: dict[str, Any] = {
    "devices": [],
    "groups": [],
    "settings": {
        "address_prefix": "A000",
        "prefix_locked": False,
    },
}

# Reentrant: callers may hold it around a cycle that itself calls _load/_save_atomic.
_STORE_LOCK = threading.RLock()

# Path of the backup made for the current corruption episode (one copy only).
_corrupt_backup: str | None = None


class RollingCodeStoreError(OSError):
    """somfy_codes.json cannot be read or written safely — do not transmit."""


def store_lock() -> threading.RLock:
    """Return the lock guarding every load-modify-save cycle on somfy_codes.json.

    Returns:
        Reentrant lock, usable as ``with store_lock(): ...``.
    """
    return _STORE_LOCK


# ---------- interne Hilfsfunktionen ----------

def _backup_corrupt_file() -> None:
    """Copy the unreadable store aside once per corruption episode."""
    global _corrupt_backup
    if _corrupt_backup is not None:
        return
    target = f"{CODES_PATH}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}"
    try:
        shutil.copy2(CODES_PATH, target)
        _corrupt_backup = target
        logger.error("Beschädigte somfy_codes.json gesichert als %s", target)
    except OSError as e:
        logger.error("Kann beschädigte somfy_codes.json nicht sichern: %s", e)


def _load() -> dict[str, Any]:
    """Load the store from CODES_PATH.

    Returns:
        Parsed store; an empty store if the file does not exist yet.

    Raises:
        RollingCodeStoreError: File exists but is unreadable or invalid.
    """
    global _corrupt_backup
    with _STORE_LOCK:
        try:
            with open(CODES_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.info("somfy_codes.json nicht gefunden — initialisiere.")
            return copy.deepcopy(_EMPTY_STORE)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            _backup_corrupt_file()
            raise RollingCodeStoreError(
                f"somfy_codes.json ist beschädigt ({e}) — Senden gesperrt, "
                "Datei manuell reparieren oder aus Backup wiederherstellen."
            ) from e
        except OSError as e:
            raise RollingCodeStoreError(
                f"somfy_codes.json nicht lesbar: {e}"
            ) from e

        if not isinstance(data, dict) or not isinstance(data.get("devices"), list):
            _backup_corrupt_file()
            raise RollingCodeStoreError(
                "somfy_codes.json hat eine ungültige Struktur (kein 'devices'-Array) — "
                "Senden gesperrt, Datei manuell reparieren."
            )

        _corrupt_backup = None
        return data


def _fsync_dir(path: str) -> None:
    """fsync a directory so the rename itself is durable (POSIX only)."""
    if os.name != "posix":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _save_atomic(store: dict[str, Any]) -> None:
    """Write store atomically to CODES_PATH (tempfile + fsync + os.replace).

    Raises:
        RollingCodeStoreError: The store could not be persisted. The previous
            file is left untouched and no temp file remains.
    """
    dir_ = os.path.dirname(os.path.abspath(CODES_PATH))
    with _STORE_LOCK:
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=dir_, delete=False, suffix=".tmp", encoding="utf-8"
            ) as tmp:
                tmp_path = tmp.name
                json.dump(store, tmp, indent=2, ensure_ascii=False)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_path, CODES_PATH)
            tmp_path = None
            _fsync_dir(dir_)
        except OSError as e:
            logger.error("Kann somfy_codes.json nicht speichern: %s", e)
            raise RollingCodeStoreError(
                f"somfy_codes.json konnte nicht gespeichert werden: {e}"
            ) from e
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


def _find_or_create_device(store: dict, address: str, name: str) -> dict:
    addr = address.upper()
    for dev in store["devices"]:
        if dev.get("address", "").upper() == addr:
            return dev
    entry: dict[str, Any] = {"address": addr, "name": name, "rolling_code": 0}
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

    Raises:
        RollingCodeStoreError: Store unreadable or the new code could not be
            persisted — the caller MUST NOT transmit.
    """
    with _STORE_LOCK:
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
    from .rts_logger import rts_logger
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


def get_settings() -> dict[str, Any]:
    """Gibt den settings-Block aus somfy_codes.json zurück."""
    return _load().get("settings", copy.deepcopy(_EMPTY_STORE["settings"]))


def set_address_prefix(prefix: str, lock: bool = True) -> None:
    """Setzt den Adress-Präfix und sperrt ihn optional nach dem ersten Gerät."""
    with _STORE_LOCK:
        store = _load()
        settings = store.setdefault("settings", {})
        settings["address_prefix"] = prefix.upper()
        settings["prefix_locked"] = lock
        _save_atomic(store)
    logger.info("Adress-Präfix gesetzt: %s (locked=%s)", prefix.upper(), lock)

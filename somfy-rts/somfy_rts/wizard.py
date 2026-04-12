"""Pairing wizard for Somfy RTS devices.

5-step pairing flow:
  1. IDLE         — waiting to start
  2. ADDR_READY   — address generated, rolling code initialized at 0
  3. PROG_SENT    — PROG command (0x8) transmitted via CUL
  4. CONFIRMED    — motor confirmed pairing (operator presses STOP in HA)
  5. FAILED       — timeout or transmission error

Address generation:
  Format: <prefix_4hex><sequence_2hex>  → 6 hex chars total
  Example: prefix "A000", sequence 1 → "A00001"
  Prefix is read from somfy_codes.json settings and locked after the first device.

ioBroker import:
  Accepts a manual address + rolling code so motors already paired via ioBroker
  can be migrated without re-pairing. Rolling code must be ≥ the last ioBroker value.
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from .gateway import BaseGateway, GatewayError
from .rolling_code import (
    _load,
    _save_atomic,
    _find_or_create_device,
    set_address_prefix,
)
from . import rts as rts_module

logger = logging.getLogger(__name__)

# Seconds to wait after sending PROG before declaring failure
PROG_TIMEOUT_S = 120


class WizardState(Enum):
    IDLE = auto()
    ADDR_READY = auto()
    PROG_SENT = auto()
    CONFIRMED = auto()
    FAILED = auto()


@dataclass
class WizardSession:
    """Holds the mutable state of a single pairing session."""
    address: str = ""
    name: str = ""
    device_type: str = "shutter"
    state: WizardState = WizardState.IDLE
    prog_sent_at: Optional[float] = None
    error: str = ""


class PairingWizard:
    """Guides a new Somfy RTS device through the 5-step pairing process.

    Usage:
        wizard = PairingWizard(gateway)
        addr = wizard.start("Wohnzimmer Rollladen", "shutter")
        wizard.send_prog()          # step 3: transmit PROG
        # user presses STOP on motor remote to confirm
        wizard.confirm()            # step 4: save to somfy_codes.json
        cfg = wizard.get_device_config()
    """

    def __init__(self, gateway: BaseGateway, address_prefix: str = "A000") -> None:
        self._gateway = gateway
        self._address_prefix = address_prefix.upper()
        self._session = WizardSession()

    # ---------- Step 1 / 2: Start & address generation ----------

    def start(self, name: str, device_type: str = "shutter") -> str:
        """Generate a new unique address and initialize rolling code at 0.

        Returns the generated 6-char hex address.
        Prefix is locked in somfy_codes.json after first call.
        """
        self._session = WizardSession(name=name, device_type=device_type)

        address = self._next_address(name)
        self._session.address = address
        self._session.state = WizardState.ADDR_READY

        logger.info(
            "Wizard ADDR_READY: '%s' → Adresse %s (Typ %s)",
            name, address, device_type,
        )
        return address

    # ---------- Step 3: Send PROG ----------

    def send_prog(self) -> None:
        """Transmit the PROG command (0x8) to put the motor in pairing mode.

        Rolling code is atomically persisted before transmission.
        Motor expects this within 2 minutes of the original remote's PROG press.
        """
        if self._session.state != WizardState.ADDR_READY:
            raise RuntimeError(
                f"Wizard nicht im Status ADDR_READY (aktuell: {self._session.state.name})"
            )

        try:
            commands = rts_module.build_rts_sequence(
                self._session.address, "PROG", self._session.name
            )
            for cmd in commands:
                self._gateway.send_raw(cmd)

            self._session.state = WizardState.PROG_SENT
            self._session.prog_sent_at = time.monotonic()
            logger.info(
                "Wizard PROG_SENT: PROG gesendet an %s — warte auf Motor-Bestätigung (%ds).",
                self._session.address, PROG_TIMEOUT_S,
            )
        except (GatewayError, ValueError) as e:
            self._session.state = WizardState.FAILED
            self._session.error = str(e)
            logger.error("Wizard FAILED: PROG Sendefehler: %s", e)
            raise

    # ---------- Step 4: Confirm ----------

    def confirm(self) -> None:
        """Mark pairing as confirmed (operator saw motor jog up/down).

        Call this after the user observes the motor's confirmation movement.
        The device entry already exists in somfy_codes.json from send_prog().
        """
        if self._session.state != WizardState.PROG_SENT:
            raise RuntimeError(
                f"Wizard nicht im Status PROG_SENT (aktuell: {self._session.state.name})"
            )

        if self._is_timed_out():
            self._session.state = WizardState.FAILED
            self._session.error = f"Timeout nach {PROG_TIMEOUT_S}s"
            raise RuntimeError(self._session.error)

        self._session.state = WizardState.CONFIRMED
        logger.info(
            "Wizard CONFIRMED: '%s' (%s) erfolgreich angelernt.",
            self._session.name, self._session.address,
        )

    # ---------- Step 5: Result ----------

    def get_device_config(self) -> dict:
        """Return the config dict ready for insertion into options.json devices list."""
        if self._session.state != WizardState.CONFIRMED:
            raise RuntimeError("Pairing nicht bestätigt.")
        return {
            "name": self._session.name,
            "type": self._session.device_type,
            "address": self._session.address,
            "mode": "A",
        }

    # ---------- ioBroker import ----------

    @staticmethod
    def import_from_iobroker(
        name: str,
        device_type: str,
        address: str,
        rolling_code: int,
    ) -> dict:
        """Import a device already paired via ioBroker — no re-pairing needed.

        The rolling code must be ≥ the last value used in ioBroker, otherwise
        the motor will ignore subsequent commands.

        Args:
            name:         Display name for the device.
            device_type:  One of: awning, shutter, blind, screen, gate, light, heater.
            address:      6-char hex address as used in ioBroker (e.g. "A1B2C3").
            rolling_code: Last rolling code value from ioBroker (add a safety margin of ~10).

        Returns:
            Config dict ready for insertion into options.json devices list.
        """
        addr = address.upper()
        store = _load()
        entry = _find_or_create_device(store, addr, name)
        entry["rolling_code"] = int(rolling_code)
        if name:
            entry["name"] = name
        _save_atomic(store)

        logger.info(
            "ioBroker import: '%s' Adresse=%s RC=%d gespeichert.",
            name, addr, rolling_code,
        )
        return {
            "name": name,
            "type": device_type,
            "address": addr,
            "mode": "A",
        }

    # ---------- State helpers ----------

    @property
    def state(self) -> WizardState:
        return self._session.state

    @property
    def address(self) -> str:
        return self._session.address

    def is_timed_out(self) -> bool:
        return self._is_timed_out()

    # ---------- Internal ----------

    def _next_address(self, name: str) -> str:
        """Generate next address: <prefix_4hex><sequence_2hex>.
        Prefix comes from config (SOMFY_ADDRESS_PREFIX), not from somfy_codes.json.
        """
        store = _load()
        prefix = self._address_prefix
        devices = store.get("devices", [])

        # Sequence = number of existing devices + 1, capped at 0xFF
        sequence = (len(devices) + 1) & 0xFF
        address = f"{prefix}{sequence:02X}"

        # Ensure uniqueness — increment if already taken
        existing = {d.get("address", "").upper() for d in devices}
        while address in existing:
            sequence = (sequence + 1) & 0xFF
            address = f"{prefix}{sequence:02X}"

        # Lock prefix in somfy_codes.json after first device is added
        settings = store.get("settings", {})
        if not settings.get("prefix_locked", False):
            set_address_prefix(prefix, lock=True)

        # Pre-create entry with RC=0 so it's present even before send_prog()
        entry = _find_or_create_device(store, address, name)
        entry["rolling_code"] = 0
        _save_atomic(store)

        return address

    def _is_timed_out(self) -> bool:
        if self._session.prog_sent_at is None:
            return False
        return (time.monotonic() - self._session.prog_sent_at) > PROG_TIMEOUT_S

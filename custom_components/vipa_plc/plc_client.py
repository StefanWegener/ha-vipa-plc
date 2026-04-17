"""PLC client abstraction using python-snap7 for the VIPA PLC integration."""
from __future__ import annotations

import logging
import time

import snap7.client
import snap7.util

from .address import S7Address, parse_address

_LOGGER = logging.getLogger(__name__)

# snap7 raises RuntimeError on communication/connection failures.
_SNAP7_ERRORS = (RuntimeError, OSError)


class PLCConnectionError(Exception):
    """Raised when a PLC connection attempt fails."""


class PLCCommunicationError(Exception):
    """Raised when a read or write operation fails."""


class PLCClient:
    """Thin wrapper around snap7.client.Client for VIPA / S7 PLCs."""

    def __init__(self, host: str, rack: int, slot: int, port: int = 102) -> None:
        self._host = host
        self._rack = rack
        self._slot = slot
        self._port = port
        self._client = snap7.client.Client()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to the PLC.

        Raises:
            PLCConnectionError: If the connection cannot be established.
        """
        _LOGGER.debug(
            "Connecting to PLC at %s:%d (rack=%d, slot=%d)",
            self._host,
            self._port,
            self._rack,
            self._slot,
        )
        try:
            self._client.connect(self._host, self._rack, self._slot, self._port)
        except _SNAP7_ERRORS as exc:
            _LOGGER.error(
                "Failed to connect to PLC at %s:%d – %s",
                self._host,
                self._port,
                exc,
            )
            raise PLCConnectionError(
                f"Cannot connect to PLC at {self._host}:{self._port}: {exc}"
            ) from exc

        if not self._client.get_connected():
            raise PLCConnectionError(
                f"Connection to PLC at {self._host}:{self._port} reported success "
                "but client is not connected"
            )

        _LOGGER.debug("Connected to PLC at %s:%d", self._host, self._port)

    def disconnect(self) -> None:
        """Disconnect from the PLC."""
        try:
            self._client.disconnect()
        except _SNAP7_ERRORS:
            pass
        _LOGGER.debug("Disconnected from PLC at %s:%d", self._host, self._port)

    def is_connected(self) -> bool:
        """Return True if the client currently has an active connection."""
        try:
            return bool(self._client.get_connected())
        except _SNAP7_ERRORS:
            return False

    # ------------------------------------------------------------------
    # Read / write helpers
    # ------------------------------------------------------------------

    def _resolve(self, address: str) -> S7Address:
        """Parse and return an S7Address, raising PLCCommunicationError on failure."""
        return parse_address(address)

    def read_bool(self, address: str) -> bool:
        """Read a single boolean bit from the PLC.

        Args:
            address: S7 address string e.g. ``DB2,X0.0``.

        Returns:
            Boolean value of the bit.

        Raises:
            PLCCommunicationError: On communication failure.
        """
        addr = self._resolve(address)
        _LOGGER.debug("Reading bit %s", addr)
        try:
            data = self._client.db_read(addr.db_number, addr.byte_index, 1)
            value = snap7.util.get_bool(data, 0, addr.bit_index)
        except _SNAP7_ERRORS as exc:
            _LOGGER.error("Read error for %s: %s", addr, exc)
            raise PLCCommunicationError(f"Read failed for {addr}: {exc}") from exc
        _LOGGER.debug("Read %s = %s", addr, value)
        return bool(value)

    def write_bool(self, address: str, value: bool) -> None:
        """Write a single boolean bit to the PLC.

        Args:
            address: S7 address string e.g. ``DB12,X6.0``.
            value: Boolean value to write.

        Raises:
            PLCCommunicationError: On communication failure.
        """
        addr = self._resolve(address)
        _LOGGER.debug("Writing bit %s = %s", addr, value)
        try:
            data = self._client.db_read(addr.db_number, addr.byte_index, 1)
            snap7.util.set_bool(data, 0, addr.bit_index, value)
            self._client.db_write(addr.db_number, addr.byte_index, data)
        except _SNAP7_ERRORS as exc:
            _LOGGER.error("Write error for %s: %s", addr, exc)
            raise PLCCommunicationError(f"Write failed for {addr}: {exc}") from exc
        _LOGGER.debug("Wrote %s = %s", addr, value)

    def pulse_bool(self, address: str, duration: float) -> None:
        """Write True, wait *duration* seconds, then write False.

        Args:
            address: S7 address string.
            duration: How long (seconds) to hold the bit high.

        Raises:
            PLCCommunicationError: On communication failure.
        """
        _LOGGER.debug("Pulsing bit %s for %.2f s", address, duration)
        self.write_bool(address, True)
        time.sleep(duration)
        self.write_bool(address, False)
        _LOGGER.debug("Pulse complete for %s", address)

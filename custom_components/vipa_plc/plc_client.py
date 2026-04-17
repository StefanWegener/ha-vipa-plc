"""PLC client abstraction using python-snap7 for the VIPA PLC integration."""
from __future__ import annotations

import logging
import threading
import time

_LOGGER = logging.getLogger(__name__)

# On Home Assistant OS (and other systems without ldconfig), ctypes.util.find_library()
# cannot locate libsnap7.  python-snap7 ships the native library inside its own package
# under snap7/lib/libsnap7.so.  We call snap7.common.load_library() with the explicit
# path before anything else imports snap7, so the singleton is already initialised with
# the correct path when snap7.client is imported below.
try:
    import pathlib

    import snap7.common as _snap7_common  # noqa: PLC0415

    _snap7_dir = pathlib.Path(_snap7_common.__file__).parent
    _lib_dir = _snap7_dir / "lib"
    _candidates = (
        list(_lib_dir.glob("libsnap7.so*")) if _lib_dir.is_dir() else []
    ) + list(_snap7_dir.glob("libsnap7.so*"))

    if _candidates:
        _lib_path = str(_candidates[0])
        _LOGGER.debug("Pre-loading snap7 library from %s", _lib_path)
        _snap7_common.load_library(_lib_path)
    else:
        _LOGGER.warning(
            "No bundled libsnap7.so found in %s – relying on system library", _snap7_dir
        )
except Exception as _exc:  # noqa: BLE001
    _LOGGER.warning("snap7 pre-load failed (%s) – relying on system library", _exc)

import snap7.client
import snap7.util

from .address import S7Address, parse_address

# snap7 raises RuntimeError or OSError on most failures.
# Newer versions of snap7 (≥ 1.4) introduce S7ConnectionError (a subclass of
# RuntimeError) specifically for broken TCP sessions (invalid TPKT/COTP frames).
# We import it defensively so the integration works with older snap7 builds too.
try:
    from snap7.error import S7ConnectionError as _Snap7ConnectionError  # type: ignore[attr-defined]
except (ImportError, AttributeError):
    try:
        from snap7.exceptions import Snap7Exception as _Snap7ConnectionError  # type: ignore[assignment]
    except (ImportError, AttributeError):
        _Snap7ConnectionError = RuntimeError  # type: ignore[assignment,misc]

Snap7ConnectionError = _Snap7ConnectionError

# Tuple of all snap7 exception types treated as communication failures
_SNAP7_ERRORS = (RuntimeError, OSError, Snap7ConnectionError)


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
        self._client: snap7.client.Client | None = None
        self._lock = threading.Lock()

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
            self._client = snap7.client.Client()
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
        if self._client is None:
            return
        try:
            self._client.disconnect()
        except _SNAP7_ERRORS:
            pass
        _LOGGER.debug("Disconnected from PLC at %s:%d", self._host, self._port)

    def is_connected(self) -> bool:
        """Return True if the client currently has an active connection."""
        if self._client is None:
            return False
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

    def _mark_disconnected(self) -> None:
        """Tear down the snap7 client so is_connected() returns False on next check."""
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._client = None
        _LOGGER.debug("PLC connection marked as disconnected after communication error")

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
        with self._lock:
            if self._client is None:
                raise PLCCommunicationError(f"Read failed for {addr}: not connected")
            try:
                data = self._client.db_read(addr.db_number, addr.byte_index, 1)
                value = snap7.util.get_bool(data, 0, addr.bit_index)
            except Snap7ConnectionError as exc:
                _LOGGER.warning("Connection lost during read of %s: %s – marking disconnected", addr, exc)
                self._mark_disconnected()
                raise PLCCommunicationError(f"Read failed for {addr}: {exc}") from exc
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
        with self._lock:
            if self._client is None:
                raise PLCCommunicationError(f"Write failed for {addr}: not connected")
            try:
                data = self._client.db_read(addr.db_number, addr.byte_index, 1)
                snap7.util.set_bool(data, 0, addr.bit_index, value)
                self._client.db_write(addr.db_number, addr.byte_index, data)
            except Snap7ConnectionError as exc:
                _LOGGER.warning("Connection lost during write of %s: %s – marking disconnected", addr, exc)
                self._mark_disconnected()
                raise PLCCommunicationError(f"Write failed for {addr}: {exc}") from exc
            except _SNAP7_ERRORS as exc:
                _LOGGER.error("Write error for %s: %s", addr, exc)
                raise PLCCommunicationError(f"Write failed for {addr}: {exc}") from exc
        _LOGGER.debug("Wrote %s = %s", addr, value)

    def pulse_bool(self, address: str, duration: float) -> None:
        """Write True, wait *duration* seconds, then write False.

        The reset to False is performed in a ``finally`` block so the PLC bit
        is always cleared, even when an exception occurs during the sleep.

        Args:
            address: S7 address string.
            duration: How long (seconds) to hold the bit high (max 10.0).

        Raises:
            PLCCommunicationError: On communication failure.
        """
        duration = min(duration, 10.0)  # safety cap
        _LOGGER.debug("Pulsing bit %s for %.2f s", address, duration)
        self.write_bool(address, True)
        try:
            time.sleep(duration)
        finally:
            try:
                self.write_bool(address, False)
            except PLCCommunicationError:
                _LOGGER.error(
                    "Failed to reset bit %s after pulse – bit may be stuck HIGH!", address
                )
                raise
        _LOGGER.debug("Pulse complete for %s", address)

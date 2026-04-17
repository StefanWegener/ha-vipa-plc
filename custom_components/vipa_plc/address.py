"""S7 address parser for the VIPA PLC integration.

Supported format: DB<number>,X<byte>.<bit>
Examples:
  DB2,X0.0   -> db_number=2, byte_index=0, bit_index=0
  DB12,X6.0  -> db_number=12, byte_index=6, bit_index=0
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ADDRESS_RE = re.compile(r"^DB(\d+),X(\d+)\.([0-7])$")


@dataclass
class S7Address:
    """Parsed S7 DB bit address."""

    db_number: int
    byte_index: int
    bit_index: int

    def __str__(self) -> str:
        return f"DB{self.db_number},X{self.byte_index}.{self.bit_index}"


class AddressParseError(ValueError):
    """Raised when an S7 address string cannot be parsed."""


def parse_address(address: str) -> S7Address:
    """Parse an S7 DB bit address string.

    Args:
        address: String in the form ``DB<n>,X<byte>.<bit>`` where bit is 0-7.

    Returns:
        Parsed :class:`S7Address`.

    Raises:
        AddressParseError: If the address does not match the expected format.
    """
    address = address.strip()
    match = _ADDRESS_RE.match(address)
    if not match:
        raise AddressParseError(
            f"Invalid S7 address '{address}'. "
            "Expected format: DB<number>,X<byte>.<bit>  e.g. DB2,X0.0"
        )
    db_number = int(match.group(1))
    byte_index = int(match.group(2))
    bit_index = int(match.group(3))
    return S7Address(db_number=db_number, byte_index=byte_index, bit_index=bit_index)

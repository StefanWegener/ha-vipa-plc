"""Tests for address.py – S7 address parser."""
import pytest

from custom_components.vipa_plc.address import (
    AddressParseError,
    S7Address,
    parse_address,
)


class TestParseAddress:
    """Tests for parse_address()."""

    def test_basic_db2_x0_0(self) -> None:
        addr = parse_address("DB2,X0.0")
        assert addr.db_number == 2
        assert addr.byte_index == 0
        assert addr.bit_index == 0

    def test_db12_x6_0(self) -> None:
        addr = parse_address("DB12,X6.0")
        assert addr.db_number == 12
        assert addr.byte_index == 6
        assert addr.bit_index == 0

    def test_large_db_number(self) -> None:
        addr = parse_address("DB999,X255.7")
        assert addr.db_number == 999
        assert addr.byte_index == 255
        assert addr.bit_index == 7

    def test_leading_trailing_whitespace(self) -> None:
        addr = parse_address("  DB2,X0.0  ")
        assert addr.db_number == 2

    def test_str_representation(self) -> None:
        addr = S7Address(db_number=2, byte_index=0, bit_index=0)
        assert str(addr) == "DB2,X0.0"

    def test_invalid_empty_string(self) -> None:
        with pytest.raises(AddressParseError):
            parse_address("")

    def test_invalid_plain_text(self) -> None:
        with pytest.raises(AddressParseError):
            parse_address("invalid")

    def test_invalid_merker_address(self) -> None:
        with pytest.raises(AddressParseError):
            parse_address("M2.0")

    def test_invalid_bit_index_out_of_range(self) -> None:
        with pytest.raises(AddressParseError):
            parse_address("DB2,X0.8")

    def test_invalid_missing_db(self) -> None:
        with pytest.raises(AddressParseError):
            parse_address("X0.0")

    def test_invalid_no_bit(self) -> None:
        with pytest.raises(AddressParseError):
            parse_address("DB2,X0")

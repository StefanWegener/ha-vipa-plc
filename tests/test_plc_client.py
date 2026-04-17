"""Tests for plc_client.py."""
from unittest.mock import MagicMock, patch

import pytest

from custom_components.vipa_plc.plc_client import (
    PLCCommunicationError,
    PLCConnectionError,
    PLCClient,
)


@pytest.fixture()
def mock_snap7_client():
    """Return a mocked snap7.client.Client."""
    with patch("custom_components.vipa_plc.plc_client.snap7.client.Client") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


class TestPLCClientConnect:
    def test_connect_success(self, mock_snap7_client: MagicMock) -> None:
        mock_snap7_client.get_connected.return_value = True
        client = PLCClient("192.168.3.125", 0, 2, 102)
        client.connect()
        mock_snap7_client.connect.assert_called_once_with("192.168.3.125", 0, 2, 102)

    def test_connect_raises_on_runtime_error(self, mock_snap7_client: MagicMock) -> None:
        mock_snap7_client.connect.side_effect = RuntimeError("timeout")
        client = PLCClient("192.168.3.125", 0, 2, 102)
        with pytest.raises(PLCConnectionError):
            client.connect()

    def test_connect_raises_if_not_connected_after(self, mock_snap7_client: MagicMock) -> None:
        mock_snap7_client.get_connected.return_value = False
        client = PLCClient("192.168.3.125", 0, 2, 102)
        with pytest.raises(PLCConnectionError):
            client.connect()

    def test_is_connected_false_by_default(self, mock_snap7_client: MagicMock) -> None:
        client = PLCClient("192.168.3.125", 0, 2, 102)
        assert not client.is_connected()


class TestPLCClientReadWrite:
    def test_read_bool(self, mock_snap7_client: MagicMock) -> None:
        data = bytearray([0b00000001])  # bit 0 is True
        mock_snap7_client.db_read.return_value = data
        mock_snap7_client.get_connected.return_value = True
        client = PLCClient("192.168.3.125", 0, 2, 102)
        client.connect()
        result = client.read_bool("DB2,X0.0")
        assert result is True
        mock_snap7_client.db_read.assert_called_once_with(2, 0, 1)

    def test_read_bool_raises_on_error(self, mock_snap7_client: MagicMock) -> None:
        mock_snap7_client.db_read.side_effect = RuntimeError("read error")
        mock_snap7_client.get_connected.return_value = True
        client = PLCClient("192.168.3.125", 0, 2, 102)
        client.connect()
        with pytest.raises(PLCCommunicationError):
            client.read_bool("DB2,X0.0")

    def test_write_bool(self, mock_snap7_client: MagicMock) -> None:
        data = bytearray([0b00000000])
        mock_snap7_client.db_read.return_value = data
        mock_snap7_client.get_connected.return_value = True
        client = PLCClient("192.168.3.125", 0, 2, 102)
        client.connect()
        client.write_bool("DB2,X0.0", True)
        mock_snap7_client.db_write.assert_called_once()

    def test_write_bool_raises_on_error(self, mock_snap7_client: MagicMock) -> None:
        mock_snap7_client.db_read.side_effect = RuntimeError("write error")
        mock_snap7_client.get_connected.return_value = True
        client = PLCClient("192.168.3.125", 0, 2, 102)
        client.connect()
        with pytest.raises(PLCCommunicationError):
            client.write_bool("DB2,X0.0", True)

    def test_pulse_bool(self, mock_snap7_client: MagicMock) -> None:
        data = bytearray([0b00000000])
        mock_snap7_client.db_read.return_value = data
        mock_snap7_client.get_connected.return_value = True
        client = PLCClient("192.168.3.125", 0, 2, 102)
        client.connect()
        with patch("custom_components.vipa_plc.plc_client.time.sleep") as mock_sleep:
            client.pulse_bool("DB2,X0.0", 0.1)
            mock_sleep.assert_called_once_with(0.1)
        assert mock_snap7_client.db_write.call_count == 2

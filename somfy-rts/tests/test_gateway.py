"""Tests for SimGateway and CULGateway in gateway.py."""

import pytest


class TestSimGateway:
    def test_initial_state_disconnected(self):
        from somfy_rts.gateway import SimGateway
        gw = SimGateway()
        assert gw.is_connected is False

    def test_connect_sets_connected(self):
        from somfy_rts.gateway import SimGateway
        gw = SimGateway()
        gw.connect()
        assert gw.is_connected is True

    def test_disconnect_clears_connected(self):
        from somfy_rts.gateway import SimGateway
        gw = SimGateway()
        gw.connect()
        gw.disconnect()
        assert gw.is_connected is False

    def test_port_name_default(self):
        from somfy_rts.gateway import SimGateway
        gw = SimGateway()
        assert gw.port_name == "sim://localhost"

    def test_port_name_custom(self):
        from somfy_rts.gateway import SimGateway
        gw = SimGateway(port="sim://test")
        assert gw.port_name == "sim://test"

    def test_send_raw_records_command(self):
        from somfy_rts.gateway import SimGateway
        gw = SimGateway()
        gw.connect()
        gw.send_raw("Yr1")
        gw.send_raw("YsA002001AA00001")
        assert gw.sent_commands == ["Yr1", "YsA002001AA00001"]

    def test_send_raw_raises_when_disconnected(self):
        from somfy_rts.gateway import GatewayError, SimGateway
        gw = SimGateway()
        with pytest.raises(GatewayError):
            gw.send_raw("Yr1")

    def test_sent_commands_empty_initially(self):
        from somfy_rts.gateway import SimGateway
        gw = SimGateway()
        assert gw.sent_commands == []

    def test_disconnect_when_not_connected_is_noop(self):
        from somfy_rts.gateway import SimGateway
        gw = SimGateway()
        gw.disconnect()  # must not raise
        assert gw.is_connected is False

    def test_multiple_connects(self):
        from somfy_rts.gateway import SimGateway
        gw = SimGateway()
        gw.connect()
        gw.disconnect()
        gw.connect()
        assert gw.is_connected is True
        assert gw.sent_commands == []  # commands cleared between connections? No — only on new instance


class TestCULGatewayReconnect:
    """Tests for CULGateway.send_raw() auto-reconnect on I/O errors."""

    def _make_gateway(self):
        """Return a CULGateway with a mocked serial port already 'open'."""
        from unittest.mock import MagicMock, patch
        import serial
        from somfy_rts.gateway import CULGateway

        gw = CULGateway("/dev/ttyACM0")
        mock_serial = MagicMock(spec=serial.Serial)
        mock_serial.is_open = True
        gw._serial = mock_serial
        return gw, mock_serial

    def test_send_raw_raises_gateway_error_on_os_error(self):
        """OSError during write → GatewayError is raised."""
        from somfy_rts.gateway import GatewayError
        gw, mock_serial = self._make_gateway()
        mock_serial.write.side_effect = OSError("USB disconnected")

        with pytest.raises(GatewayError, match="I/O Fehler"):
            gw.send_raw("Yr1")

    def test_send_raw_closes_serial_before_reconnect(self):
        """On I/O error the serial port is closed before reconnect attempt."""
        from somfy_rts.gateway import GatewayError
        from unittest.mock import patch
        gw, mock_serial = self._make_gateway()
        mock_serial.write.side_effect = OSError("broken pipe")

        with patch.object(gw, "connect", side_effect=GatewayError("no device")):
            with pytest.raises(GatewayError):
                gw.send_raw("Yr1")

        mock_serial.close.assert_called_once()

    def test_send_raw_attempts_reconnect_on_serial_exception(self):
        """serial.SerialException triggers a reconnect attempt."""
        import serial
        from somfy_rts.gateway import GatewayError
        from unittest.mock import patch
        gw, mock_serial = self._make_gateway()
        mock_serial.write.side_effect = serial.SerialException("device lost")

        connect_called = []
        with patch.object(gw, "connect", side_effect=lambda: connect_called.append(1)):
            with pytest.raises(GatewayError):
                gw.send_raw("Yr1")

        assert len(connect_called) == 1, "connect() must be called exactly once on I/O error"

    def test_send_raw_raises_even_after_successful_reconnect(self):
        """Even when reconnect succeeds the original exception is still raised."""
        from somfy_rts.gateway import GatewayError
        from unittest.mock import patch
        gw, mock_serial = self._make_gateway()
        mock_serial.write.side_effect = OSError("glitch")

        with patch.object(gw, "connect"):  # reconnect succeeds
            with pytest.raises(GatewayError):
                gw.send_raw("Yr1")

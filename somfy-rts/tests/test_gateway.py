"""Tests for SimGateway in gateway.py."""

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

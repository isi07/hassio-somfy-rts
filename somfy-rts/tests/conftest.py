"""Shared pytest fixtures for somfy_rts tests."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def tmp_codes_path(tmp_path, monkeypatch):
    """Point rolling_code.CODES_PATH at a temp file for each test."""
    import somfy_rts.rolling_code as rc
    codes_file = tmp_path / "somfy_codes.json"
    monkeypatch.setattr(rc, "CODES_PATH", str(codes_file))
    return str(codes_file)


@pytest.fixture
def mock_gateway():
    """MagicMock implementing BaseGateway — records send_raw calls."""
    from somfy_rts.gateway import BaseGateway
    gw = MagicMock(spec=BaseGateway)
    gw.is_connected.return_value = True
    return gw

"""HIDTransport.read_ must tell a failed read apart from a timeout."""
from unittest.mock import MagicMock, patch

import pytest

from StreamDock.transport import hid_transport
from StreamDock.transport.hid_transport import HIDReadError, HIDTransport


@pytest.fixture
def transport():
    t = HIDTransport()
    t._device = 0x1234
    return t


def test_timeout_returns_none(transport):
    with patch.object(hid_transport, '_hidapi', MagicMock()) as hidapi:
        hidapi.hid_read_timeout.return_value = 0
        assert transport.read_(13, timeout_ms=10) is None


def test_hidapi_error_raises(transport):
    # An unplugged device returns -1 at once; returning None would make the reader spin.
    with patch.object(hid_transport, '_hidapi', MagicMock()) as hidapi:
        hidapi.hid_read_timeout.return_value = -1
        with pytest.raises(HIDReadError):
            transport.read_(13, timeout_ms=10)


def test_closed_device_raises(transport):
    transport._device = None
    with pytest.raises(HIDReadError):
        transport.read_(13, timeout_ms=10)


def test_read_error_is_an_oserror():
    # StreamDock._read backs off on OSError without importing the transport.
    assert issubclass(HIDReadError, OSError)

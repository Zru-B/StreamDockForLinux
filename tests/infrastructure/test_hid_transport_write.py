"""HIDTransport writes and enumeration against a mocked hidapi."""
import ctypes
from unittest.mock import MagicMock, patch

import pytest

from StreamDock.transport import hid_transport
from StreamDock.transport.hid_transport import HIDTransport, _hid_device_info


@pytest.fixture
def transport():
    t = HIDTransport()
    t._device = 0x1234
    return t


def test_short_write_is_a_failure(transport):
    # A partial packet leaves the device mid-command; only a full write counts.
    with patch.object(hid_transport, '_hidapi', MagicMock()) as hidapi:
        hidapi.hid_write.return_value = 10
        assert transport.set_brightness(50) == -1
        assert transport.wake_screen() == -1

        hidapi.hid_write.return_value = HIDTransport.PACKET_SIZE
        assert transport.set_brightness(50) == 1
        assert transport.wake_screen() == 1


def test_short_header_write_aborts_image_transfer(transport, tmp_path):
    # Guards streaming data packets after the header was only partly sent.
    image = tmp_path / "k.jpg"
    image.write_bytes(b'\x00' * 3000)
    with patch.object(hid_transport, '_hidapi', MagicMock()) as hidapi:
        hidapi.hid_write.return_value = 1
        assert transport.set_key_img_dual_device(str(image), 3) == -1
        assert hidapi.hid_write.call_count == 1


def test_packet_bytes_reach_hidapi_unchanged(transport):
    # Guards the ctypes copy of the packet (from_buffer_copy) dropping or shifting bytes.
    sent = {}

    def fake_write(device, data, length):
        sent['bytes'] = bytes(data[:length])
        return length

    with patch.object(hid_transport, '_hidapi', MagicMock()) as hidapi:
        hidapi.hid_write.side_effect = fake_write
        transport.set_brightness(42)

    assert len(sent['bytes']) == HIDTransport.PACKET_SIZE
    assert sent['bytes'][:12] == b'\x00CRT\x00\x00LIG\x00\x00\x2a'


def test_enumerate_reports_descriptor_strings():
    # Guards serial/manufacturer/product never reaching DeviceInfo; NULL strings become ''.
    second = _hid_device_info(path=b'/dev/b', vendor_id=1, product_id=2,
                              serial_number=None, manufacturer_string=None,
                              product_string=None, interface_number=0)
    first = _hid_device_info(path=b'/dev/a', vendor_id=1, product_id=2,
                             serial_number='SNé1', manufacturer_string='HOTSPOTEKUSB',
                             product_string='Stream Dock', interface_number=0,
                             next=ctypes.pointer(second))

    with patch.object(hid_transport, '_hidapi', MagicMock()) as hidapi:
        hidapi.hid_enumerate.return_value = ctypes.pointer(first)
        devices = HIDTransport().enumerate(1, 2)

    assert devices[0]['serial_number'] == 'SNé1'
    assert devices[0]['manufacturer_string'] == 'HOTSPOTEKUSB'
    assert devices[0]['product_string'] == 'Stream Dock'
    assert devices[1]['serial_number'] == ''
    assert devices[1]['manufacturer_string'] == ''
    assert devices[1]['product_string'] == ''

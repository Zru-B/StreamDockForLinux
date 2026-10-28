"""Tests for the device naming helpers in device_discovery."""

from StreamDock.application.device_discovery import device_label, device_name
from StreamDock.devices.product_ids import STREAMDOCK_293V3_PID, STREAMDOCK_VID
from StreamDock.infrastructure.hardware_interface import DeviceInfo


def _device(vid=STREAMDOCK_VID, pid=STREAMDOCK_293V3_PID, serial='0300D0782D35',
            manufacturer='HOTSPOTEKUSB', product='HOTSPOTEKUSB HID DEMO'):
    return DeviceInfo(vendor_id=vid, product_id=pid, serial_number=serial,
                      path='1-3:1.0', manufacturer=manufacturer, product=product)


def test_known_model_is_named_from_product_id_not_usb_string():
    assert device_name(_device()) == "Stream Dock 293V3"


def test_label_appends_serial_to_model_name():
    assert device_label(_device()) == "Stream Dock 293V3 (0300D0782D35)"


def test_unknown_product_falls_back_to_usb_strings():
    assert device_name(_device(pid=0x9999, product='Other Dock')) == "Other Dock"
    assert device_name(_device(pid=0x9999, product='', manufacturer='')) == "Stream Dock"

from unittest.mock import MagicMock, patch

import pytest

from src.StreamDock.device_manager import DeviceManager
from src.StreamDock.product_ids import USBProductIDs, USBVendorIDs


@pytest.fixture
def mock_transport():
    with patch('src.StreamDock.device_manager.LibUSBHIDAPI') as mock:
        yield mock

@pytest.fixture
def mock_stream_dock_class():
    with patch('src.StreamDock.product_ids.StreamDock293V3') as mock:
        yield mock

def test_enumerate_finds_devices(mock_transport, mock_stream_dock_class):
    # Setup transport mock
    transport_instance = mock_transport.return_value
    fake_device_info = {'path': 'path/to/device', 'vendor_id': USBVendorIDs.USB_PID_293V3, 'product_id': USBProductIDs.USB_PID_STREAMDOCK_293V3EN}
    transport_instance.enumerate.return_value = [fake_device_info]
    
    manager = DeviceManager()
    devices = manager.enumerate()
    
    assert len(devices) == 1
    # Verify transport.enumerate was called with correct VID/PID
    transport_instance.enumerate.assert_called_with(
        vid=USBVendorIDs.USB_PID_293V3, 
        pid=USBProductIDs.USB_PID_STREAMDOCK_293V3EN
    )
    # Verify StreamDock class was instantiated
    # The actual class in product_ids is used in the list g_products. 
    # Since we can't easily patch g_products directly without patching the module where it is defined
    # AND where it is imported. In device_manager.py it does `from .product_ids import g_products`.
    # So patching `src.StreamDock.product_ids.StreamDock293V3` might work if `g_products` uses the name reference, 
    # but `g_products` is defined at module level in `product_ids.py` with the class object.
    # So `from .product_ids import g_products` imports that list.
    # To mock the class used in `g_products`, we might need to patch `src.StreamDock.product_ids.g_products` 
    # OR patch `src.StreamDock.device_manager.g_products`.

@patch('src.StreamDock.device_manager.g_products')
def test_enumerate_uses_g_products(mock_g_products, mock_transport):
    # Setup custom g_products for testing
    mock_cls = MagicMock()
    mock_g_products.__iter__.return_value = [(0x1234, 0x5678, mock_cls)]
    
    transport_instance = mock_transport.return_value
    fake_device_info = {'path': 'path/to/device'}
    transport_instance.enumerate.return_value = [fake_device_info]
    
    manager = DeviceManager()
    devices = manager.enumerate()
    
    assert len(devices) == 1
    transport_instance.enumerate.assert_called_with(vid=0x1234, pid=0x5678)
    mock_cls.assert_called_with(transport_instance, fake_device_info)


@patch('pyudev.Context')
@patch('pyudev.Monitor')
@patch('src.StreamDock.device_manager.g_products')
def test_listen_add_device(mock_g_products, mock_monitor, mock_context, mock_transport):
    # Setup custom g_products
    vid, pid = 0x1234, 0x5678
    mock_cls = MagicMock()
    mock_g_products.__iter__.return_value = [(vid, pid, mock_cls)]
    
    # Setup udev monitor
    monitor_instance = mock_monitor.from_netlink.return_value
    
    # Mock a device add event
    mock_udev_device = MagicMock()
    mock_udev_device.action = 'add'
    mock_udev_device.get.side_effect = lambda x: hex(vid)[2:] if x == 'ID_VENDOR_ID' else hex(pid)[2:]
    mock_udev_device.device_path = '/sys/bus/usb/devices/1-1'
    
    # Configure poll to yield device then None to stop loop
    monitor_instance.poll.side_effect = [mock_udev_device, None]
    
    # Setup transport enumerate to return matching device
    transport_instance = mock_transport.return_value
    # Device path construction in code: device.device_path.split('/')[-1] + ":1.0"
    # '1-1' + ':1.0' = '1-1:1.0'
    expected_suffix = '1-1:1.0'
    fake_device_info = {'path': f'something/{expected_suffix}'}
    transport_instance.enumerate.return_value = [fake_device_info]
    
    manager = DeviceManager()
    manager.listen()
    
    # Verify device was added and opened
    assert len(manager.streamdocks) == 1
    mock_cls.assert_called()
    manager.streamdocks[0].open.assert_called_once()


@patch('pyudev.Context')
@patch('pyudev.Monitor')
@patch('src.StreamDock.device_manager.g_products')
def test_listen_remove_device(mock_g_products, mock_monitor, mock_context, mock_transport):
    # Setup custom g_products
    vid, pid = 0x1234, 0x5678
    mock_cls = MagicMock()
    mock_g_products.__iter__.return_value = [(vid, pid, mock_cls)]
    
    # Setup existing device
    manager = DeviceManager()
    mock_existing_device = MagicMock()
    mock_existing_device.get_path.return_value = 'some/path/1-1:1.0'
    manager.streamdocks.append(mock_existing_device)
    
    # Setup udev monitor
    monitor_instance = mock_monitor.from_netlink.return_value
    
    # Mock a device remove event
    mock_udev_device = MagicMock()
    mock_udev_device.action = 'remove'
    # The code checks: if device.device_path.find(willRemoveDevice.get_path()) != -1:
    # This logic seems inverted or dependent on full paths. 
    # Usually device_path in udev is like /sys/devices/...
    # And HID path is different.
    # Let's check the code: 
    # if device.device_path.find(willRemoveDevice.get_path()) != -1:
    # If get_path() returns a substring of udev path? Or vice versa?
    # Usually HIDAPI path is /dev/hidrawX or libusb path.
    # Udev path is /sys/devices/...
    # The code seems to assume some relationship. 
    # Let's just mock it so the find returns != -1
    mock_udev_device.device_path = 'some/path/1-1:1.0' 
    
    monitor_instance.poll.side_effect = [mock_udev_device, None]
    
    manager.listen()
    
    # Verify device was removed
    assert len(manager.streamdocks) == 0


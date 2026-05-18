"""
Unit tests for HardwareInterface and USBHardware implementation.

Tests the wrapper around HIDTransport, verifying format conversion,
error handling, and design contract compliance.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from StreamDock.infrastructure.hardware_interface import HardwareInterface, DeviceInfo, InputEvent
from StreamDock.infrastructure.usb_hardware import USBHardware


class TestDeviceInfo:
    """Tests for DeviceInfo dataclass."""
    
    def test_device_id_generation(self):
        """Design contract: device_id is stable identifier from VID:PID:Serial."""
        device = DeviceInfo(
            vendor_id=0x1234,
            product_id=0x5678,
            serial_number='ABC123',
            path='/dev/hidraw0'
        )
        
        assert device.device_id == '1234:5678:ABC123'
    
    def test_device_info_with_optional_fields(self):
        """Edge case: DeviceInfo works with only required fields."""
        device = DeviceInfo(
            vendor_id=0x1234,
            product_id=0x5678,
            serial_number='TEST',
            path='/dev/hidraw0'
        )
        
        assert device.manufacturer == ""
        assert device.product == ""


class TestInputEvent:
    """Tests for InputEvent dataclass."""
    
    def test_input_event_creation(self):
        """Design contract: InputEvent captures button press with timestamp."""
        event = InputEvent(button_index=5, event_type='press')
        
        assert event.button_index == 5
        assert event.event_type == 'press'
        assert event.timestamp > 0


class TestUSBHardware:
    """Tests for USBHardware implementation."""
    
    @pytest.fixture
    def mock_transport(self):
        """Mock HIDTransport for testing."""
        transport = Mock()
        # Set default return values
        transport.enumerate.return_value = []
        transport.open.return_value = -1
        transport.close.return_value = None
        transport.set_brightness.return_value = -1
        transport.set_key_img.return_value = -1
        transport.read_.return_value = None
        return transport
    
    @pytest.fixture
    def usb_hardware(self, mock_transport):
        """USBHardware instance with mocked transport."""
        hardware = USBHardware()
        hardware._transport = mock_transport
        return hardware
    
    # ==================== Enumeration Tests ====================
    
    def test_enumerate_devices_converts_format_correctly(self, usb_hardware, mock_transport):
        """Design contract: enumerate returns List[DeviceInfo] with correct format."""
        mock_transport.enumerate.return_value = [
            {
                'vendor_id': 0x1234,
                'product_id': 0x5678,
                'serial_number': 'ABC123',
                'path': b'/dev/hidraw0',
                'manufacturer_string': 'TestManufacturer',
                'product_string': 'TestProduct'
            }
        ]
        
        devices = usb_hardware.enumerate_devices(0x1234, 0x5678)
        
        assert len(devices) == 1
        assert devices[0].vendor_id == 0x1234
        assert devices[0].product_id == 0x5678
        assert devices[0].serial_number == 'ABC123'
        assert devices[0].path == '/dev/hidraw0'  # Converted from bytes
        assert devices[0].manufacturer == 'TestManufacturer'
        assert devices[0].product == 'TestProduct'
    
    def test_enumerate_devices_empty_list_when_none_found(self, usb_hardware, mock_transport):
        """Design contract: Returns empty list when no devices found."""
        mock_transport.enumerate.return_value = []
        
        devices = usb_hardware.enumerate_devices(0xFFFF, 0xFFFF)
        
        assert devices == []
    
    def test_enumerate_devices_handles_missing_serial_number(self, usb_hardware, mock_transport):
        """Edge case: Handles devices with None serial number."""
        mock_transport.enumerate.return_value = [
            {
                'vendor_id': 0x1234,
                'product_id': 0x5678,
                'serial_number': None,  # Missing serial
                'path': b'/dev/hidraw0'
            }
        ]
        
        devices = usb_hardware.enumerate_devices(0x1234, 0x5678)
        
        assert len(devices) == 1
        assert devices[0].serial_number == ''  # Converted to empty string
    
    def test_enumerate_devices_handles_string_path(self, usb_hardware, mock_transport):
        """Edge case: Handles path already as string."""
        mock_transport.enumerate.return_value = [
            {
                'vendor_id': 0x1234,
                'product_id': 0x5678,
                'serial_number': 'TEST',
                'path': '/dev/hidraw0'  # Already a string
            }
        ]
        
        devices = usb_hardware.enumerate_devices(0x1234, 0x5678)
        
        assert devices[0].path == '/dev/hidraw0'
    
    def test_enumerate_devices_handles_exception(self, usb_hardware, mock_transport):
        """Error handling: Returns empty list on exception."""
        mock_transport.enumerate.side_effect = Exception("USB error")
        
        devices = usb_hardware.enumerate_devices(0x1234, 0x5678)
        
        assert devices == []
    
    # ==================== Device Operations Tests ====================
    
    def test_open_device_success(self, usb_hardware, mock_transport):
        """Design contract: open_device returns True on success."""
        mock_transport.open.return_value = 1  # Success
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        
        result = usb_hardware.open_device(device)
        
        assert result is True
        assert usb_hardware.is_connected() is True
        mock_transport.open.assert_called_once()
    
    def test_open_device_failure_returns_false(self, usb_hardware, mock_transport):
        """Design contract: open_device returns False on failure."""
        mock_transport.open.return_value = -1  # Failure
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        
        result = usb_hardware.open_device(device)
        
        assert result is False
        assert usb_hardware.is_connected() is False
    
    def test_open_device_converts_string_path_to_bytes(self, usb_hardware, mock_transport):
        """Implementation detail: Converts string path to bytes for HIDTransport."""
        mock_transport.open.return_value = 1
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        
        usb_hardware.open_device(device)
        
        # Verify path was converted to bytes
        call_args = mock_transport.open.call_args[0]
        assert isinstance(call_args[0], bytes)
        assert call_args[0] == b'/dev/hidraw0'
    
    def test_open_device_closes_existing_device_first(self, usb_hardware, mock_transport):
        """Design contract: Opening new device closes existing one."""
        mock_transport.open.return_value = 1
        device1 = DeviceInfo(0x1234, 0x5678, 'TEST1', '/dev/hidraw0')
        device2 = DeviceInfo(0x1234, 0x5678, 'TEST2', '/dev/hidraw1')
        
        usb_hardware.open_device(device1)
        assert usb_hardware._current_device == device1
        
        usb_hardware.open_device(device2)
        
        # close() should have been called
        assert mock_transport.close.called
        assert usb_hardware._current_device == device2
    
    def test_close_device_clears_current_device(self, usb_hardware, mock_transport):
        """Design contract: close_device clears device state."""
        mock_transport.open.return_value = 1
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        usb_hardware.open_device(device)
        
        usb_hardware.close_device()
        
        assert usb_hardware._current_device is None
        assert usb_hardware.is_connected() is False
        mock_transport.close.assert_called_once()
    
    def test_close_device_safe_when_no_device_open(self, usb_hardware, mock_transport):
        """Design contract: Safe to call close when no device is open."""
        usb_hardware.close_device()  # Should not raise
        
        assert usb_hardware.is_connected() is False
    
    def test_is_connected_true_when_device_open(self, usb_hardware, mock_transport):
        """Design contract: is_connected returns True when device is open."""
        mock_transport.open.return_value = 1
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        usb_hardware.open_device(device)
        
        assert usb_hardware.is_connected() is True
    
    def test_is_connected_false_when_no_device(self, usb_hardware):
        """Design contract: is_connected returns False when no device."""
        assert usb_hardware.is_connected() is False
    
    # ==================== Brightness Tests ====================
    
    def test_set_brightness_clamps_to_0_100(self, usb_hardware, mock_transport):
        """Design contract: Brightness values clamped to 0-100 range."""
        mock_transport.open.return_value = 1
        mock_transport.set_brightness.return_value = 1
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        usb_hardware.open_device(device)
        
        # Test upper bound
        usb_hardware.set_brightness(150)
        assert mock_transport.set_brightness.call_args[0][0] == 100
        
        # Test lower bound
        usb_hardware.set_brightness(-10)
        assert mock_transport.set_brightness.call_args[0][0] == 0
    
    def test_set_brightness_delegates_to_transport(self, usb_hardware, mock_transport):
        """Design contract: Brightness change delegated to HIDTransport."""
        mock_transport.open.return_value = 1
        mock_transport.set_brightness.return_value = 1
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        usb_hardware.open_device(device)
        
        result = usb_hardware.set_brightness(75)
        
        assert result is True
        mock_transport.set_brightness.assert_called_with(75)
    
    def test_set_brightness_returns_false_when_no_device(self, usb_hardware):
        """Design contract: Returns False when no device is open."""
        result = usb_hardware.set_brightness(50)
        
        assert result is False
    
    # ==================== Input Reading Tests ====================
    
    def test_read_input_returns_event_on_button_press(self, usb_hardware, mock_transport):
        """Design contract: Converts HIDTransport data to InputEvent."""
        mock_transport.open.return_value = 1
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        usb_hardware.open_device(device)
        
        # HIDTransport.read_() returns: (raw_bytes, ack, ok, key, status)
        mock_transport.read_.return_value = (b'data', True, True, 5, 0)
        
        event = usb_hardware.read_input(timeout_ms=100)
        
        assert event is not None
        assert event.button_index == 5
        assert event.event_type == 'press'
    
    def test_read_input_returns_none_on_timeout(self, usb_hardware, mock_transport):
        """Design contract: Returns None on timeout (not an error)."""
        mock_transport.open.return_value = 1
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        usb_hardware.open_device(device)
        
        mock_transport.read_.return_value = None  # Timeout
        
        event = usb_hardware.read_input(timeout_ms=100)
        
        assert event is None
    
    def test_read_input_timeout_parameter_passed_correctly(self, usb_hardware, mock_transport):
        """Implementation: Timeout parameter passed to HIDTransport."""
        mock_transport.open.return_value = 1
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        usb_hardware.open_device(device)
        
        usb_hardware.read_input(timeout_ms=500)
        
        # Verify timeout was passed
        call_args = mock_transport.read_.call_args[0]
        assert call_args[1] == 500  # timeout_ms parameter
    
    def test_read_input_returns_none_when_no_device(self, usb_hardware):
        """Design contract: Returns None when no device is open."""
        event = usb_hardware.read_input()
        
        assert event is None
    
    # ==================== Image Tests ====================
    
    def test_send_image_delegates_to_transport(self, usb_hardware, mock_transport):
        """Design contract: Image sending delegated to HIDTransport."""
        mock_transport.open.return_value = 1
        mock_transport.set_key_img.return_value = 1
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        usb_hardware.open_device(device)
        
        image_data = b'fake_image_data'
        result = usb_hardware.send_image(image_data, button_index=3)
        
        assert result is True
        mock_transport.set_key_img.assert_called_once_with(image_data, len(image_data), 3)
    
    def test_send_image_returns_false_when_no_device(self, usb_hardware):
        """Design contract: Returns False when no device is open."""
        result = usb_hardware.send_image(b'data', button_index=0)
        
        assert result is False
    
    def test_send_image_handles_transport_failure(self, usb_hardware, mock_transport):
        """Error handling: Returns False on transport failure."""
        mock_transport.open.return_value = 1
        mock_transport.set_key_img.return_value = -1  # Failure
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        usb_hardware.open_device(device)
        
        result = usb_hardware.send_image(b'data', button_index=0)
        
        assert result is False
    
    # ==================== Additional Edge Cases ====================
    
    def test_open_device_handles_exception(self, usb_hardware, mock_transport):
        """Error handling: Returns False on exception during open."""
        mock_transport.open.side_effect = Exception("USB error")
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        
        result = usb_hardware.open_device(device)
        
        assert result is False
        assert usb_hardware.is_connected() is False
    
    def test_close_device_handles_exception(self, usb_hardware, mock_transport):
        """Error handling: Clears device even if close raises exception."""
        mock_transport.open.return_value = 1
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        usb_hardware.open_device(device)
        
        mock_transport.close.side_effect = Exception("Close error")
        
        usb_hardware.close_device()
        
        # Even with exception, device should be cleared
        assert usb_hardware._current_device is None
    
    def test_set_brightness_handles_exception(self, usb_hardware, mock_transport):
        """Error handling: Returns False on exception."""
        mock_transport.open.return_value = 1
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        usb_hardware.open_device(device)
        
        mock_transport.set_brightness.side_effect = Exception("Brightness error")
        
        result = usb_hardware.set_brightness(50)
        
        assert result is False
    
    def test_read_input_handles_exception(self, usb_hardware, mock_transport):
        """Error handling: Returns None on exception."""
        mock_transport.open.return_value = 1
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        usb_hardware.open_device(device)
        
        mock_transport.read_.side_effect = Exception("Read error")
        
        event = usb_hardware.read_input()
        
        assert event is None
    
    def test_send_image_handles_exception(self, usb_hardware, mock_transport):
        """Error handling: Returns False on exception."""
        mock_transport.open.return_value = 1
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        usb_hardware.open_device(device)
        
        mock_transport.set_key_img.side_effect = Exception("Image error")
        
        result = usb_hardware.send_image(b'data', button_index=0)
        
        assert result is False
    
    def test_read_input_handles_invalid_key_index(self, usb_hardware, mock_transport):
        """Edge case: Negative key index means no button press."""
        mock_transport.open.return_value = 1
        device = DeviceInfo(0x1234, 0x5678, 'TEST', '/dev/hidraw0')
        usb_hardware.open_device(device)
        
        # Negative key means no press
        mock_transport.read_.return_value = (b'data', True, True, -1, 0)
        
        event = usb_hardware.read_input()
        
        assert event is None


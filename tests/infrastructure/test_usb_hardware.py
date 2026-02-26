"""
Tests for USBHardware adapter.
"""

import pytest
from unittest.mock import Mock, patch
from StreamDock.infrastructure.usb_hardware import USBHardware
from StreamDock.infrastructure.hardware_interface import DeviceInfo


class TestUSBHardware:
    """Tests for USBHardware connection tracking and adapter logic."""

    @pytest.fixture
    def mock_hid_transport(self):
        """Mock the underlying HIDTransport."""
        with patch('StreamDock.infrastructure.usb_hardware.HIDTransport') as mock_class:
            mock_instance = Mock()
            mock_instance.open.return_value = 1
            mock_instance.set_brightness.return_value = 1
            mock_class.return_value = mock_instance
            yield mock_instance

    def test_legacy_open_tracks_state(self, mock_hid_transport):
        """CRITICAL: Test that calling legacy open directly populates _current_device."""
        hardware = USBHardware()
        
        # Initially not connected
        assert not hardware.is_connected()
        
        # Call legacy open format
        result = hardware.open("/dev/hidraw0")
        
        # Check result and state
        assert result == 1
        assert hardware.is_connected() is True
        assert hardware._current_device is not None
        assert hardware._current_device.path == "/dev/hidraw0"
        
        # Check transport called correctly
        mock_hid_transport.open.assert_called_once_with(b"/dev/hidraw0")

    def test_legacy_close_clears_state(self, mock_hid_transport):
        """CRITICAL: Test that calling legacy close clears _current_device."""
        hardware = USBHardware()
        
        # Setup connected state
        hardware.open("/dev/hidraw0")
        assert hardware.is_connected() is True
        
        # Call close
        hardware.close()
        
        # Check state cleared
        assert not hardware.is_connected()
        assert hardware._current_device is None
        mock_hid_transport.close.assert_called_once()

    def test_open_device_tracks_state(self, mock_hid_transport):
        """Test Interface-compliant open_device populates state."""
        hardware = USBHardware()
        device_info = DeviceInfo(1, 2, "serial", "/dev/hidraw0")
        
        success = hardware.open_device(device_info)
        
        assert success is True
        assert hardware.is_connected() is True
        assert hardware._current_device == device_info

    def test_close_device_clears_state(self, mock_hid_transport):
        """Test Interface-compliant close_device clears state."""
        hardware = USBHardware()
        device_info = DeviceInfo(1, 2, "serial", "/dev/hidraw0")
        
        hardware.open_device(device_info)
        hardware.close_device()
        
        assert not hardware.is_connected()
        assert hardware._current_device is None

    def test_hardware_actions_aborted_when_disconnected(self, mock_hid_transport):
        """CRITICAL: Action methods must check is_connected() and gracefully abort."""
        hardware = USBHardware()
        
        # Do not open device
        assert not hardware.is_connected()
        
        # Attempt brightness set
        result = hardware.set_brightness(50)
        
        # Action aborted
        assert result is False
        mock_hid_transport.set_brightness.assert_not_called()

"""
Unit tests for DeviceRegistry.

Tests path-independent device tracking, auto-reconnection, and registry management.
"""

import pytest
from unittest.mock import Mock, MagicMock, call
import time

from StreamDock.infrastructure.device_registry import DeviceRegistry, TrackedDevice
from StreamDock.infrastructure.hardware_interface import HardwareInterface, DeviceInfo


class TestTrackedDevice:
    """Tests for TrackedDevice dataclass."""
    
    def test_tracked_device_creation(self):
        """Design contract: TrackedDevice stores device info and instance."""
        device_info = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        device_instance = Mock()
        
        tracked = TrackedDevice(
            device_info=device_info,
            device_instance=device_instance
        )
        
        assert tracked.device_info == device_info
        assert tracked.device_instance == device_instance
        assert tracked.is_connected is True
        assert tracked.last_seen > 0


class TestDeviceRegistry:
    """Tests for DeviceRegistry."""
    
    @pytest.fixture
    def mock_hardware(self):
        """Mock hardware interface."""
        return Mock(spec=HardwareInterface)
    
    @pytest.fixture
    def registry(self, mock_hardware):
        """DeviceRegistry instance."""
        return DeviceRegistry(mock_hardware)
    
    @pytest.fixture
    def mock_device_class(self):
        """Mock device class for instantiation."""
        mock_class = Mock()
        mock_class.return_value = Mock()  # Instance
        return mock_class
    
    # ==================== Registration Tests ====================
    
    def test_enumerate_and_register_new_device(self, registry, mock_hardware, mock_device_class):
        """Design contract: New devices are registered."""
        device_info = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        mock_hardware.enumerate_devices.return_value = [device_info]
        
        devices = registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        
        assert len(devices) == 1
        assert registry.get_device_count() == 1
        mock_device_class.assert_called_once_with(mock_hardware, device_info)
    
    def test_enumerate_and_register_multiple_devices(self, registry, mock_hardware, mock_device_class):
        """Design contract: Multiple devices can be registered."""
        device1 = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        device2 = DeviceInfo(0x1234, 0x5678, 'DEF456', '/dev/hidraw1')
        mock_hardware.enumerate_devices.return_value = [device1, device2]
        
        devices = registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        
        assert len(devices) == 2
        assert registry.get_device_count() == 2
    
    def test_enumerate_empty_list(self, registry, mock_hardware, mock_device_class):
        """Edge case: Empty enumeration returns empty list."""
        mock_hardware.enumerate_devices.return_value = []
        
        devices = registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        
        assert len(devices) == 0
        assert registry.get_device_count() == 0
    
    # ==================== Retrieval Tests ====================
    
    def test_get_device_by_id(self, registry, mock_hardware, mock_device_class):
        """Design contract: Devices retrievable by stable ID."""
        device_info = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        mock_hardware.enumerate_devices.return_value = [device_info]
        
        devices = registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        
        retrieved = registry.get_device('1234:5678:ABC123')
        assert retrieved == devices[0]
    
    def test_get_device_not_found(self, registry):
        """Design contract: Returns None for unknown device ID."""
        result = registry.get_device('unknown:id:here')
        
        assert result is None
    
    def test_get_all_devices(self, registry, mock_hardware, mock_device_class):
        """Design contract: Can retrieve all registered devices."""
        device1 = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        device2 = DeviceInfo(0x1234, 0x5678, 'DEF456', '/dev/hidraw1')
        mock_hardware.enumerate_devices.return_value = [device1, device2]
        
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        all_devices = registry.get_all_devices()
        
        assert len(all_devices) == 2
    
    def test_get_connected_devices(self, registry, mock_hardware, mock_device_class):
        """Design contract: Can get only connected devices."""
        device1 = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        device2 = DeviceInfo(0x1234, 0x5678, 'DEF456', '/dev/hidraw1')
        mock_hardware.enumerate_devices.return_value = [device1, device2]
        
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        registry.mark_disconnected('1234:5678:ABC123')
        
        connected = registry.get_connected_devices()
        assert len(connected) == 1  # Only DEF456 connected
    
    # ==================== Reconnection Tests (CRITICAL) ====================
    
    def test_reconnect_device_at_new_path(self, registry, mock_hardware, mock_device_class):
        """CRITICAL: Device reconnects when USB path changes."""
        # First enumeration at /dev/hidraw0
        device1 = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        mock_hardware.enumerate_devices.return_value = [device1]
        mock_hardware.open_device.return_value = True
        
        devices1 = registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        initial_instance = devices1[0]
        
        # Second enumeration at /dev/hidraw1 (NEW PATH, same serial)
        device2 = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw1')
        mock_hardware.enumerate_devices.return_value = [device2]
        
        devices2 = registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        
        # Should return SAME instance (not create new one)
        assert len(devices2) == 1
        assert devices2[0] is initial_instance
        assert registry.get_device_count() == 1  # Still only ONE device
        
        # Path should be updated
        tracked = registry._devices['1234:5678:ABC123']
        assert tracked.device_info.path == '/dev/hidraw1'
        
        # Device should have been reopened
        mock_hardware.open_device.assert_called()
    
    def test_reconnect_updates_device_info(self, registry, mock_hardware, mock_device_class):
        """Design contract: Reconnection updates DeviceInfo."""
        device1 = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        mock_hardware.enumerate_devices.return_value = [device1]
        mock_hardware.open_device.return_value = True
        
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        
        # Reconnect with new info
        device2 = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw5', 
                            manufacturer='NewManuf', product='NewProd')
        mock_hardware.enumerate_devices.return_value = [device2]
        
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        
        tracked = registry._devices['1234:5678:ABC123']
        assert tracked.device_info.manufacturer == 'NewManuf'
        assert tracked.device_info.product == 'NewProd'
    
    def test_reconnect_reopens_device(self, registry, mock_hardware, mock_device_class):
        """Design contract: Reconnection calls open_device."""
        device1 = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        mock_hardware.enumerate_devices.return_value = [device1]
        mock_hardware.open_device.return_value = True
        
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        mock_hardware.open_device.reset_mock()
        
        # Reconnect at new path
        device2 = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw1')
        mock_hardware.enumerate_devices.return_value = [device2]
        
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        
        # Verify device was reopened
        mock_hardware.open_device.assert_called_once_with(device2)
    
    def test_reconnect_same_path_no_reopen(self, registry, mock_hardware, mock_device_class):
        """Optimization: Same path doesn't trigger reopen."""
        device = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        mock_hardware.enumerate_devices.return_value = [device]
        
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        mock_hardware.open_device.reset_mock()
        
        # Enumerate again with same path
        mock_hardware.enumerate_devices.return_value = [device]
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        
        # Should NOT reopen (same path)
        mock_hardware.open_device.assert_not_called()
    
    def test_device_remains_in_registry_after_disconnect(self, registry, mock_hardware, mock_device_class):
        """Design contract: Disconnected devices remain in registry."""
        device = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        mock_hardware.enumerate_devices.return_value = [device]
        
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        registry.mark_disconnected('1234:5678:ABC123')
        
        # Still in registry
        assert registry.get_device_count() == 1
        assert registry.get_device('1234:5678:ABC123') is not None
        assert not registry.is_device_connected('1234:5678:ABC123')
    
    def test_reconnect_after_marked_disconnected(self, registry, mock_hardware, mock_device_class):
        """Design contract: Marked-disconnected devices auto-reconnect."""
        device = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        mock_hardware.enumerate_devices.return_value = [device]
        mock_hardware.open_device.return_value = True
        
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        registry.mark_disconnected('1234:5678:ABC123')
        
        # Enumerate again (device reappeared)
        mock_hardware.enumerate_devices.return_value = [device]
        mock_hardware.open_device.reset_mock()
        
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        
        # Should reconnect
        assert registry.is_device_connected('1234:5678:ABC123')
        mock_hardware.open_device.assert_called_once()
    
    # ==================== Disconnection Tests ====================
    
    def test_mark_disconnected_keeps_device_in_registry(self, registry, mock_hardware, mock_device_class):
        """Design contract: Soft disconnect keeps device registered."""
        device = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        mock_hardware.enumerate_devices.return_value = [device]
        
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        registry.mark_disconnected('1234:5678:ABC123')
        
        assert registry.get_device_count() == 1
        assert not registry.is_device_connected('1234:5678:ABC123')
    
    def test_mark_disconnected_unknown_device(self, registry):
        """Error handling: Marking unknown device as disconnected is safe."""
        registry.mark_disconnected('unknown:device:id')  # Should not raise
    
    def test_remove_device_deletes_from_registry(self, registry, mock_hardware, mock_device_class):
        """Design contract: Remove permanently deletes device."""
        device = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        mock_hardware.enumerate_devices.return_value = [device]
        
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        registry.remove_device('1234:5678:ABC123')
        
        assert registry.get_device_count() == 0
        assert registry.get_device('1234:5678:ABC123') is None
    
    def test_remove_device_unknown(self, registry):
        """Error handling: Removing unknown device is safe."""
        registry.remove_device('unknown:device:id')  # Should not raise
    
    # ==================== Edge Cases ====================
    
    def test_device_creation_failure_handled(self, registry, mock_hardware, mock_device_class):
        """Error handling: Device creation failure is logged but doesn't crash."""
        device = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        mock_hardware.enumerate_devices.return_value = [device]
        mock_device_class.side_effect = Exception("Creation failed")
        
        devices = registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        
        # Should return empty list, not crash
        assert devices == []
        assert registry.get_device_count() == 0
    
    def test_reopen_failure_marks_disconnected(self, registry, mock_hardware, mock_device_class):
        """Error handling: Reopen failure marks device as disconnected."""
        device1 = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        mock_hardware.enumerate_devices.return_value = [device1]
        mock_hardware.open_device.return_value = True
        
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        
        # Reconnect with open failure
        device2 = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw1')
        mock_hardware.enumerate_devices.return_value = [device2]
        mock_hardware.open_device.return_value = False  # FAIL
        
        registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        
        # Device should be marked disconnected
        assert not registry.is_device_connected('1234:5678:ABC123')
    
    def test_is_device_connected_false_for_unknown(self, registry):
        """Design contract: Unknown devices report as not connected."""
        assert not registry.is_device_connected('unknown:device:id')
    
    def test_duplicate_serial_numbers_handled(self, registry, mock_hardware, mock_device_class):
        """Edge case: Devices with same serial are treated as same device."""
        device1 = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw0')
        device2 = DeviceInfo(0x1234, 0x5678, 'ABC123', '/dev/hidraw1')
        mock_hardware.enumerate_devices.return_value = [device1, device2]
        mock_hardware.open_device.return_value = True
        
        devices = registry.enumerate_and_register(0x1234, 0x5678, mock_device_class)
        
        # Returns list with same instance twice (both results point to same device)
        assert len(devices) == 2
        assert devices[0] is devices[1]  # Same instance
        assert registry.get_device_count() == 1  # Only one in registry

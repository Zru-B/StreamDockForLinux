import pytest
import sys
from unittest.mock import MagicMock, patch

# Mock dbus before importing LockMonitor to avoid import error
sys.modules["dbus"] = MagicMock()
sys.modules["dbus.mainloop.glib"] = MagicMock()
# Also mock gi.repository
module = MagicMock()
sys.modules["gi"] = module
sys.modules["gi.repository"] = module

from StreamDock.LockMonitor import LockMonitor

class TestLockMonitor:

    @pytest.fixture
    def lock_monitor(self, mock_device):
        # We need to mock the import of dbus inside the class check
        with patch.dict('sys.modules', {'dbus': MagicMock(), 'gi.repository': MagicMock()}):
            monitor = LockMonitor(mock_device, enabled=True)
            return monitor

    def test_initialization(self, lock_monitor):
        assert lock_monitor.enabled == True
        assert lock_monitor.dbus_available == True # Since we mocked it
        
    def test_lock_event(self, lock_monitor, mock_device):
        """Test reaction to lock event."""
        # Simulate lock
        lock_monitor._on_lock_state_changed(True)
        
        assert lock_monitor.is_locked == True
        mock_device.clearAllIcon.assert_called_once()
        mock_device.close.assert_called_once()
        
    def test_unlock_event(self, lock_monitor, mock_device):
        """Test reaction to unlock event."""
        # First lock it
        lock_monitor.is_locked = True
        lock_monitor._last_state_change = 0 # reset debounce
        
        # Setup mocks for re-enumeration
        lock_monitor.device_transport.enumerate.return_value = [
            {"path": b"mock_path", "vendor_id": 0x1234, "product_id": 0x5678}
        ]
        
        # We need to mock the device class instantiation
        MockDeviceClass = MagicMock()
        MockDeviceClass.return_value = mock_device # Return same mock for simplicity
        lock_monitor.device_class = MockDeviceClass
        
        # Simulate unlock
        lock_monitor._on_lock_state_changed(False)
        
        assert lock_monitor.is_locked == False
        
        # Should have tried to re-create device
        MockDeviceClass.assert_called()
        mock_device.open.assert_called()
        mock_device.init.assert_called()

    def test_debounce_logic(self, lock_monitor, mock_device):
        """Test that rapid state changes are ignored."""
        import time
        
        lock_monitor._last_state_change = time.time()
        
        # Try to lock
        lock_monitor._on_lock_state_changed(True)
        
        # Should be ignored (still False)
        assert lock_monitor.is_locked == False
        mock_device.close.assert_not_called()

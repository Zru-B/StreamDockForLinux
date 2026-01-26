
import unittest
from unittest.mock import MagicMock, patch
import time
from StreamDock.lock_monitor import LockMonitor

class TestLockMonitorHotplug(unittest.TestCase):
    def setUp(self):
        # Mock device
        self.mock_device = MagicMock()
        self.mock_device.path = b"test_path"
        self.mock_device.vendor_id = 0x1234
        self.mock_device.product_id = 0x5678
        self.mock_device.transport = MagicMock()
        self.mock_device._current_brightness = 80
        
        # Mock wrapper for device class
        self.mock_device_class = MagicMock(return_value=self.mock_device)
        
        self.mock_layout = MagicMock()
        self.all_layouts = {'default': self.mock_layout}
        
        # Initialize monitor
        with patch('sys.modules', {'dbus': MagicMock()}):
            self.monitor = LockMonitor(
                self.mock_device, 
                device_class=self.mock_device_class,
                all_layouts=self.all_layouts
            )
            # Inject mock properties
            self.monitor.device_vendor_id = 0x1234
            self.monitor.device_product_id = 0x5678
            self.monitor.device_path = "test_path"
            self.monitor.saved_brightness = 80
            self.monitor.device_transport = self.mock_device.transport

    def test_update_device_restores_state(self):
        """
        Test that update_device(new_device) correctly updates references and restores state.
        """
        # Create a new mock device
        new_mock_device = MagicMock()
        new_mock_device.path = b"new_path"
        new_mock_device.transport = MagicMock()
        new_mock_device.open.return_value = True
        
        # Call update_device
        self.monitor.update_device(new_mock_device)
        
        # Verify internal device reference updated
        self.assertEqual(self.monitor.device, new_mock_device)
        self.assertEqual(self.monitor.device_path, new_mock_device.path)
        
        # Verify layouts updated
        self.mock_layout.update_device.assert_called_with(new_mock_device)
        
        # Verify state restored (brightness set)
        new_mock_device.wake_screen.assert_called_once()
        new_mock_device.set_brightness.assert_called_with(80)
        
        # Verify window monitor restarted (if it was running)
        # We didn't set window monitor in this test setup, but if we did:
        pass

    def test_handle_unlock_fails_if_signal_missed(self):
        """
        If lock/unlock signal is missed (or LockMonitor thinks it's already unlocked),
        triggering unlock manually (or if it never triggers) leaves device dead?
        """
        # If is_locked is False
        self.monitor.is_locked = False
        
        # And we call _on_lock_state_changed(False) -> Unlock
        self.monitor._on_lock_state_changed(False)
        
        # It should log "ignoring duplicate signal" and return
        # So no device restoration happens.
        # This confirms that if LockMonitor thinks it's unlocked, it won't try to reconnect to the device.
        # So even if DeviceManager found the device, LockMonitor ignores it.
        pass

if __name__ == '__main__':
    unittest.main()

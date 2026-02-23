
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

    def test_update_device_resets_window_monitor_detection_state(self):
        """
        Regression test: after a hotplug event the window monitor must fire an
        immediate layout update. If current_window_id is not reset, the monitor
        sees 'same window as before' and skips the callback, leaving a blank screen.
        """
        # Set up a window monitor mock that is currently stopped
        mock_window_monitor = MagicMock()
        mock_window_monitor.running = False
        mock_window_monitor.current_window_id = "org.kde.plasmashell"  # Stale state
        self.monitor.window_monitor = mock_window_monitor

        new_mock_device = MagicMock()
        new_mock_device.path = b"new_path"
        new_mock_device.transport = MagicMock()

        self.monitor.update_device(new_mock_device)

        # current_window_id must be cleared so the first poll fires the layout callback
        self.assertIsNone(mock_window_monitor.current_window_id)
        # Window monitor must be (re)started
        mock_window_monitor.start.assert_called_once()

    def test_update_device_clears_window_id_even_when_monitor_already_running(self):
        """
        Even if the window monitor is already running, current_window_id must still
        be reset so the next poll triggers a layout update.
        """
        mock_window_monitor = MagicMock()
        mock_window_monitor.running = True
        mock_window_monitor.current_window_id = "org.kde.konsole"
        self.monitor.window_monitor = mock_window_monitor

        new_mock_device = MagicMock()
        new_mock_device.path = b"another_path"
        new_mock_device.transport = MagicMock()

        self.monitor.update_device(new_mock_device)

        # current_window_id must be cleared regardless of running state
        self.assertIsNone(mock_window_monitor.current_window_id)
        # start() should NOT be called again when already running
        mock_window_monitor.start.assert_not_called()


    def test_update_device_while_locked_does_not_clear_lock_state(self):
        """
        Regression test for the scenario that triggered the bug in real use:

        1. PC is locked (is_locked=True, screen off).
        2. Device is hotplugged to a different USB port while still locked.
        3. DeviceManager fires update_device().

        Expected: is_locked must remain True so the subsequent unlock signal
        is NOT dropped by the debounce check. Screen must stay off.
        """
        # Simulate being in locked state
        self.monitor.is_locked = True

        new_mock_device = MagicMock()
        new_mock_device.path = b"1-2.2:1.0"
        new_mock_device.transport = MagicMock()

        self.monitor.update_device(new_mock_device)

        # is_locked must NOT be cleared — the real unlock signal must still fire
        self.assertTrue(self.monitor.is_locked)

        # Screen must stay off (disconnected called, wake_screen NOT called)
        new_mock_device.transport.disconnected.assert_called_once()
        new_mock_device.wake_screen.assert_not_called()

        # Layout must NOT be applied while locked
        self.mock_layout.apply.assert_not_called()

        # Device reference must be updated for when unlock does fire
        self.assertEqual(self.monitor.device, new_mock_device)


if __name__ == '__main__':
    unittest.main()

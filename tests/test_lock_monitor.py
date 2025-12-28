import unittest
from unittest.mock import MagicMock, patch, call
import sys
import threading
import time

# Mock dbus before importing LockMonitor if possible, or patch it during setup
# Since LockMonitor imports dbus at module level inside __init__ (wait, no, inside __init__ try-except)
# We can just patch sys.modules or use patch.dict.

from StreamDock.lock_monitor import LockMonitor

class TestLockMonitor(unittest.TestCase):

    def setUp(self):
        # Mock device
        self.mock_device = MagicMock()
        self.mock_device.path = b"test_path"
        self.mock_device.vendor_id = 0x1234
        self.mock_device.product_id = 0x5678
        self.mock_device.transport = MagicMock()
        self.mock_device._current_brightness = 80
        
        # Mock window monitor
        self.mock_window_monitor = MagicMock()
        self.mock_window_monitor.running = True

    def test_init_no_dbus(self):
        """Test initialization when dbus is not available."""
        with patch.dict(sys.modules, {'dbus': None}):
            # Force ImportError behavior by patching __import__ or just ensuring usage fails?
            # Actually LockMonitor tries `import dbus`.
            # If we remove 'dbus' from sys.modules and make it raise ImportError...
            
            with patch('builtins.__import__', side_effect=ImportError("No module named dbus")):
                monitor = LockMonitor(self.mock_device)
                self.assertFalse(monitor.dbus_available)
                self.assertFalse(monitor.enabled)

    def test_init_success(self):
        """Test successful initialization."""
        mock_dbus_module = MagicMock()
        with patch.dict(sys.modules, {'dbus': mock_dbus_module, 'dbus.mainloop.glib': MagicMock()}):
            monitor = LockMonitor(self.mock_device)
            self.assertTrue(monitor.dbus_available)
            self.assertTrue(monitor.enabled)
            self.assertEqual(monitor.device, self.mock_device)
            self.assertEqual(monitor.dbus, mock_dbus_module)

    @patch('StreamDock.lock_monitor.threading.Thread')
    def test_start_stop(self, mock_thread_cls):
        """Test starting and stopping the monitor."""
        # We need dbus to be available for start() to work
        mock_dbus_module = MagicMock()
        with patch.dict(sys.modules, {'dbus': mock_dbus_module, 'dbus.mainloop.glib': MagicMock()}):
            monitor = LockMonitor(self.mock_device)
            monitor.dbus_available = True
            
            # Start
            monitor.start()
            self.assertTrue(monitor.running)
            mock_thread_cls.assert_called_once()
            monitor.monitor_thread.start.assert_called_once()
            
            # Stop
            monitor.stop()
            self.assertFalse(monitor.running)
            monitor.monitor_thread.join.assert_called_once()

    @patch('StreamDock.lock_monitor.threading')
    def test_monitor_loop_connection_success(self, mock_threading):
        """Test connection to D-Bus services."""
        # Create monitor with mocked dbus module injected into it
        mock_dbus_module = MagicMock()
        mock_glib_module = MagicMock()
        mock_gi_repository = MagicMock()
        mock_gi_repository.GLib = mock_glib_module
        
        # We need to manually inject the dbus module into the monitor instance
        monitor = LockMonitor(self.mock_device)
        monitor.dbus = mock_dbus_module
        monitor.DBusGMainLoop = MagicMock() # Mock the instance attribute
        monitor.running = True
        monitor.dbus_available = True
        
        # Test the loop inside a patch for sys.modules
        with patch.dict(sys.modules, {'gi.repository': mock_gi_repository, 'gi.repository.GLib': mock_glib_module}):
            # Mock SessionBus and connection
            mock_bus = MagicMock()
            mock_dbus_module.SessionBus.return_value = mock_bus
            
            # Mock Loop to exit immediately
            mock_loop = MagicMock()
            mock_glib_module.MainLoop.return_value = mock_loop
            
            # Inject side effect to stop loop after one iteration
            mock_loop.get_context.return_value.iteration.side_effect = lambda x: setattr(monitor, 'running', False)
            
            monitor._monitor_loop()
            
            # Verify attempt to connect to KDE screensaver
            mock_bus.get_object.assert_any_call('org.freedesktop.ScreenSaver', '/ScreenSaver')
        
    @patch('StreamDock.lock_monitor.time.sleep', return_value=None)
    def test_on_lock_state_changed_lock(self, mock_sleep):
        """Test locking the computer."""
        monitor = LockMonitor(self.mock_device, window_monitor=self.mock_window_monitor)
        
        # Simulate lock
        monitor._on_lock_state_changed(True)
        
        self.assertTrue(monitor.is_locked)
        
        # Window monitor execution
        self.mock_window_monitor.stop.assert_called_once()
        
        # Device execution
        self.mock_device.clear_all_icons.assert_called_once()
        self.mock_device.close.assert_called_once()

    @patch('StreamDock.lock_monitor.time.sleep', return_value=None)
    def test_on_lock_state_changed_unlock(self, mock_sleep):
        """Test unlocking the computer."""
        monitor = LockMonitor(self.mock_device, window_monitor=self.mock_window_monitor)
        monitor.is_locked = True
        monitor._last_state_change = 0
        
        # Setup mock transport for re-enumeration
        mock_transport = self.mock_device.transport
        device_info_dict = {
            'path': self.mock_device.path,
            'vendor_id': self.mock_device.vendor_id,
            'product_id': self.mock_device.product_id
        }
        mock_transport.enumerate.return_value = [device_info_dict]
        
        # Setup device class to return a new mock device
        new_mock_device = MagicMock()
        
        # Need to patch the class used to create device
        # In reality monitor.device_class is set from device.__class__
        monitor.device_class = MagicMock(return_value=new_mock_device)
        
        # Simulate unlock
        monitor._on_lock_state_changed(False)
        
        self.assertFalse(monitor.is_locked)
        
        # Verify enumeration
        mock_transport.enumerate.assert_called()
        
        # Verify new device creation and init
        monitor.device_class.assert_called_with(mock_transport, device_info_dict)
        new_mock_device.open.assert_called_once()
        new_mock_device.init.assert_called_once()
        new_mock_device.set_brightness.assert_called_with(80) # restored brightness
        
        # Verify window monitor restart
        self.mock_window_monitor.start.assert_called_once()

    @patch('StreamDock.lock_monitor.time.sleep', return_value=None)
    def test_debounce(self, mock_sleep):
        """Test debouncing of events."""
        monitor = LockMonitor(self.mock_device)
        monitor._last_state_change = time.time()
        
        # Try to change state immediately
        monitor._on_lock_state_changed(True)
        
        # Should be ignored (no processing)
        self.assertFalse(monitor.is_locked)
        self.mock_device.close.assert_not_called()

if __name__ == '__main__':
    unittest.main()

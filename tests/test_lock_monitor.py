import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, call, patch

from StreamDock.lock_monitor import LockMonitor

# Mock dbus before importing LockMonitor if possible, or patch it during setup
# Since LockMonitor imports dbus at module level inside __init__ (wait, no, inside __init__ try-except)
# We can just patch sys.modules or use patch.dict.


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
        """Test locking schedules verification timer instead of immediate action."""
        monitor = LockMonitor(self.mock_device, window_monitor=self.mock_window_monitor)
        
        # Simulate lock signal
        monitor._on_lock_state_changed(True)
        
        # Lock should NOT be processed immediately - timer should be scheduled
        self.assertFalse(monitor.is_locked)  # Not yet locked
        self.assertIsNotNone(monitor._pending_lock_timer)  # Timer is scheduled
        
        # Device should NOT have been turned off yet
        self.mock_device.transport.disconnected.assert_not_called()
        self.mock_window_monitor.stop.assert_not_called()
        
        # Cancel timer to clean up
        monitor._pending_lock_timer.cancel()
    
    @patch('StreamDock.lock_monitor.time.sleep', return_value=None)
    def test_verify_and_handle_lock_confirmed(self, mock_sleep):
        """Test: Lock signal → verification confirms lock → screen turns off."""
        monitor = LockMonitor(self.mock_device, window_monitor=self.mock_window_monitor)
        
        # Mock GetActive to return True (locked)
        mock_interface = MagicMock()
        mock_interface.GetActive.return_value = True
        monitor._screensaver_interface = mock_interface
        
        # Directly call verification (simulating timer callback)
        monitor._verify_and_handle_lock()
        
        self.assertTrue(monitor.is_locked)
        
        # Window monitor should be stopped
        self.mock_window_monitor.stop.assert_called_once()
        
        # Transport should call disconnected to turn off screen
        self.mock_device.transport.disconnected.assert_called_once()
    
    @patch('StreamDock.lock_monitor.time.sleep', return_value=None)
    def test_verify_and_handle_lock_aborted(self, mock_sleep):
        """Test: Lock signal → verification shows NOT locked (aborted) → screen stays on."""
        monitor = LockMonitor(self.mock_device, window_monitor=self.mock_window_monitor)
        
        # Mock GetActive to return False (lock was aborted)
        mock_interface = MagicMock()
        mock_interface.GetActive.return_value = False
        monitor._screensaver_interface = mock_interface
        
        # Directly call verification (simulating timer callback)
        monitor._verify_and_handle_lock()
        
        self.assertFalse(monitor.is_locked)  # Never locked
        
        # Device should NOT have been turned off
        self.mock_device.transport.disconnected.assert_not_called()
        self.mock_window_monitor.stop.assert_not_called()
    
    @patch('StreamDock.lock_monitor.time.sleep', return_value=None)
    def test_unlock_cancels_pending_lock_verification(self, mock_sleep):
        """Test: Lock signal → unlock before verification → timer cancelled.
        
        When a lock signal fires and schedules verification, but an unlock signal
        arrives before verification completes, the timer should be cancelled.
        Since the lock was never confirmed (is_locked stayed False), no unlock
        processing should occur - we simply cancel the timer and return.
        """
        monitor = LockMonitor(self.mock_device, window_monitor=self.mock_window_monitor)
        
        # Simulate lock signal - schedules timer
        monitor._on_lock_state_changed(True)
        timer = monitor._pending_lock_timer
        self.assertIsNotNone(timer)
        self.assertFalse(monitor.is_locked)  # Lock not yet confirmed
        
        # Simulate quick unlock (user aborted lock)
        monitor._on_lock_state_changed(False)
        
        # Timer should be cancelled
        self.assertIsNone(monitor._pending_lock_timer)
        self.assertFalse(monitor.is_locked)  # Still not locked
        
        # Since we were never actually locked, unlock handler should NOT run
        # (no brightness restore, no window monitor restart)
        self.mock_device.transport.disconnected.assert_not_called()
        self.mock_window_monitor.stop.assert_not_called()
        self.mock_window_monitor.start.assert_not_called()
    
    @patch('StreamDock.lock_monitor.time.sleep', return_value=None)
    def test_verify_lock_dbus_failure_fallback(self, mock_sleep):
        """Test: Verification failure (D-Bus error) → fallback to assuming lock."""
        monitor = LockMonitor(self.mock_device, window_monitor=self.mock_window_monitor)
        
        # Mock GetActive to raise exception (D-Bus failure)
        mock_interface = MagicMock()
        mock_interface.GetActive.side_effect = Exception("D-Bus error")
        monitor._screensaver_interface = mock_interface
        
        # Should fallback to assuming locked (fail-safe)
        monitor._verify_and_handle_lock()
        
        self.assertTrue(monitor.is_locked)
        self.mock_device.transport.disconnected.assert_called_once()
    
    @patch('StreamDock.lock_monitor.time.sleep', return_value=None)
    def test_verify_lock_no_interface_fallback(self, mock_sleep):
        """Test: No screensaver interface available → fallback to assuming lock."""
        monitor = LockMonitor(self.mock_device, window_monitor=self.mock_window_monitor)
        monitor._screensaver_interface = None  # No interface available
        
        # Should fallback to assuming locked (fail-safe)
        monitor._verify_and_handle_lock()
        
        self.assertTrue(monitor.is_locked)
        self.mock_device.transport.disconnected.assert_called_once()
    
    @patch('StreamDock.lock_monitor.time.sleep', return_value=None)
    def test_multiple_lock_signals_reset_timer(self, mock_sleep):
        """Test: Multiple rapid lock signals handled correctly (timer reset)."""
        monitor = LockMonitor(self.mock_device, window_monitor=self.mock_window_monitor)
        
        # First lock signal
        monitor._on_lock_state_changed(True)
        first_timer = monitor._pending_lock_timer
        self.assertIsNotNone(first_timer)
        
        # Second lock signal - should cancel first timer and start new one
        monitor.is_locked = False  # Reset to allow second signal
        monitor._on_lock_state_changed(True)
        
        # First timer should have been cancelled
        self.assertIsNotNone(monitor._pending_lock_timer)
        
        # Clean up
        monitor._pending_lock_timer.cancel()

    @patch('StreamDock.lock_monitor.time.sleep', return_value=None)
    def test_unlock_with_valid_handle(self, mock_sleep):
        """Test unlocking when existing HID handle is still valid."""
        monitor = LockMonitor(self.mock_device, window_monitor=self.mock_window_monitor)
        monitor.is_locked = True
        monitor._last_state_change = 0
        monitor.saved_brightness = 80
        
        # Mock transport.set_brightness to return success (handle is valid)
        mock_transport = self.mock_device.transport
        mock_transport.set_brightness.return_value = 1
        
        # Simulate unlock
        monitor._on_lock_state_changed(False)
        
        self.assertFalse(monitor.is_locked)
        
        # Should use existing handle (no device recreation)
        mock_transport.set_brightness.assert_called_with(80)
        self.mock_window_monitor.start.assert_called_once()
    
    @patch('StreamDock.lock_monitor.time.sleep', return_value=None)
    def test_unlock_with_stale_handle_fallback(self, mock_sleep):
        """Test unlocking when existing HID handle is stale - should fallback to reopen."""
        monitor = LockMonitor(self.mock_device, window_monitor=self.mock_window_monitor)
        monitor.is_locked = True
        monitor._last_state_change = 0
        monitor.saved_brightness = 80
        
        # Mock transport.set_brightness to return failure (handle is stale)
        mock_transport = self.mock_device.transport
        mock_transport.set_brightness.return_value = -1
        
        # Setup for fallback reopen
        device_info_dict = {
            'path': self.mock_device.path,
            'vendor_id': self.mock_device.vendor_id,
            'product_id': self.mock_device.product_id
        }
        mock_transport.enumerate.return_value = [device_info_dict]
        
        new_mock_device = MagicMock()
        new_mock_device.open.return_value = True
        monitor.device_class = MagicMock(return_value=new_mock_device)
        
        # Simulate unlock
        monitor._on_lock_state_changed(False)
        
        self.assertFalse(monitor.is_locked)
        
        # Should fallback to device recreation
        self.mock_device.close.assert_called_once()  # Close old handle
        monitor.device_class.assert_called_with(mock_transport, device_info_dict)
        new_mock_device.open.assert_called_once()
        new_mock_device.init.assert_called_once()
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
        self.mock_device.set_brightness.assert_not_called()

if __name__ == '__main__':
    unittest.main()

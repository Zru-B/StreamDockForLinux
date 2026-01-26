
import unittest
from unittest.mock import MagicMock, patch, call
import time
from StreamDock.lock_monitor import LockMonitor

class TestLockMonitorReconnect(unittest.TestCase):
    def setUp(self):
        # Mock device
        self.mock_device = MagicMock()
        self.mock_device.path = b"test_path"
        self.mock_device.vendor_id = 0x1234
        self.mock_device.product_id = 0x5678
        self.mock_device.transport = MagicMock()
        self.mock_device._current_brightness = 80
        
        # Mock wrapper for device class that returns the mock device
        self.mock_device_class = MagicMock(return_value=self.mock_device)
        
        # Initialize monitor
        with patch('sys.modules', {'dbus': MagicMock()}):
            self.monitor = LockMonitor(self.mock_device, device_class=self.mock_device_class)
            # Inject mock properties
            self.monitor.device_vendor_id = 0x1234
            self.monitor.device_product_id = 0x5678
            self.monitor.device_path = "test_path"
            self.monitor.saved_brightness = 80
            self.monitor.device_transport = self.mock_device.transport

    @patch('StreamDock.lock_monitor.time.sleep', return_value=None)
    def test_reopen_device_retries_successfully(self, mock_sleep):
        """
        Test that _reopen_device_and_restore retries enumeration if device is not found immediately.
        This reproduces the fix requirement: we need it to retry enough times.
        """
        # Close should be called on old device
        self.mock_device.close = MagicMock()
        
        # Setup enumerate to return empty list first 5 times, then find the device
        # This simulates a slow device wake-up (e.g., 5 seconds delay)
        device_info = {'path': "test_path"}
        
        # Current implementation only retries once with 1s sleep (approx 2s total wait)
        # If we set it to fail 5 times, the current implementation should fail.
        # The fixed implementation should pass.
        
        self.mock_device.transport.enumerate.side_effect = [
            [], [], [], [], [], # 5 failures
            [device_info]       # Success
        ]
        
        # Determine if we expect failure (current code) or success (future code)
        # For reproduction, we assert that with current code this raises Exception
        # But for TDD, we can write the test assuming the fix, and see it fail.
        
        # We want the test to pass AFTER fix. So we expect success.
        # But failing right now confirms the bug.
        
        # Let's try to run it. If logic is correct, it should eventually find it.
        # But if the code doesn't retry enough, it will raise Exception.
        
        try:
            self.monitor._reopen_device_and_restore()
        except Exception as e:
            # If it failed as expected (bug reproduced), we can mark it.
            # But standard TDD flow is: Write test -> Fail -> Fix -> Pass.
            # So here I just call it, and expect it to fail now.
            raise e

        # verify it was called multiple times
        self.assertGreater(self.mock_device.transport.enumerate.call_count, 5)
        
        # Verify device was recreated and opened
        self.mock_device_class.assert_called()
        self.mock_device.open.assert_called()
        self.mock_device.init.assert_called()
        self.mock_device.set_brightness.assert_called_with(80)

if __name__ == '__main__':
    unittest.main()

import threading
import time
import unittest
from unittest.mock import ANY, MagicMock, patch

from StreamDock.devices.stream_dock import (DEFAULT_DOUBLE_PRESS_INTERVAL,
                                            StreamDock)


# Concrete implementation for testing abstract base class
class ConcreteStreamDock(StreamDock):
    def get_serial_number(self):
        return "TEST-SERIAL"
    
    def set_key_image(self, key, image):
        pass
        
    def set_brightness(self, percent):
        pass
        
    def set_touchscreen_image(self, image):
        pass

class TestStreamDock(unittest.TestCase):
    def setUp(self):
        self.mock_transport = MagicMock()
        self.dev_info = {
            'vendor_id': 0x1234,
            'product_id': 0x5678,
            'path': 'test_path'
        }
        self.device = ConcreteStreamDock(self.mock_transport, self.dev_info)
        # Mock the update lock which is usually created in subclasses or mixins?
        # StreamDock base doesn't seem to init update_lock in __init__ based on the code I viewed?
        # Let's check the code provided. 
        # Ah, __enter__ uses self.update_lock, but it's not defined in __init__.
        # It must be expected that generic initialization or mixins provide it.
        # Allowing it to fail if not present or mocking it if we test context manager.
        self.device.update_lock = MagicMock()

    def test_initialization(self):
        """Test proper initialization of the device."""
        self.assertEqual(self.device.vendor_id, 0x1234)
        self.assertEqual(self.device.product_id, 0x5678)
        self.assertEqual(self.device.path, 'test_path')
        self.assertEqual(self.device.transport, self.mock_transport)
        self.assertIsNone(self.device.read_thread)

    def test_open_close(self):
        """Test open and close lifecycle."""
        # Open
        self.device.open()
        self.mock_transport.open.assert_called_with(b'test_path')
        self.assertIsNotNone(self.device.read_thread)
        self.assertTrue(self.device.run_read_thread)
        
        # Close
        # In current implementation, close() just disconnects transport.
        # It does NOT stop the thread flag directly (that relies on read failure or __del__)
        self.device.close()
        self.mock_transport.disconnected.assert_called()
        # self.assertFalse(self.device.run_read_thread) # Removed as it's not guaranteed by close()

    def test_context_manager(self):
        """Test with statement lock acquisition."""
        with self.device:
            self.device.update_lock.acquire.assert_called_once()
        self.device.update_lock.release.assert_called_once()

    def test_command_passthrough(self):
        """Test delegation of commands to transport."""
        # Clear icon
        self.device.clear_icon(5)
        self.mock_transport.key_clear.assert_called_with(5)
        
        # Clear all
        self.device.clear_all_icons()
        self.mock_transport.key_all_clear.assert_called_once()
        
        # Wake screen
        self.device.wake_screen()
        self.mock_transport.wake_screen.assert_called_once()
        
        # Screen off/on
        # Need to mock screenlicent (timer) for screen_off
        self.device.screenlicent = MagicMock()
        self.device.screen_off()
        self.mock_transport.screen_off.assert_called_once()
        
        self.device.screen_on()
        self.mock_transport.screen_on.assert_called_once()
        
    def _process_queue(self):
        """Helper to process all events in the queue."""
        while not self.device._event_queue.empty():
            func, args = self.device._event_queue.get()
            func(*args)
            self.device._event_queue.task_done()

    def test_read_callback_dispatch(self):
        """Test that read loop dispatches single key press correctly."""
        # Data for Key 5 (mapped to 15) Pressed
        data_press = bytearray([0]*13)
        data_press[9] = 5
        data_press[10] = 1
        
        callback_mock = MagicMock()
        self.device.set_key_callback(callback_mock)
        
        # Mock read behavior
        def read_mock(*args, **kwargs):
             if getattr(read_mock, 'called', False):
                 self.device.run_read_thread = False
                 return None
             read_mock.called = True
             return data_press
             
        self.device.read = read_mock
        self.device.run_read_thread = True
        
        with patch('threading.Thread') as mock_thread_cls:
             def side_effect(target=None, daemon=False):
                 t = MagicMock()
                 t.start.side_effect = lambda: target() if target else None
                 return t
             
             mock_thread_cls.side_effect = side_effect
             
             self.device._read()
             
             self._process_queue()
             
             # Default KEY_MAP is False, so key 5 maps to 15 via KEY_MAPPING (unconditional)
             callback_mock.assert_called_with(self.device, 15, 1)

    @patch('StreamDock.devices.stream_dock.time.time')
    @patch('StreamDock.devices.stream_dock.threading.Timer')
    def test_double_press_detection(self, mock_timer, mock_time):
        """Test double press detection logic."""
        # Setup callbacks
        on_press = MagicMock()
        on_release = MagicMock()
        on_double = MagicMock()
        key_raw = 5
        key_mapped = 15 # KEY_MAPPING[5]
        
        self.device.set_per_key_callback(key_mapped, on_press, on_release, on_double)
        
        # Helper to stop loop after one read
        def create_read_mock(data):
            m = MagicMock()
            def side_effect(*args, **kwargs):
                if getattr(m, 'called_once', False):
                    self.device.run_read_thread = False
                    return None
                m.called_once = True
                return data
            m.side_effect = side_effect
            return m

        # Mock Threading to run callbacks immediately
        with patch('threading.Thread') as mock_thread_cls:
             def thread_side_effect(target=None, daemon=False):
                 t = MagicMock()
                 # Run target immediately
                 t.start.side_effect = lambda: target() if target else None
                 return t
             mock_thread_cls.side_effect = thread_side_effect
             
             # --- Simulation Sequence for Double Press ---
             
             # 1. First Press
             mock_time.return_value = 100.0
             # Data: Key 5, State 1
             data_p1 = bytearray([0]*13); data_p1[9]=key_raw; data_p1[10]=1
             
             # Inject into _read loop
             self.device.read = create_read_mock(data_p1)
             self.device.run_read_thread = True
             self.device._read()
             
             self._process_queue()

             # Verify: Timer started for delayed single press
             # Because we have a double press callback, it delays the single press
             mock_timer.assert_called() 
             # Capture the timer callback for single press
             timer_args = mock_timer.call_args[0]
             delayed_press_callback = timer_args[1]
             
             # Verify on_press NOT called yet
             on_press.assert_not_called()
             
             # 2. First Release
             mock_time.return_value = 100.1
             # Data: Key 5, State 0
             data_r1 = bytearray([0]*13); data_r1[9]=key_raw; data_r1[10]=0
             
             self.device.read = create_read_mock(data_r1)
             self.device.run_read_thread = True
             self.device._read()
             
             self._process_queue()

             # Verify: Timer started for delayed release
             delayed_release_callback = mock_timer.call_args[0][1]
             on_release.assert_not_called()
             
             # 3. Second Press (Double Press Action)
             mock_time.return_value = 100.2 # Within interval (default 0.3s)
             # Data: Key 5, State 1
             data_p2 = bytearray([0]*13); data_p2[9]=key_raw; data_p2[10]=1
             
             self.device.read = create_read_mock(data_p2)
             self.device.run_read_thread = True
             
             # Create mock timers and inject them, KEEPING references
             mock_press_timer = MagicMock()
             mock_release_timer = MagicMock()
             self.device.pending_single_press[key_mapped] = mock_press_timer
             self.device.pending_single_release[key_mapped] = mock_release_timer
             
             self.device._read()
             
             self._process_queue()
             
             # Verify: Double press callback called
             on_double.assert_called_with(self.device, key_mapped)
             
             # Verify: Pending single press/release cancelled
             # We use the references we kept, because self.device.pending_... is now None
             mock_press_timer.cancel.assert_called()
             mock_release_timer.cancel.assert_called()
             
             # 4. Second Release (Should be skipped)
             mock_time.return_value = 100.3
             data_r2 = bytearray([0]*13); data_r2[9]=key_raw; data_r2[10]=0
             
             self.device.read = create_read_mock(data_r2)
             self.device.run_read_thread = True
             
             self.device._read()
             
             self._process_queue()
             
             # Verify on_release STILL not called (skipped)
             on_release.assert_not_called()

    @patch('StreamDock.devices.stream_dock.time.time')
    @patch('StreamDock.devices.stream_dock.threading.Timer')
    def test_single_press_with_double_setup(self, mock_timer, mock_time):
        """Test single press behaving correctly even when double press is configured."""
        on_press = MagicMock()
        on_release = MagicMock()
        on_double = MagicMock()
        key_raw = 5
        key_mapped = 15
        
        self.device.set_per_key_callback(key_mapped, on_press, on_release, on_double)
        
        # Helper to stop loop after one read
        def create_read_mock(data):
            m = MagicMock()
            def side_effect(*args, **kwargs):
                if getattr(m, 'called_once', False):
                    self.device.run_read_thread = False
                    return None
                m.called_once = True
                return data
            m.side_effect = side_effect
            return m

        with patch('threading.Thread') as mock_thread_cls:
             def side_effect(target=None, daemon=False):
                 t = MagicMock()
                 t.start.side_effect = lambda: target() if target else None
                 return t
             mock_thread_cls.side_effect = side_effect
             
             # 1. Press
             mock_time.return_value = 100.0
             data_p1 = bytearray([0]*13); data_p1[9]=key_raw; data_p1[10]=1
             self.device.read = create_read_mock(data_p1)
             self.device.run_read_thread = True
             self.device._read()
             
             self._process_queue()

             # Capture timer
             press_timer_callback = mock_timer.call_args[0][1]
             press_timer_mock = mock_timer.return_value
             
             # 2. Release
             mock_time.return_value = 100.1
             data_r1 = bytearray([0]*13); data_r1[9]=key_raw; data_r1[10]=0
             self.device.read = create_read_mock(data_r1)
             self.device.run_read_thread = True
             self.device._read()
             
             self._process_queue()
             
             # Capture release timer
             release_timer_callback = mock_timer.call_args[0][1]
             
             # 3. Time passes... No second press.
             # Ideally the timers would fire. We manually fire them.
             
             # Simulate Press Timer firing
             press_timer_callback()
             self._process_queue() # Timer puts callback in queue!
             on_press.assert_called_with(self.device, key_mapped)
             
             # Simulate Release Timer firing
             release_timer_callback()
             self._process_queue() # Timer puts callback in queue!
             on_release.assert_called_with(self.device, key_mapped)
             
             on_double.assert_not_called()

if __name__ == '__main__':
    unittest.main()

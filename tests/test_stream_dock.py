import threading
import time
import unittest
from unittest.mock import ANY, MagicMock, patch

from StreamDock.devices.stream_dock import (DEFAULT_BRIGHTNESS,
                                            DEFAULT_DOUBLE_PRESS_INTERVAL,
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
        # Mock transport.open to return success (1)
        self.mock_transport.open.return_value = 1
        
        # Open
        result = self.device.open()
        self.assertTrue(result)
        self.mock_transport.open.assert_called_with(b'test_path')
        self.assertIsNotNone(self.device.read_thread)
        self.assertTrue(self.device.run_read_thread)
        
        # Close
        # In current implementation, close() just disconnects transport.
        # It does NOT stop the thread flag directly (that relies on read failure or __del__)
        self.device.close()
        self.mock_transport.disconnected.assert_called()

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
        
    def test_init_applies_requested_brightness(self):
        """Test init() applies the requested brightness instead of forcing 100%."""
        self.device.set_brightness = MagicMock(return_value=1)

        self.device.init(15)

        self.device.set_brightness.assert_called_once_with(15)
        self.assertEqual(self.device._current_brightness, 15)
        self.mock_transport.wake_screen.assert_called_once()
        self.mock_transport.key_all_clear.assert_called_once()
        self.mock_transport.refresh.assert_called_once()

    def test_init_defaults_to_full_brightness(self):
        """Test init() falls back to the default brightness when none is given."""
        self.device.set_brightness = MagicMock(return_value=1)

        self.device.init()

        self.device.set_brightness.assert_called_once_with(DEFAULT_BRIGHTNESS)
        self.assertEqual(self.device._current_brightness, DEFAULT_BRIGHTNESS)

    def test_init_clamps_brightness(self):
        """Test init() clamps the brightness to the 0-100 range."""
        self.device.set_brightness = MagicMock()

        self.device.init(150)
        self.device.set_brightness.assert_called_once_with(100)

        self.device.set_brightness.reset_mock()
        self.device.init(-10)
        self.device.set_brightness.assert_called_once_with(0)

    def test_init_keeps_previous_brightness_when_write_fails(self):
        # Guards brightness up/down stepping from a value the device never took.
        self.device._current_brightness = 40
        self.device.set_brightness = MagicMock(return_value=-1)

        self.device.init(80)

        self.assertEqual(self.device._current_brightness, 40)

    def test_clear_icon_rejects_out_of_range_key_on_mapped_device(self):
        # Guards KEY_MAPPING raising KeyError before the range check could run.
        self.device.KEY_MAP = True

        self.assertEqual(self.device.clear_icon(16), -1)
        self.assertEqual(self.device.clear_icon(0), -1)
        self.mock_transport.key_clear.assert_not_called()

        self.device.clear_icon(1)
        self.mock_transport.key_clear.assert_called_once_with(11)

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


class TestReaderAndLifecycleRegressions(unittest.TestCase):
    def setUp(self):
        self.transport = MagicMock()
        self.transport.open.return_value = 1
        self.transport.read_.return_value = None
        self.device = ConcreteStreamDock(
            self.transport, {'vendor_id': 1, 'product_id': 2, 'path': 'p'})

    def tearDown(self):
        self.device.close()

    def _run_reader_over(self, reads):
        """Feed `reads` (values or exceptions) to _read, then stop the loop."""
        reads = list(reads)

        def read_mock(*args, **kwargs):
            if not reads:
                self.device.run_read_thread = False
                return None
            item = reads.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item

        self.device.read = read_mock
        self.device.run_read_thread = True
        self.device._read()

    def test_screen_off_does_not_rearm_itself(self):
        # Guards the deck blanking every N seconds forever after the first lock.
        self.device.screen_off()
        self.assertIsNone(self.device.screenlicent)

    def test_close_cancels_pending_countdown(self):
        # Guards a countdown armed before close blanking a reopened deck.
        self.device.set_seconds(0.05)
        self.device.close()
        time.sleep(0.15)
        self.transport.screen_off.assert_not_called()

    def test_open_cancels_pending_countdown(self):
        self.device.set_seconds(0.05)
        self.device.open()
        time.sleep(0.15)
        self.transport.screen_off.assert_not_called()

    def test_unknown_key_report_is_ignored_and_reader_keeps_running(self):
        # Guards a KeyError on an unmapped key id closing the device from the reader.
        callback = MagicMock()
        self.device.key_callback = callback
        self.device.close = MagicMock()
        unknown = bytearray(13); unknown[9] = 0x40; unknown[10] = 1
        known = bytearray(13); known[9] = 5; known[10] = 1

        self._run_reader_over([unknown, known])

        self.device.close.assert_not_called()
        queued = []
        while not self.device._event_queue.empty():
            queued.append(self.device._event_queue.get_nowait())
        self.assertEqual([args for _, args in queued], [(self.device, 15, 1)])

    @patch('StreamDock.devices.stream_dock.time.sleep')
    def test_read_error_backs_off_instead_of_closing(self, mock_sleep):
        # Guards a busy spin (or a close) when every read fails after an unplug.
        self.device.close = MagicMock()

        self._run_reader_over([OSError("gone"), OSError("gone")])

        self.device.close.assert_not_called()
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertGreater(mock_sleep.call_args[0][0], 0)

    def test_reopen_stops_old_reader_before_reopening_transport(self):
        # Guards hid_close() running while the old reader is inside hid_read_timeout().
        order = []
        self.device.open()
        old_reader = self.device.read_thread

        def transport_open(path):
            order.append(('open', old_reader.is_alive()))
            return 1
        self.transport.open.side_effect = transport_open

        self.device.open()

        self.assertEqual(order, [('open', False)])
        self.assertIsNot(self.device.read_thread, old_reader)

    def test_close_cancels_gestures_and_drops_queued_callbacks(self):
        # Guards a press, release or long press from before close firing after reopen.
        fired = []
        self.device.long_press_duration = 0.05
        self.device.double_press_interval = 0.05
        self.device.set_per_key_callback(
            3, on_press=lambda d, k: fired.append('press'),
            on_long_press=lambda d, k: fired.append('long'),
            on_double_press=lambda d, k: fired.append('double'))
        self.device.set_per_key_callback(
            4, on_release=lambda d, k: fired.append('release'),
            on_double_press=lambda d, k: fired.append('double'))

        self.device._handle_key_event(3, True)
        self.device._handle_key_event(4, True)
        self.device._handle_key_event(4, False)
        self.device.long_press_fired.add(7)
        self.device.release_skip_count[8] = 1
        self.device._queue_callback(lambda d, k: fired.append('queued'), 1)

        self.device.close()
        self.device.open()
        time.sleep(0.2)

        self.assertEqual(fired, [])
        self.assertEqual(self.device.long_press_fired, set())
        self.assertEqual(self.device.release_skip_count, {})
        self.assertFalse(any(self.device.pending_long_press.values()))
        self.assertFalse(any(self.device.pending_single_release.values()))
        self.assertIn(3, self.device.per_key_callbacks)


class TestStreamDock293V3Brightness(unittest.TestCase):
    def setUp(self):
        from StreamDock.devices.stream_dock_293_v3 import StreamDock293V3
        self.transport = MagicMock()
        self.device = StreamDock293V3(
            self.transport, {'vendor_id': 1, 'product_id': 2, 'path': 'p'})

    def test_records_brightness_on_success(self):
        # The brightness up/down actions step from _current_brightness.
        self.transport.set_brightness.return_value = 1

        self.device.set_brightness(30)

        self.assertEqual(self.device._current_brightness, 30)

    def test_keeps_brightness_on_failure(self):
        self.transport.set_brightness.return_value = -1

        self.device.set_brightness(30)

        self.assertEqual(self.device._current_brightness, DEFAULT_BRIGHTNESS)



class TestSuspendedInput(unittest.TestCase):
    """While the screensaver runs on a locked computer, no key may act."""

    def setUp(self):
        self.device = ConcreteStreamDock(MagicMock(), {'vendor_id': 1, 'product_id': 2,
                                                       'path': 'p'})
        self.pressed = MagicMock()
        self.device.set_per_key_callback(15, on_press=self.pressed)
        self.global_callback = MagicMock()
        self.device.set_key_callback(self.global_callback)

    def _feed_one_press(self):
        report = bytearray([0] * 13)
        report[9] = 5
        report[10] = 1
        reports = [report]

        def read(*args, **kwargs):
            if not reports:
                self.device.run_read_thread = False
                return None
            return reports.pop()

        self.device.read = read
        self.device.run_read_thread = True
        self.device._read()

    def test_a_press_while_suspended_is_dropped(self):
        self.device.suspend_input()

        self._feed_one_press()

        self.assertTrue(self.device._event_queue.empty())
        self.assertTrue(self.device.input_suspended)

    def test_suspending_drops_work_already_queued(self):
        self.device._event_queue.put((self.pressed, (self.device, 15)))

        self.device.suspend_input()

        self.assertTrue(self.device._event_queue.empty())

    def test_keys_work_again_after_resume(self):
        self.device.suspend_input()
        self.device.resume_input()

        self._feed_one_press()

        self.assertFalse(self.device._event_queue.empty())


if __name__ == '__main__':
    unittest.main()

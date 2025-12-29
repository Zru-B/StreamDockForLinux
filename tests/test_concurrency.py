import unittest
import threading
import time
import random
import logging
import pytest
from unittest.mock import MagicMock, patch
from StreamDock.devices.stream_dock import StreamDock

# Configure logging to capture output during tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConcreteStreamDock(StreamDock):
    """Concrete implementation for testing abstract base class."""
    def get_serial_number(self):
        return "TEST-SERIAL-CONCURRENCY"
    
    def set_key_image(self, key, image):
        pass
        
    def set_brightness(self, percent):
        pass
        
    def set_touchscreen_image(self, image):
        pass

@pytest.mark.regression
@pytest.mark.stability
class TestConcurrencyAndStability(unittest.TestCase):
    def setUp(self):
        self.mock_transport = MagicMock()
        self.dev_info = {
            'vendor_id': 0x1234,
            'product_id': 0x5678,
            'path': 'test_path_concurrency'
        }
        # Ensure clean state for threading counts
        self.initial_thread_count = threading.active_count()

    def tearDown(self):
        # Ensure we don't leak threads between tests
        # Give a small grace period for daemon threads to be collected or stopped
        time.sleep(0.1)
        final_thread_count = threading.active_count()
        # Note: accurate thread counting is hard in test runners due to background tasks
        # but we can check if it exploded.

    def test_rapid_lifecycle_stress(self):
        """
        Stress test rapid open/close cycles to ensure no resource leaks or race conditions.
        """
        device = ConcreteStreamDock(self.mock_transport, self.dev_info)
        
        # Mock transport.read to return empty or block slightly so read thread starts
        def blocking_read():
            time.sleep(0.001)
            return None
        device.read = blocking_read
        
        cycles = 50
        for i in range(cycles):
            try:
                device.open()
                # Simulate a tiny bit of work
                time.sleep(0.001)
                device.close()
            except Exception as e:
                self.fail(f"Lifecycle crashed on iteration {i}: {e}")
        
        # Verify cleanup
        self.assertFalse(device.run_read_thread)
        # Check threads (heuristic)
        # Ideally, we shouldn't have 50 extra threads running
        current_threads = threading.active_count()
        self.assertLess(current_threads, self.initial_thread_count + 5, "Potential thread leak detected")


    def test_thread_bounding(self):
        """
        Verify that thread count stays bounded even when flooding the event queue.
        With the new Worker Pool model, we expect exactly DEFAULT_WORKER_THREADS + 1 (Reader) + Main.
        """
        device = ConcreteStreamDock(self.mock_transport, self.dev_info)
        device.open()
        
        # Determine expected baseline:
        # Initial + Reader Thread + Worker Threads
        from StreamDock.devices.stream_dock import DEFAULT_WORKER_THREADS
        expected_threads = self.initial_thread_count + 1 + DEFAULT_WORKER_THREADS
        
        # Allow some grace for other system threads, but it shouldn't be much higher
        # Wait a bit for workers to start
        time.sleep(0.1)
        
        current_threads = threading.active_count()
        # We assert it's roughly correct. 
        self.assertLessEqual(current_threads, expected_threads + 2, 
                             f"Thread count {current_threads} exceeds expectation {expected_threads + 2}")
        
        # Now flood with tasks (indirectly via callbacks)
        # We can't flood with actual events easily without generating thousands of callbacks
        # Let's manually convert internal queue flood:
        for i in range(200):
            # Queue a dummy task
            device._event_queue.put((lambda: time.sleep(0.001), ()))
            
        time.sleep(0.1)
        
        # Thread count should NOT have increased despite 200 tasks
        new_thread_count = threading.active_count()
        self.assertLessEqual(new_thread_count, expected_threads + 2, 
                             "Thread explosion detected! Pool not working.")
                             
        device.close()

    def test_daemon_thread_safety(self):
        """
        Verify that all spawned threads (read thread, workers) are daemon threads.
        """
        device = ConcreteStreamDock(self.mock_transport, self.dev_info)
        device.open()
        
        # 1. Check Read Thread
        self.assertTrue(device.read_thread.daemon, "Read thread must be daemon")
        
        # 2. Check Worker Threads
        time.sleep(0.1)
        self.assertTrue(len(device._workers) > 0, "Workers should be started")
        for t in device._workers:
            self.assertTrue(t.daemon, "Worker thread must be daemon")
            
        device.close()


    def test_event_flooding_stability(self):
        """
        Flood the device with events while modifying state to check for crashes.
        """
        device = ConcreteStreamDock(self.mock_transport, self.dev_info)
        device.open()
        
        stop_flood = threading.Event()
        error_container = []

        def spam_events():
            # Generate random key presses
            while not stop_flood.is_set():
                key = random.randint(1, 15)
                state = random.randint(0, 1)
                data = bytearray([0]*13)
                data[9] = key
                data[10] = state
                
                # Directly call processing logic to simulate rapid transport reads
                # We bypass the actual read thread loop effectively by calling the processor
                # providing 'process_key_event' existed, but it's inside _read.
                # So we have to mock 'read' to return fast.
                pass 
        
        # Better approach: Mock 'read' to yield data extremely fast
        # Generator for infinite random data
        def data_generator():
            while not stop_flood.is_set():
                key = random.randint(1, 15)
                state = random.choice([0, 1])
                data = bytearray([0]*13)
                data[9] = key
                data[10] = state
                yield data
            yield None

        gen = data_generator()
        device.read = lambda: next(gen)

        # Start a reader thread manually if not already running (open starts it)
        # But we replaced 'read' after open, which might be too late if thread cached it?
        # Python methods are looked up at runtime, so it should be fine.
        
        # Wait a bit
        time.sleep(1.0)
        
        # During flood, do some operations
        try:
            device.set_brightness(50)
            # device.read() # Call manually removed to avoid generator contention
            device.reset_countdown(5)
            # device.close() # Close in the middle
        except Exception as e:
            self.fail(f"Crashed during event flooding: {e}")
        
        stop_flood.set()
        device.close()

    def test_race_close_during_callback(self):
        """
        Ensure closing the device while a callback is executing doesn't deadlock.
        """
        device = ConcreteStreamDock(self.mock_transport, self.dev_info)
        
        callback_started = threading.Event()
        callback_finished = threading.Event()
        
        def slow_callback(dev, key, state):
            callback_started.set()
            time.sleep(0.5) # Simulate work
            callback_finished.set()
            
        device.set_key_callback(slow_callback)
        
        # Inject one event
        data_p = bytearray([0]*13); data_p[9]=1; data_p[10]=1
        device.read = MagicMock(side_effect=[data_p, None]) # Return one event then stop
        
        device.open()
        
        # Wait for callback to start
        if not callback_started.wait(timeout=2):
            self.fail("Callback never started")
            
        # Call close immediately while callback is sleeping
        start_close = time.time()
        device.close()
        end_close = time.time()
        
        # Check if close hung
        self.assertLess(end_close - start_close, 1.0, "Close() took too long, possible deadlock waiting for callback")
        
        # Wait for callback to finish to ensure clean teardown
        callback_finished.wait(timeout=1)

    def test_exception_resilience(self):
        """
        Ensure an exception in a user callback doesn't crash the reader thread.
        """
        device = ConcreteStreamDock(self.mock_transport, self.dev_info)
        
        def crashing_callback(dev, key, state):
            raise ValueError("I crashed!")
            
        device.set_key_callback(crashing_callback)
        
        # Inject event 1 (Crash)
        data_1 = bytearray([0]*13); data_1[9]=1; data_1[10]=1
        # Inject event 2 (Normal - ensures thread still alive)
        data_2 = bytearray([0]*13); data_2[9]=2; data_2[10]=1
        
        device.read = MagicMock(side_effect=[data_1, data_2, None])
        
        # We need a way to verify Event 2 was processed. 
        # But we can't easily hook into the loop without another callback?
        # Wait, the callback crashes. So we can't use it for verification easily unless we change it based on key.
        
        success_event = threading.Event()
        
        def mixed_callback(dev, key, state):
            if key == 11: # Key 1 maps to 11
                raise ValueError("Crash")
            if key == 12: # Key 2 maps to 12
                success_event.set()
                
        device.set_key_callback(mixed_callback)
        
        device.open()
        
        # Wait for success
        success = success_event.wait(timeout=2)
        device.close()
        
        self.assertTrue(success, "Reader thread died after exception, failed to process subsequent events")

if __name__ == '__main__':
    unittest.main()

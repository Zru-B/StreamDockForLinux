import asyncio
import logging
import queue
import threading
import time
from abc import ABC, ABCMeta, abstractmethod

logger = logging.getLogger(__name__)

class TransportError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code

    def __str__(self):
        if self.code:
            return f"[Error Code {self.code}] {super().__str__()}"
        return super().__str__()

KEY_MAPPING = {
    1 : 11, 2 : 12, 3 : 13, 4 : 14,
    5 : 15, 6 : 6,  7 : 7,  8 : 8,
    9 : 9,  10 : 10,11 : 1, 12 : 2,
    13 : 3, 14 : 4, 15 : 5
}

# Default double-press detection interval (in seconds)
# This can be overridden via configuration
DEFAULT_DOUBLE_PRESS_INTERVAL = 0.3

# Default hold time (in seconds) after which a key press counts as a long press
# This can be overridden via configuration
DEFAULT_LONG_PRESS_DURATION = 0.5

# Default number of worker threads for callback processing
DEFAULT_WORKER_THREADS = 4

# Default screen brightness (percent) used when none is configured
DEFAULT_BRIGHTNESS = 100

class StreamDock(ABC):
    """
    Represents a physically attached StreamDock device.
    """

    KEY_COUNT = 0
    KEY_COLS = 0
    KEY_ROWS = 0

    KEY_PIXEL_WIDTH = 0
    KEY_PIXEL_HEIGHT = 0
    KEY_IMAGE_FORMAT = ""
    KEY_FLIP = (False, False)
    KEY_ROTATION = 0
    KEY_MAP = False

    TOUCHSCREEN_PIXEL_WIDTH = 0
    TOUCHSCREEN_PIXEL_HEIGHT = 0
    TOUCHSCREEN_IMAGE_FORMAT = ""
    TOUCHSCREEN_FLIP = (False, False)
    TOUCHSCREEN_ROTATION = 0

    DIAL_COUNT = 0

    DECK_TYPE = ""
    DECK_VISUAL = False
    DECK_TOUCH = False

    __metaclass__ = ABCMeta
    __seconds = 300
    def __init__(self,transport1,devInfo):
        self.transport=transport1
        self.vendor_id=devInfo['vendor_id']
        self.product_id=devInfo['product_id']
        self.path=devInfo['path']

        self.read_thread = None
        self.run_read_thread = False

        self.key_callback = None
        self.per_key_callbacks = {}  # Dictionary to store per-key callbacks

        # event queue and worker threads
        self._event_queue = queue.Queue()
        self._workers = []

        # Gesture (double-press / long-press) detection tracking
        self.last_release_time = {}  # Track last release time for each key
        self.pending_single_press = {}  # Track pending single press events
        self.pending_single_release = {}  # Track pending single release events
        self.release_skip_count = {}  # Track how many releases to skip after double-press
        self.pending_long_press = {}  # Track pending long-press timers
        self.long_press_fired = set()  # Keys whose current hold already fired a long press
        # Gesture timers fire on their own threads while the read thread
        # handles the next event, so all of the state above is guarded.
        self._gesture_lock = threading.Lock()

        # Gesture timings (can be configured)
        self.double_press_interval = DEFAULT_DOUBLE_PRESS_INTERVAL
        self.long_press_duration = DEFAULT_LONG_PRESS_DURATION
        self.screenlicent = None

        # Last brightness applied to the device, used by brightness up/down actions
        self._current_brightness = DEFAULT_BRIGHTNESS

    def __del__(self):
        """
        Delete handler for the StreamDock, automatically closing the transport
        if it is currently open and terminating the transport reader thread.
        """
        try:
            self._setup_reader(None)
        except (TransportError, ValueError):
            pass

        try:
            self.close()
        except (TransportError):
            pass

    def __enter__(self):
        """
        Enter handler for the StreamDock, taking the exclusive update lock on
        the deck. This can be used in a `with` statement to ensure that only one
        thread is currently updating the deck, even if it is doing multiple
        operations (e.g. setting the image on multiple keys).
        """
        self.update_lock.acquire()

    def __exit__(self, type, value, traceback):
        """
        Exit handler for the StreamDock, releasing the exclusive update lock on
        the deck.
        """
        self.update_lock.release()

    def key(self, k):
        if self.KEY_MAP:
            return KEY_MAPPING[k]
        
        return k

    def open(self):
        """
        Open the device for communication.

        Returns:
            True if device opened successfully, False otherwise
        """
        self._start_workers()
        result = self.transport.open(bytes(self.path, 'utf-8'))
        if result != 1:
            self._stop_workers()
            return False
        self._setup_reader(self._read)
        return True

    def init(self, brightness=DEFAULT_BRIGHTNESS):
        """
        Wake the screen and bring the device to a known state.

        :param int brightness: Brightness percentage (0-100) to apply.
        """
        brightness = max(0, min(100, int(brightness)))
        self.wake_screen()
        self.set_brightness(brightness)
        self._current_brightness = brightness
        self.clear_all_icons()
        self.refresh()

    def close(self):
        """
        Close the device and release the HID handle.
        """
        self._setup_reader(None)
        self._stop_workers()
        self.disconnected()
        self.transport.close()  # Release the HID handle so device can be reopened

    def disconnected(self):
        self.transport.disconnected()

    def clear_icon(self, index):
        origin = index
        index = self.key(index)
        if index not in range(1, 16):
            logger.error("key '%s' out of range. you should set (1 ~ 15)", origin)
            return -1
        self.transport.key_clear(index)

    def clear_all_icons(self):
        self.transport.key_all_clear()

    def wake_screen(self):
        self.transport.wake_screen()

    def refresh(self):
        self.transport.refresh()

    def get_path(self):
        return self.path

    def read(self, timeout_ms=None):
        if timeout_ms is not None:
            data = self.transport.read_(13, timeout_ms=timeout_ms)
        else:
            data = self.transport.read_(13)

        # read_() returns a tuple: (result_bytes, ack, ok, key, status)
        # Extract only the bytes array
        if data and isinstance(data, tuple):
            return data[0]  # Return only result_bytes
        return data

    def whileread(self):
        """Read loop for manual key event monitoring (deprecated - use callbacks)."""
        while 1:
            try:
                data = self.read(timeout_ms=1000)
                if data != None and len(data) >= 11:
                    if (data[:3].decode('utf-8', errors='ignore') == "ACK" and data[5:7].decode('utf-8', errors='ignore')):
                        if data[10] == 0x01 and data[9] > 0x00 and data[9] <= 0x0f:
                            key_num = KEY_MAPPING[data[9]] if self.KEY_MAP else data[9]
                            logger.debug("Key %s pressed", key_num)
                        elif data[10] == 0x00 and data[9] > 0x00 and data[9] <= 0x0f:
                            key_num = KEY_MAPPING[data[9]] if self.KEY_MAP else data[9]
                            logger.debug("Key %s released", key_num)
            except Exception as e:
                logger.exception("Error in whileread: %s", e)
                break

    def screen_off(self):
        res=self.transport.screen_off()
        self.reset_countdown(self.__seconds)
        return res

    def screen_on(self):
        return self.transport.screen_on()

    def set_seconds(self,data):
        self.__seconds=data
        self.reset_countdown(self.__seconds)

    def reset_countdown(self,data):
        if self.screenlicent is not None:
            self.screenlicent.cancel()
        self.screenlicent=threading.Timer(data,self.screen_off)
        self.screenlicent.daemon = True
        self.screenlicent.start()

    @abstractmethod
    def get_serial_number(self):
        pass

    @abstractmethod
    def set_key_image(self, key, image):
        pass

    @abstractmethod
    def set_brightness(self, percent):
        pass

    @abstractmethod
    def set_touchscreen_image(self, image):
        pass

    def id(self):
        """
        Retrieves the physical ID of the attached StreamDock. This can be used
        to differentiate one StreamDock from another.

        :rtype: str
        :return: Identifier for the attached device.
        """
        return self.get_path()

    def _setup_reader(self, callback):
        """
        Sets up the internal transport reader thread with the given callback,
        for asynchronous processing of HID events from the device. If the thread
        already exists, it is terminated and restarted with the new callback
        function.

        :param function callback: Callback to run on the reader thread.
        """
        if self.read_thread is not None:
            self.run_read_thread = False

            try:
                self.read_thread.join()
            except RuntimeError:
                pass

        self.read_thread = None

        if callback is not None:
            self.run_read_thread = True
            self.read_thread = threading.Thread(target=callback)
            self.read_thread.daemon = True
            self.read_thread.start()

    def _worker_loop(self):
        """
        Worker thread loop that consumes tasks from the event queue and executes them.
        """
        while True:
            try:
                task = self._event_queue.get()
                if task is None:
                    # Sentinel to shut down the worker
                    self._event_queue.task_done()
                    break

                func, args = task
                try:
                    func(*args)
                except Exception:
                    logger.exception("Error executing callback %s", func.__name__)
                finally:
                    self._event_queue.task_done()
            except Exception:
                logger.exception("Unexpected error in worker loop")

    def _start_workers(self):
        """
        Starts the worker threads for processing callbacks.
        """
        if not self._workers:
            for _ in range(DEFAULT_WORKER_THREADS):
                t = threading.Thread(target=self._worker_loop)
                t.daemon = True
                t.start()
                self._workers.append(t)

    def _stop_workers(self):
        """
        Stops the worker threads.
        """
        # Send shutdown sentinels
        for _ in self._workers:
            self._event_queue.put(None)

        # We don't necessarily join() here because they are daemon threads
        # and we might want fast shutdown. But for correctness we could.
        # Given StreamDock usage, just clearing the list is enough as they are Daemon.
        # But clearing the list ensures we can restart them if opened again.
        self._workers.clear()


    def set_key_callback(self, callback):
        """
        Sets the callback function called each time a button on the StreamDock
        changes state (either pressed, or released).

        .. note:: This callback will be fired from an internal reader thread.
                  Ensure that the given callback function is thread-safe.

        .. note:: Only one callback can be registered at one time.

        .. seealso:: See :func:`~StreamDock.set_key_callback_async` method for
                     a version compatible with Python 3 `asyncio` asynchronous
                     functions.

        :param function callback: Callback function to fire each time a button
                                state changes.
        """
        self.key_callback = callback

    def set_key_callback_async(self, async_callback, loop=None):
        """
        Sets the asynchronous callback function called each time a button on the
        StreamDock changes state (either pressed, or released). The given
        callback should be compatible with Python 3's `asyncio` routines.

        .. note:: The asynchronous callback will be fired in a thread-safe
                  manner.

        .. note:: This will override the callback (if any) set by
                  :func:`~StreamDock.set_key_callback`.

        :param function async_callback: Asynchronous callback function to fire
                                        each time a button state changes.
        :param asyncio.loop loop: Asyncio loop to dispatch the callback into
        """
        loop = loop or asyncio.get_event_loop()

        def callback(*args):
            asyncio.run_coroutine_threadsafe(async_callback(*args), loop)

        self.set_key_callback(callback)

    def set_touchscreen_callback(self, callback):
        """
        Sets the callback function called each time there is an interaction
        with a touchscreen on the StreamDock.

        .. note:: This callback will be fired from an internal reader thread.
                  Ensure that the given callback function is thread-safe.

        .. note:: Only one callback can be registered at one time.

        .. seealso:: See :func:`~StreamDock.set_touchscreen_callback_async`
                     method for a version compatible with Python 3 `asyncio`
                     asynchronous functions.

        :param function callback: Callback function to fire each time a button
                                state changes.
        """

    def set_touchscreen_callback_async(self, async_callback, loop=None):
        """
        Sets the asynchronous callback function called each time there is an
        interaction with the touchscreen on the StreamDock. The given callback
        should be compatible with Python 3's `asyncio` routines.

        .. note:: The asynchronous callback will be fired in a thread-safe
                  manner.

        .. note:: This will override the callback (if any) set by
                  :func:`~StreamDock.set_touchscreen_callback`.

        :param function async_callback: Asynchronous callback function to fire
                                        each time a button state changes.
        :param asyncio.loop loop: Asyncio loop to dispatch the callback into
        """
        loop = loop or asyncio.get_event_loop()

        def callback(*args):
            asyncio.run_coroutine_threadsafe(async_callback(*args), loop)

        self.set_touchscreen_callback(callback)

    def set_per_key_callback(self, key, on_press=None, on_release=None, on_double_press=None,
                             on_long_press=None):
        """
        Sets the callback functions for a specific key on the StreamDock.
        You can register separate callbacks for press, release, double-press
        and long-press events.

        When ``on_double_press`` is set, press and release are delayed by
        ``double_press_interval`` so a second press can cancel them.

        When ``on_long_press`` is set, ``on_press`` is deferred to the release:
        a key released before ``long_press_duration`` runs ``on_press`` then
        ``on_release``; a key held that long runs ``on_long_press`` while still
        down, and its release runs nothing.

        .. note:: These callbacks will be fired from an internal reader thread.
                  Ensure that the given callback functions are thread-safe.

        .. note:: This does not override the global key_callback. Both will be called.

        :param int key: The key number to set callbacks for.
        :param function on_press: Callback function to fire when the key is pressed.
                                  Signature: callback(device, key)
        :param function on_release: Callback function to fire when the key is released.
                                    Signature: callback(device, key)
        :param function on_double_press: Callback function to fire when the key is double-pressed.
                                         Signature: callback(device, key)
        :param function on_long_press: Callback function to fire when the key is held down.
                                       Signature: callback(device, key)
        """
        self.per_key_callbacks[key] = {
            'on_press': on_press,
            'on_release': on_release,
            'on_double_press': on_double_press,
            'on_long_press': on_long_press
        }

    def clear_key_callback(self, key):
        """
        Clears all callback functions for a specific key on the StreamDock.

        :param int key: The key number to clear callbacks for.
        """
        with self._gesture_lock:
            self.per_key_callbacks.pop(key, None)

            for pending in (self.pending_single_press, self.pending_single_release,
                            self.pending_long_press):
                timer = pending.pop(key, None)
                if timer is not None:
                    timer.cancel()

            self.last_release_time.pop(key, None)
            self.release_skip_count.pop(key, None)
            self.long_press_fired.discard(key)

    def clear_all_callbacks(self):
        """
        Clears all per-key callback functions from the StreamDock.
        """
        with self._gesture_lock:
            for pending in (self.pending_single_press, self.pending_single_release,
                            self.pending_long_press):
                for timer in pending.values():
                    if timer is not None:
                        timer.cancel()
                pending.clear()

            self.per_key_callbacks.clear()
            self.last_release_time.clear()
            self.release_skip_count.clear()
            self.long_press_fired.clear()

    def _queue_callback(self, callback, k):
        self._event_queue.put((callback, (self, k)))

    def _queue_in_order(self, callbacks, k):
        """
        Queue several callbacks as one work item so the worker pool cannot
        reorder them (e.g. a deferred press landing after its release).
        """
        callbacks = [cb for cb in callbacks if cb]
        if not callbacks:
            return

        def run_all(device, key):
            for cb in callbacks:
                cb(device, key)

        self._queue_callback(run_all, k)

    def _start_gesture_timer(self, pending, k, delay, on_timeout):
        """
        Start a timer stored in ``pending[k]``. It fires ``on_timeout`` (under
        the gesture lock) only if it is still the key's pending timer, so a
        timer racing a cancellation from the read thread does nothing.
        """
        def fire():
            with self._gesture_lock:
                if pending.get(k) is not timer:
                    return
                pending[k] = None
                on_timeout()

        timer = threading.Timer(delay, fire)
        pending[k] = timer
        timer.daemon = True
        timer.start()

    @staticmethod
    def _cancel_pending(pending, k):
        timer = pending.get(k)
        if timer is not None:
            timer.cancel()
            pending[k] = None

    def _handle_key_event(self, k, pressed):
        """Dispatch one press/release of key ``k`` to its per-key callbacks."""
        with self._gesture_lock:
            callbacks = self.per_key_callbacks.get(k)
            if callbacks is None:
                return
            if pressed:
                self._handle_press(k, callbacks)
            else:
                self._handle_release(k, callbacks)

    def _is_double_press(self, k, callbacks):
        if callbacks.get('on_double_press') is None or k not in self.last_release_time:
            return False
        return time.time() - self.last_release_time[k] <= self.double_press_interval

    def _handle_press(self, k, callbacks):
        if self._is_double_press(k, callbacks):
            self._cancel_pending(self.pending_single_press, k)
            self._cancel_pending(self.pending_single_release, k)
            self._cancel_pending(self.pending_long_press, k)
            self._queue_callback(callbacks['on_double_press'], k)
            # A third press starts a new cycle rather than another double-press
            del self.last_release_time[k]
            self.release_skip_count[k] = 1
            return

        if callbacks.get('on_long_press') is not None:
            self.long_press_fired.discard(k)

            def long_press():
                self.long_press_fired.add(k)
                self._queue_callback(callbacks['on_long_press'], k)

            self._start_gesture_timer(self.pending_long_press, k,
                                      self.long_press_duration, long_press)
            return

        if not callbacks.get('on_press'):
            return
        if callbacks.get('on_double_press') is not None:
            self._start_gesture_timer(
                self.pending_single_press, k, self.double_press_interval + 0.01,
                lambda: self._queue_callback(callbacks['on_press'], k))
        else:
            self._queue_callback(callbacks['on_press'], k)

    def _handle_release(self, k, callbacks):
        if self.release_skip_count.get(k, 0) > 0:
            self.release_skip_count[k] -= 1
            if self.release_skip_count[k] == 0:
                del self.release_skip_count[k]
            return

        has_double_press = callbacks.get('on_double_press') is not None

        if callbacks.get('on_long_press') is not None:
            if k in self.long_press_fired:
                # The hold was the gesture; its release is not a tap, so it
                # must not open a double-press window either.
                self.long_press_fired.discard(k)
                return

            self._cancel_pending(self.pending_long_press, k)
            tap = [callbacks.get('on_press'), callbacks.get('on_release')]
            if has_double_press:
                self.last_release_time[k] = time.time()
                self._start_gesture_timer(
                    self.pending_single_press, k, self.double_press_interval + 0.01,
                    lambda: self._queue_in_order(tap, k))
            else:
                self._queue_in_order(tap, k)
            return

        if not has_double_press:
            if callbacks.get('on_release'):
                self._queue_callback(callbacks['on_release'], k)
            return

        self.last_release_time[k] = time.time()
        if callbacks.get('on_release'):
            self._start_gesture_timer(
                self.pending_single_release, k, self.double_press_interval + 0.01,
                lambda: self._queue_callback(callbacks['on_release'], k))

    def _read(self):
        while self.run_read_thread:
            try:
                arr=self.read(timeout_ms=1000)
                if arr is not None and len(arr) >= 10:
                    if arr[9]!=0xFF:
                        k = KEY_MAPPING[arr[9]]
                        new = arr[10]
                        if new == 0x02:
                            new = 0
                        if new == 0x01:
                            new = 1

                        # Call global callback if set (in worker pool)
                        if self.key_callback is not None:
                            self._event_queue.put((self.key_callback, (self, k, new)))

                        if new in (0, 1):
                            self._handle_key_event(k, new == 1)
                del arr
            except Exception:
                logger.exception("Error in read loop")
                self.run_read_thread = False
                self.close()

import threading
import logging
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
    1: 11,
    2: 12,
    3: 13,
    4: 14,
    5: 15,
    6: 6,
    7: 7,
    8: 8,
    9: 9,
    10: 10,
    11: 1,
    12: 2,
    13: 3,
    14: 4,
    15: 5,
}

# Default double-press detection interval (in seconds)
# This can be overridden via configuration
DEFAULT_DOUBLE_PRESS_INTERVAL = 0.3


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

    transport = None
    screenlicent = None
    __metaclass__ = ABCMeta
    __seconds = 300

    def __init__(self, transport1, devInfo):
        self.transport = transport1
        self.vendor_id = devInfo["vendor_id"]
        self.product_id = devInfo["product_id"]
        self.path = devInfo["path"]

        self.read_thread = None
        self.run_read_thread = False

        self.key_callback = None
        self.per_key_callbacks = {}  # Dictionary to store per-key callbacks

        # Double-press detection tracking
        self.last_release_time = {}  # Track last release time for each key
        self.pending_single_press = {}  # Track pending single press events
        self.pending_single_release = {}  # Track pending single release events
        self.double_press_detected = {}  # Track which keys had double-press detected
        self.release_skip_count = (
            {}
        )  # Track how many releases to skip after double-press

        # Double-press interval (can be configured)
        self.double_press_interval = DEFAULT_DOUBLE_PRESS_INTERVAL
        self.update_lock = threading.Lock()
        self._current_brightness = 50

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
        except TransportError:
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
        else:
            return k

    def open(self):
        self.transport.open(bytes(self.path, "utf-8"))
        self._setup_reader(self._read)

    def init(self):
        self.wakeScreen()
        self.set_brightness(100)
        self.clearAllIcon()
        self.refresh()

    def close(self):
        self.disconnected()

    def disconnected(self):
        self.transport.disconnected()

    def clearIcon(self, index):
        origin = index
        index = self.key(index)
        if index not in range(1, 16):
            logger.warning(f"key '{origin}' out of range. you should set (1 ~ 15)")
            return -1
        self.transport.keyClear(index)

    def clearAllIcon(self):
        self.transport.keyAllClear()

    def get_brightness(self):
        return self._current_brightness

    def wakeScreen(self):
        self.transport.wakeScreen()

    def refresh(self):
        self.transport.refresh()

    def getPath(self):
        return self.path

    def read(self):
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
                data = self.read()
                if data is not None and len(data) >= 11:
                    if data[:3].decode("utf-8", errors="ignore") == "ACK" and data[
                        5:7
                    ].decode("utf-8", errors="ignore"):
                        if data[10] == 0x01 and data[9] > 0x00 and data[9] <= 0x0F:
                            key_num = KEY_MAPPING[data[9]] if self.KEY_MAP else data[9]
                            logger.info(f"Key {key_num} pressed")
                        elif data[10] == 0x00 and data[9] > 0x00 and data[9] <= 0x0F:
                            key_num = KEY_MAPPING[data[9]] if self.KEY_MAP else data[9]
                            logger.info(f"Key {key_num} released")
            except Exception as e:
                logger.exception(f"Error in whileread: {e}")
                break

    def screen_Off(self):
        res = self.transport.screen_Off()
        self.reset_Countdown(self.__seconds)
        return res

    def screen_On(self):
        return self.transport.screen_On()

    def set_seconds(self, data):
        self.__seconds = data
        self.reset_Countdown(self.__seconds)

    def reset_Countdown(self, data):
        self.screenlicent.cancel()
        self.screenlicent = threading.Timer(data, self.screen_Off)
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
        return self.getPath()

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
        import asyncio

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
        pass

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
        import asyncio

        loop = loop or asyncio.get_event_loop()

        def callback(*args):
            asyncio.run_coroutine_threadsafe(async_callback(*args), loop)

        self.set_touchscreen_callback(callback)

    def set_per_key_callback(
        self, key, on_press=None, on_release=None, on_double_press=None
    ):
        """
        Sets the callback functions for a specific key on the StreamDock.
        You can register separate callbacks for press, release, and double-press events.

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
        """
        self.per_key_callbacks[key] = {
            "on_press": on_press,
            "on_release": on_release,
            "on_double_press": on_double_press,
        }

    def clear_key_callback(self, key):
        """
        Clears all callback functions for a specific key on the StreamDock.

        :param int key: The key number to clear callbacks for.
        """
        if key in self.per_key_callbacks:
            del self.per_key_callbacks[key]

        # Clean up any pending timers for this key
        if (
            key in self.pending_single_press
            and self.pending_single_press[key] is not None
        ):
            self.pending_single_press[key].cancel()
            del self.pending_single_press[key]

        if (
            key in self.pending_single_release
            and self.pending_single_release[key] is not None
        ):
            self.pending_single_release[key].cancel()
            del self.pending_single_release[key]

        if key in self.last_release_time:
            del self.last_release_time[key]

        if key in self.double_press_detected:
            del self.double_press_detected[key]

        if key in self.release_skip_count:
            del self.release_skip_count[key]

    def clear_all_callbacks(self):
        """
        Clears all per-key callback functions from the StreamDock.
        """
        # Cancel all pending timers
        for key in list(self.pending_single_press.keys()):
            if self.pending_single_press[key] is not None:
                self.pending_single_press[key].cancel()

        for key in list(self.pending_single_release.keys()):
            if self.pending_single_release[key] is not None:
                self.pending_single_release[key].cancel()

        # Clear all callback and tracking dictionaries
        self.per_key_callbacks.clear()
        self.pending_single_press.clear()
        self.pending_single_release.clear()
        self.last_release_time.clear()
        self.double_press_detected.clear()
        self.release_skip_count.clear()

    def _read(self):
        while self.run_read_thread:
            try:
                arr = self.read()
                if len(arr) >= 10:
                    if arr[9] != 0xFF:
                        k = KEY_MAPPING[arr[9]]
                        new = arr[10]
                        if new == 0x02:
                            new = 0
                        if new == 0x01:
                            new = 1

                        # Call global callback if set (in separate thread to avoid blocking)
                        if self.key_callback is not None:

                            def execute_global_callback():
                                self.key_callback(self, k, new)

                            global_callback_thread = threading.Thread(
                                target=execute_global_callback
                            )
                            global_callback_thread.daemon = True
                            global_callback_thread.start()

                        # Handle per-key callbacks with double-press detection
                        if k in self.per_key_callbacks:
                            callbacks = self.per_key_callbacks[k]

                            # Check if this key has double-press callback enabled
                            has_double_press = (
                                callbacks.get("on_double_press") is not None
                            )

                            # Handle key press (new == 1)
                            if new == 1:
                                # Only use double-press detection if on_double_press is set
                                if has_double_press:
                                    current_time = time.time()

                                    # Check if this is a double-press (press within interval after last release)
                                    if k in self.last_release_time:
                                        time_since_last_release = (
                                            current_time - self.last_release_time[k]
                                        )

                                        if (
                                            time_since_last_release
                                            <= self.double_press_interval
                                        ):
                                            # Double-press detected!
                                            # Cancel any pending single press callback from first press
                                            if (
                                                k in self.pending_single_press
                                                and self.pending_single_press[k]
                                                is not None
                                            ):
                                                self.pending_single_press[k].cancel()
                                                self.pending_single_press[k] = None

                                            # Cancel any pending single release callback from first press
                                            if (
                                                k in self.pending_single_release
                                                and self.pending_single_release[k]
                                                is not None
                                            ):
                                                self.pending_single_release[k].cancel()
                                                self.pending_single_release[k] = None

                                            # Call double-press callback in a separate thread to avoid blocking reader
                                            def execute_double_press():
                                                callbacks["on_double_press"](self, k)

                                            double_press_thread = threading.Thread(
                                                target=execute_double_press
                                            )
                                            double_press_thread.daemon = True
                                            double_press_thread.start()

                                            # Clear the last release time to prevent triple-press from being detected as another double-press
                                            del self.last_release_time[k]
                                            self.release_skip_count[k] = (
                                                1  # Skip the next release (from the second press)
                                            )
                                            continue

                                    # Not a double-press (yet) - delay on_press callback to wait for potential double-press
                                    if callbacks.get("on_press"):

                                        def delayed_press_callback():
                                            # Fire the callback only if it wasn't cancelled
                                            if (
                                                k in self.pending_single_press
                                                and self.pending_single_press[k]
                                                is not None
                                            ):
                                                callbacks["on_press"](self, k)
                                                self.pending_single_press[k] = None

                                        timer = threading.Timer(
                                            self.double_press_interval + 0.01,
                                            delayed_press_callback,
                                        )
                                        self.pending_single_press[k] = timer
                                        timer.start()
                                else:
                                    # No double-press callback, use immediate on_press in separate thread
                                    if callbacks.get("on_press"):

                                        def execute_press():
                                            callbacks["on_press"](self, k)

                                        press_thread = threading.Thread(
                                            target=execute_press
                                        )
                                        press_thread.daemon = True
                                        press_thread.start()

                            # Handle key release (new == 0)
                            elif new == 0:
                                # Check if we need to skip this release due to double-press
                                if (
                                    k in self.release_skip_count
                                    and self.release_skip_count[k] > 0
                                ):
                                    # Decrement the skip counter
                                    self.release_skip_count[k] -= 1
                                    # Clean up if all releases have been skipped
                                    if self.release_skip_count[k] == 0:
                                        del self.release_skip_count[k]
                                        # Also clean up the double_press_detected flag
                                        if k in self.double_press_detected:
                                            del self.double_press_detected[k]
                                    # Skip on_release callback entirely
                                    continue

                                # Record release time for double-press detection
                                if has_double_press:
                                    self.last_release_time[k] = time.time()

                                    # Delay on_release callback to wait for potential double-press
                                    if callbacks.get("on_release"):

                                        def delayed_release_callback():
                                            # Fire the callback only if it wasn't cancelled
                                            if (
                                                k in self.pending_single_release
                                                and self.pending_single_release[k]
                                                is not None
                                            ):
                                                callbacks["on_release"](self, k)
                                                self.pending_single_release[k] = None

                                        timer = threading.Timer(
                                            self.double_press_interval + 0.01,
                                            delayed_release_callback,
                                        )
                                        self.pending_single_release[k] = timer
                                        timer.start()
                                else:
                                    # No double-press callback, use immediate on_release in separate thread
                                    if callbacks.get("on_release"):

                                        def execute_release():
                                            callbacks["on_release"](self, k)

                                        release_thread = threading.Thread(
                                            target=execute_release
                                        )
                                        release_thread.daemon = True
                                        release_thread.start()
                del arr
            except Exception:
                self.run_read_thread = False
                self.close()
        pass

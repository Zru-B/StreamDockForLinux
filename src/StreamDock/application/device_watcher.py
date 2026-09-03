"""
Notice devices being plugged in and unplugged while running.

Removing the udev auto-start left nothing watching the USB bus, so a replug
used to mean restarting the application. This watches it instead, for both the
GUI and the headless runner.

Events are not matched on their properties: a udev "remove" event does not
reliably carry the vendor and product attributes an "add" does. Instead any
USB event triggers a re-enumeration, which is cheap and only happens when
something is actually plugged or unplugged.
"""

import logging
import threading
from typing import Callable, List, Optional

from StreamDock.application.device_discovery import device_key, discover_devices
from StreamDock.infrastructure.hardware_interface import DeviceInfo

logger = logging.getLogger(__name__)

# Plugging one device emits several events (usb_device, usb_interface,
# hidraw). Coalesce them, and give the kernel a moment to create the nodes
# before enumerating.
DEFAULT_DEBOUNCE = 0.4

# Used only when pyudev is unavailable.
DEFAULT_POLL_INTERVAL = 2.0


class DeviceWatcher:
    """
    Reports the attached Stream Docks whenever that set changes.

    Prefers udev events, falling back to polling so the feature still works
    where pyudev is missing.
    """

    def __init__(self, on_changed: Callable[[List[DeviceInfo]], None],
                 hardware=None,
                 debounce: float = DEFAULT_DEBOUNCE,
                 poll_interval: float = DEFAULT_POLL_INTERVAL):
        """
        Args:
            on_changed: Called with the full current device list whenever it
                changes. Runs on a background thread, so it must not touch a
                GUI directly.
            hardware: Hardware abstraction to enumerate through. A throwaway
                one is created per scan when omitted.
            debounce: Seconds to wait for related udev events to settle
            poll_interval: Seconds between scans in polling mode
        """
        self._on_changed = on_changed
        self._hardware = hardware
        self._debounce = debounce
        self._poll_interval = poll_interval

        self._devices: List[DeviceInfo] = []
        self._keys: set = set()
        self._lock = threading.RLock()

        self._observer = None
        self._monitor = None
        self._debounce_timer: Optional[threading.Timer] = None
        self._poll_thread: Optional[threading.Thread] = None
        self._running = False

    # ── lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> bool:
        """
        Begin watching.

        Returns:
            True if udev events are being used, False if polling. Either way
            the watcher is running.
        """
        if self._running:
            return self._observer is not None

        self._running = True
        # Seed the known set so the first real change is what gets reported.
        self._devices = self._scan()
        self._keys = {device_key(d) for d in self._devices}

        if self._start_udev():
            logger.info("Watching for device changes via udev")
            return True

        self._start_polling()
        logger.info("Watching for device changes by polling every %.1fs",
                    self._poll_interval)
        return False

    def stop(self) -> None:
        """Stop watching. Safe to call when not started."""
        self._running = False

        with self._lock:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
                self._debounce_timer = None

        if self._observer is not None:
            try:
                self._observer.stop()
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.debug("Error stopping udev observer: %s", e)
            self._observer = None
        self._monitor = None

        if self._poll_thread is not None:
            self._poll_thread.join(timeout=2)
            self._poll_thread = None

        logger.debug("Device watcher stopped")

    def devices(self) -> List[DeviceInfo]:
        """The devices seen at the last scan."""
        with self._lock:
            return list(self._devices)

    def refresh(self) -> None:
        """Scan now and report if anything changed."""
        self._rescan()

    # ── udev ──────────────────────────────────────────────────────────────

    def _start_udev(self) -> bool:
        """
        Subscribe to udev USB events.

        Returns:
            True if the subscription is live.
        """
        try:
            import pyudev  # pylint: disable=import-outside-toplevel
        except ImportError:
            logger.info("pyudev is not installed; falling back to polling")
            return False

        try:
            context = pyudev.Context()
            monitor = pyudev.Monitor.from_netlink(context)
            monitor.filter_by(subsystem='usb')
            observer = pyudev.MonitorObserver(
                monitor, callback=self._on_udev_event, name='device-watch')
            observer.daemon = True
            observer.start()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Could not subscribe to udev events (%s); polling instead", e)
            return False

        self._monitor = monitor
        self._observer = observer
        return True

    def _on_udev_event(self, device) -> None:
        """Coalesce a burst of udev events into one rescan."""
        if device.action not in ('add', 'remove', 'bind', 'unbind'):
            return

        with self._lock:
            if not self._running:
                return
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(self._debounce, self._rescan)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    # ── polling ───────────────────────────────────────────────────────────

    def _start_polling(self) -> None:
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name='device-poll', daemon=True)
        self._poll_thread.start()

    def _poll_loop(self) -> None:
        while self._running:
            # Sleep first: start() has just scanned.
            for _ in range(int(self._poll_interval * 10)):
                if not self._running:
                    return
                threading.Event().wait(0.1)
            self._rescan()

    # ── scanning ──────────────────────────────────────────────────────────

    def _scan(self) -> List[DeviceInfo]:
        try:
            return discover_devices(self._hardware)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error scanning for devices: %s", e)
            return []

    def _rescan(self) -> None:
        """Enumerate and report when the attached set has changed."""
        with self._lock:
            self._debounce_timer = None
            if not self._running:
                return

        devices = self._scan()
        keys = {device_key(d) for d in devices}

        with self._lock:
            if keys == self._keys:
                return
            added, removed = keys - self._keys, self._keys - keys
            self._devices, self._keys = devices, keys

        logger.info("Device change: %d attached (+%d, -%d)",
                    len(devices), len(added), len(removed))
        try:
            self._on_changed(devices)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error in device change handler: %s", e)

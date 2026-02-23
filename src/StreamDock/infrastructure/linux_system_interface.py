"""
Linux implementation of SystemInterface.

This module implements SystemInterface for Linux systems, wrapping the existing
WindowUtils class and providing D-Bus-based lock monitoring.
"""

import logging
import subprocess
import threading
from typing import Callable, Optional

from .system_interface import SystemInterface, WindowInfo

logger = logging.getLogger(__name__)


class LinuxSystemInterface(SystemInterface):
    """
    Linux implementation of SystemInterface.

    This class wraps the existing WindowUtils implementation and adds
    D-Bus-based lock monitoring, providing a clean adapter layer without
    modifying legacy code.

    Design Pattern: Adapter pattern - wraps WindowUtils without modification
    """

    def __init__(self):
        """Initialize Linux system interface."""
        self._lock_monitor_thread: Optional[threading.Thread] = None
        self._lock_monitor_callback: Optional[Callable[[bool], None]] = None
        self._lock_monitor_stop_event = threading.Event()
        logger.debug("LinuxSystemInterface initialized")

    # ==================== Tool Availability ====================

    def is_kdotool_available(self) -> bool:
        """Check if kdotool is available. Delegates to WindowUtils."""
        try:
            from StreamDock.window_utils import WindowUtils
            return WindowUtils.is_kdotool_available()
        except Exception as e:
            logger.error(f"Error checking kdotool availability: {e}")
            return False

    def is_xdotool_available(self) -> bool:
        """Check if xdotool is available. Delegates to WindowUtils."""
        try:
            from StreamDock.window_utils import WindowUtils
            return WindowUtils.is_xdotool_available()
        except Exception as e:
            logger.error(f"Error checking xdotool availability: {e}")
            return False

    def is_dbus_available(self) -> bool:
        """Check if dbus-send is available. Delegates to WindowUtils."""
        try:
            from StreamDock.window_utils import WindowUtils
            return WindowUtils.is_dbus_available()
        except Exception as e:
            logger.error(f"Error check dbus availability: {e}")
            return False

    def is_pactl_available(self) -> bool:
        """Check if pactl is available. Delegates to WindowUtils."""
        try:
            from StreamDock.window_utils import WindowUtils
            return WindowUtils.is_pactl_available()
        except Exception as e:
            logger.error(f"Error checking pactl availability: {e}")
            return False

    # ==================== Window Operations ====================

    def get_active_window(self) -> Optional[WindowInfo]:
        """
        Get active window using kdotool (preferred) or xdotool (fallback).

        Delegates to WindowUtils methods.
        """
        try:
            from StreamDock.window_utils import WindowUtils

            # Try kdotool first (Wayland/KDE)
            if self.is_kdotool_available():
                logger.debug("Getting active window with kdotool")
                window = WindowUtils.kdotool_get_active_window()
                if window:
                    return window

            # Fallback to xdotool (X11)
            if self.is_xdotool_available():
                logger.debug("Getting active window with xdotool")
                window = WindowUtils.xdotool_get_active_window()
                if window:
                    return window

            logger.warning("No window detection tools available")
            return None

        except Exception as e:
            logger.error(f"Error getting active window: {e}", exc_info=True)
            return None

    def search_window_by_class(self, class_name: str) -> Optional[str]:
        """
        Search for window by class name.

        Delegates to WindowUtils methods.
        """
        try:
            from StreamDock.window_utils import WindowUtils

            # Try kdotool first
            if self.is_kdotool_available():
                logger.debug(f"Searching for window class '{class_name}' with kdotool")
                window_id = WindowUtils.kdotool_search_by_class(class_name)
                if window_id:
                    return window_id

            # Fallback to xdotool
            if self.is_xdotool_available():
                logger.debug(f"Searching for window class '{class_name}' with xdotool")
                window_id = WindowUtils.xdotool_search_by_class(class_name)
                if window_id:
                    return window_id

            logger.debug(f"Window class '{class_name}' not found")
            return None

        except Exception as e:
            logger.error(f"Error searching for window: {e}", exc_info=True)
            return None

    def activate_window(self, window_id: str) -> bool:
        """
        Activate window by ID.

        Delegates to WindowUtils methods.
        """
        try:
            from StreamDock.window_utils import WindowUtils

            # Try kdotool first
            if self.is_kdotool_available():
                logger.debug(f"Activating window {window_id} with kdotool")
                return WindowUtils.kdotool_activate_window(window_id)

            # Fallback to xdotool
            if self.is_xdotool_available():
                logger.debug(f"Activating window {window_id} with xdotool")
                return WindowUtils.xdotool_activate_window(window_id)

            logger.warning("No window activation tools available")
            return False

        except Exception as e:
            logger.error(f"Error activating window: {e}", exc_info=True)
            return False

    # ==================== Input Simulation ====================

    def send_key_combo(self, key_sequence: str) -> bool:
        """
        Send keyboard shortcut.

        Delegates to xdotool (most reliable for key combos).
        """
        try:
            from StreamDock.window_utils import WindowUtils

            if not self.is_xdotool_available():
                logger.warning("xdotool not available for key combo")
                return False

            logger.debug(f"Sending key combo: {key_sequence}")
            return WindowUtils.xdotool_key(key_sequence)

        except Exception as e:
            logger.error(f"Error sending key combo: {e}", exc_info=True)
            return False

    def type_text(self, text: str) -> bool:
        """
        Type text into active window.

        Delegates to xdotool.
        """
        try:
            from StreamDock.window_utils import WindowUtils

            if not self.is_xdotool_available():
                logger.warning("xdotool not available for typing")
                return False

            logger.debug(f"Typing text: {text[:50]}...")
            WindowUtils.xdotool_type(text)
            return True

        except Exception as e:
            logger.error(f"Error typing text: {e}", exc_info=True)
            return False

    def execute_command(self, command: str) -> bool:
        """
        Execute shell command in background.
        """
        try:
            logger.info(f"Executing command: {command}")
            subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True  # Detach from parent process
            )
            return True

        except Exception as e:
            logger.error(f"Error executing command '{command}': {e}", exc_info=True)
            return False

    # ==================== Lock/Unlock Monitoring ====================

    def poll_lock_state(self) -> bool:
        """
        Poll D-Bus for current lock state.

        Tries KDE interface first, fallbacks to GNOME.
        """
        try:
            import dbus
            bus = dbus.SessionBus()

            # Try KDE/freedesktop interface
            try:
                proxy = bus.get_object('org.freedesktop.ScreenSaver', '/ScreenSaver')
                iface = dbus.Interface(proxy, 'org.freedesktop.ScreenSaver')
                is_locked = bool(iface.GetActive())
                logger.debug(f"Lock state (freedesktop): {is_locked}")
                return is_locked
            except dbus.DBusException:
                pass

            # Try GNOME interface
            try:
                proxy = bus.get_object('org.gnome.ScreenSaver', '/org/gnome/ScreenSaver')
                iface = dbus.Interface(proxy, 'org.gnome.ScreenSaver')
                is_locked = bool(iface.GetActive())
                logger.debug(f"Lock state (GNOME): {is_locked}")
                return is_locked
            except dbus.DBusException:
                pass

            logger.warning("No D-Bus screensaver interface available")
            return False

        except ImportError:
            logger.warning("dbus-python not available, cannot poll lock state")
            return False
        except Exception as e:
            logger.error(f"Error polling lock state: {e}", exc_info=True)
            return False

    def start_lock_monitor(self, callback: Callable[[bool], None]) -> bool:
        """
        Start monitoring lock/unlock events via D-Bus.

        Runs callback on background thread when lock state changes.
        """
        if self._lock_monitor_thread and self._lock_monitor_thread.is_alive():
            logger.warning("Lock monitor already running")
            return False

        try:
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop

            # Test D-Bus availability
            bus = dbus.SessionBus()

            self._lock_monitor_callback = callback
            self._lock_monitor_stop_event.clear()

            self._lock_monitor_thread = threading.Thread(
                target=self._lock_monitor_loop,
                daemon=True,
                name="LockMonitor"
            )
            self._lock_monitor_thread.start()

            logger.info("Lock monitor started")
            return True

        except ImportError:
            logger.error("dbus-python or GLib not available for lock monitoring")
            return False
        except Exception as e:
            logger.error(f"Error starting lock monitor: {e}", exc_info=True)
            return False

    def stop_lock_monitor(self) -> None:
        """Stop lock monitoring thread."""
        if self._lock_monitor_thread and self._lock_monitor_thread.is_alive():
            logger.info("Stopping lock monitor")
            self._lock_monitor_stop_event.set()
            self._lock_monitor_thread.join(timeout=2.0)
            self._lock_monitor_thread = None

        self._lock_monitor_callback = None

    def _lock_monitor_loop(self) -> None:
        """
        D-Bus monitoring loop (runs on background thread).

        Note: This is a simplified polling-based implementation.
        Production code should use GLib mainloop with signal handlers.
        """
        import time

        logger.debug("Lock monitor loop started")
        last_state = False

        try:
            while not self._lock_monitor_stop_event.is_set():
                current_state = self.poll_lock_state()

                if current_state != last_state:
                    logger.info(f"Lock state changed: {last_state} -> {current_state}")
                    if self._lock_monitor_callback:
                        try:
                            self._lock_monitor_callback(current_state)
                        except Exception as e:
                            logger.error(f"Error in lock monitor callback: {e}", exc_info=True)
                    last_state = current_state

                # Poll every second
                self._lock_monitor_stop_event.wait(timeout=1.0)

        except Exception as e:
            logger.error(f"Error in lock monitor loop: {e}", exc_info=True)
        finally:
            logger.debug("Lock monitor loop stopped")

    # ==================== Media Controls ====================

    def send_media_key(self, key: str) -> bool:
        """
        Send media control key.

        Uses xdotool to simulate media keys.
        """
        try:
            # Map friendly names to X key symbols
            key_map = {
                'PlayPause': 'XF86AudioPlay',
                'Play': 'XF86AudioPlay',
                'Pause': 'XF86AudioPause',
                'Next': 'XF86AudioNext',
                'Previous': 'XF86AudioPrev',
                'Stop': 'XF86AudioStop',
            }

            x_key = key_map.get(key, key)
            logger.debug(f"Sending media key: {key} ({x_key})")

            return self.send_key_combo(x_key)

        except Exception as e:
            logger.error(f"Error sending media key: {e}", exc_info=True)
            return False

    def set_volume(self, volume: int) -> bool:
        """
        Set system volume using pactl.

        Args:
            volume: Volume level 0-100
        """
        if not self.is_pactl_available():
            logger.warning("pactl not available for volume control")
            return False

        # Clamp volume to valid range
        volume = max(0, min(100, volume))

        try:
            logger.debug("Setting volume to %d%%", volume)
            result = subprocess.run(
                ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{volume}%'],
                capture_output=True,
                timeout=5.0
            )

            if result.returncode == 0:
                logger.debug("Volume set to %d%%", volume)
                return True
            
            logger.warning("pactl failed: %s", result.stderr.decode())
            return False

        except Exception as e:
            logger.error("Error setting volume: %s", e, exc_info=True)
            return False

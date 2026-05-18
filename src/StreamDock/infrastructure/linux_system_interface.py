"""
Linux implementation of SystemInterface.

Provides methods for input simulation, volume control, process checking,
and lock monitoring using Linux subprocesses and DBus. Window operations
are handled separately by ``LinuxWindowManager``.
"""

import logging
import shutil
import subprocess
import threading
from typing import Callable, Optional, Union

from .system_interface import SystemInterface, WindowInfo
from .window_interface import WindowInterface
from .linux_window_manager import LinuxWindowManager

logger = logging.getLogger(__name__)


class LinuxSystemInterface(SystemInterface):
    """
    Linux implementation of SystemInterface.

    Uses ``xdotool`` for input simulation, ``pactl`` for volume, ``pgrep``
    for process checking, and ``dbus`` for screensaver lock monitoring.
    """

    def __init__(self) -> None:
        """Initialise the Linux system interface."""
        self._lock_monitor_thread: Optional[threading.Thread] = None
        self._lock_monitor_callback: Optional[Callable[[bool], None]] = None
        self._lock_monitor_stop_event = threading.Event()
        logger.debug("LinuxSystemInterface initialised")

    # ------------------------------------------------------------------ #
    # Process / Execution                                                  #
    # ------------------------------------------------------------------ #

    def is_process_running(self, process_name: str) -> bool:
        """Return True if a process named *process_name* is running."""
        try:
            r = subprocess.run(
                ["pgrep", "-x", process_name],
                capture_output=True, text=True, timeout=1,
            )
            return r.returncode == 0 and bool(r.stdout.strip())
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    # ------------------------------------------------------------------ #
    # Input simulation                                                     #
    # ------------------------------------------------------------------ #

    def send_key_combo(self, key_sequence: str) -> bool:
        """Send a keyboard shortcut via xdotool."""
        try:
            subprocess.run(
                ["xdotool", "key", key_sequence],
                check=True, capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as exc:
            logger.error("Error pressing key combination: %s", exc)
            return False
        except FileNotFoundError:
            logger.warning("xdotool not found; cannot send key combo")
            return False
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Unexpected error in send_key_combo: %s", exc)
            return False

    def type_text(self, text: str) -> bool:
        """Type *text* into the currently focused window via xdotool."""
        try:
            # xdotool sometimes drops Shift modifiers when --clearmodifiers is used 
            # alongside a very short --delay (in milliseconds). Increasing delay and relying on native behavior.
            subprocess.run(
                ["xdotool", "type", "--delay", "12", "--", text],
                check=True, capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as exc:
            logger.error("xdotool type failed: %s", exc)
            return False
        except FileNotFoundError:
            logger.warning("xdotool not found; cannot type text")
            return False
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Unexpected error in type_text: %s", exc)
            return False

    def execute_command(self, command: str) -> bool:
        """Execute *command* in the background, fully detached."""
        try:
            logger.info("Executing command: %s", command)
            subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Error executing command '%s': %s", command, exc, exc_info=True)
            return False

    # ------------------------------------------------------------------ #
    # Lock / Unlock monitoring                                             #
    # ------------------------------------------------------------------ #

    def poll_lock_state(self) -> bool:
        """Poll the D-Bus screensaver interface for the current lock state."""
        try:
            import dbus  # pylint: disable=import-outside-toplevel
            bus = dbus.SessionBus()
            for service, path, iface in [
                ("org.freedesktop.ScreenSaver", "/ScreenSaver",
                 "org.freedesktop.ScreenSaver"),
                ("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver",
                 "org.gnome.ScreenSaver"),
            ]:
                try:
                    proxy = bus.get_object(service, path)
                    return bool(dbus.Interface(proxy, iface).GetActive())
                except dbus.DBusException:
                    continue
            logger.warning("No D-Bus screensaver interface available")
            return False
        except ImportError:
            logger.warning("dbus-python not available; cannot poll lock state")
            return False
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Error polling lock state: %s", exc, exc_info=True)
            return False

    def start_lock_monitor(self, callback: Callable[[bool], None]) -> bool:
        """Start a background thread that fires *callback* on lock-state changes."""
        if self._lock_monitor_thread and self._lock_monitor_thread.is_alive():
            logger.warning("Lock monitor already running")
            return False
        try:
            import dbus  # noqa: F401  pylint: disable=import-outside-toplevel
            self._lock_monitor_callback = callback
            self._lock_monitor_stop_event.clear()
            self._lock_monitor_thread = threading.Thread(
                target=self._lock_monitor_loop, daemon=True, name="LockMonitor",
            )
            self._lock_monitor_thread.start()
            logger.info("Lock monitor started")
            return True
        except ImportError:
            logger.error("dbus-python not available for lock monitoring")
            return False
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Error starting lock monitor: %s", exc, exc_info=True)
            return False

    def stop_lock_monitor(self) -> None:
        """Stop the lock-monitor background thread."""
        if self._lock_monitor_thread and self._lock_monitor_thread.is_alive():
            self._lock_monitor_stop_event.set()
            self._lock_monitor_thread.join(timeout=2.0)
            self._lock_monitor_thread = None
        self._lock_monitor_callback = None

    def _lock_monitor_loop(self) -> None:
        logger.debug("Lock monitor loop started")
        last_state = False
        while not self._lock_monitor_stop_event.is_set():
            try:
                current_state = self.poll_lock_state()
                if current_state != last_state:
                    logger.info("Lock state changed: %s -> %s", last_state, current_state)
                    if self._lock_monitor_callback:
                        try:
                            self._lock_monitor_callback(current_state)
                        except Exception as exc:  # pylint: disable=broad-exception-caught
                            logger.error("Lock monitor callback error: %s", exc, exc_info=True)
                    last_state = current_state
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.error("Error in lock monitor loop: %s", exc, exc_info=True)
            self._lock_monitor_stop_event.wait(timeout=1.0)
        logger.debug("Lock monitor loop stopped")

    # ------------------------------------------------------------------ #
    # Media & volume controls                                              #
    # ------------------------------------------------------------------ #

    def send_media_key(self, key: str) -> bool:
        """Simulate a media key (PlayPause, Next, Previous, Stop)."""
        key_map = {
            "PlayPause": "XF86AudioPlay",
            "Play":      "XF86AudioPlay",
            "Pause":     "XF86AudioPause",
            "Next":      "XF86AudioNext",
            "Previous":  "XF86AudioPrev",
            "Stop":      "XF86AudioStop",
        }
        return self.send_key_combo(key_map.get(key, key))

    def set_volume(self, volume: Union[int, str]) -> bool:
        """Set the system volume via pactl."""
        if shutil.which("pactl") is None:
            logger.warning("pactl not available for volume control")
            return False
        volume_str = (
            f"{max(0, min(100, volume))}%" if isinstance(volume, int) else volume
        )
        try:
            r = subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", volume_str],
                capture_output=True, timeout=5.0,
            )
            if r.returncode == 0:
                return True
            logger.warning("pactl set-sink-volume failed: %s", r.stderr.decode())
            return False
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Error setting volume: %s", exc, exc_info=True)
            return False

    def toggle_mute(self) -> bool:
        """Toggle system mute state via pactl."""
        if shutil.which("pactl") is None:
            logger.warning("pactl not available for volume control")
            return False
        try:
            r = subprocess.run(
                ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
                capture_output=True, timeout=5.0,
            )
            if r.returncode == 0:
                return True
            logger.warning("pactl set-sink-mute failed: %s", r.stderr.decode())
            return False
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Error toggling mute: %s", exc, exc_info=True)
            return False

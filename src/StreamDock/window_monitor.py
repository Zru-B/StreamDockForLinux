"""
Window monitoring for KDE Plasma Wayland to detect active window and trigger layout changes.
"""

import logging
import re
import shutil
import subprocess
import threading
import time
from typing import Callable, Optional

from StreamDock.Models import WindowInfo, AppPattern
from StreamDock.WindowUtils import WindowUtils

logger = logging.getLogger(__name__)


class WindowMonitor:
    """
    Monitor the active window on KDE Plasma (Wayland) and trigger callbacks when focus changes.
    """

    def __init__(self, poll_interval: float = 0.5, simulation_mode: bool = False):
        """
        Initialize the window monitor.

        :param poll_interval: How often to check for window changes (in seconds)
        :param simulation_mode: If True, read active window from a file instead of system
        """
        self.poll_interval: float = poll_interval
        self.current_window_id: Optional[str] = None
        self.current_window_detection_method: Optional[str] = None
        self.window_rules: list[dict] = []
        self.running: bool = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.default_callback: Optional[Callable[[WindowInfo], None]] = None
        self.simulation_mode: bool = simulation_mode
        self.simulated_window_file: str = "/tmp/streamdock_fake_window"
        self.kdotool_available: bool = False
        
        if self.simulation_mode:
            self.kdotool_available = False
            logger.info(f"WindowMonitor running in SIMULATION MODE. Reading from {self.simulated_window_file}")
        else:
            # Use WindowUtils for tool availability checking
            self.kdotool_available = WindowUtils.is_kdotool_available()

    def get_active_window_info(self) -> WindowInfo | None:
        """
        Get information about the currently active window using multiple methods.
        Tries different approaches for KDE Plasma 6 Wayland compatibility.

        :return: WindowInfo object with window info, or None if unable to get window info
        """
        self.current_window_detection_method = None

        # Method 0: Simulation Mode
        if self.simulation_mode:
            return self._try_simulation()

        # Try multiple methods in order of reliability
        # Method 1: Try kdotool (best for KDE Wayland)
        if self.kdotool_available:
            window_info = WindowUtils.kdotool_get_active_window()
            if window_info:
                self.current_window_detection_method = "kdotool"
                return window_info

        # Method 2: Try KWin D-Bus scripting interface
        window_info = self._try_kwin_scripting()
        if window_info:
            self.current_window_detection_method = "kwin_scripting"
            return window_info

        # Method 3: Try parsing plasma-workspace
        window_info = self._try_plasma_taskmanager()
        if window_info:
            self.current_window_detection_method = "plasma_taskmanager"
            return window_info

        # Method 4: Fallback to basic KWin interface
        window_info = self._try_kwin_basic()
        if window_info:
            self.current_window_detection_method = "kwin_basic"
            return window_info

        return None

    def _try_simulation(self) -> WindowInfo | None:
        """Read active window from simulation file."""
        import os
        try:
            if not os.path.exists(self.simulated_window_file):
                return None
                
            with open(self.simulated_window_file, 'r') as f:
                content = f.read().strip()
                
            if not content:
                return None
                
            # Content format: "Title|Class" or just "Class"
            parts = content.split('|')
            if len(parts) == 2:
                title, win_class = parts
            else:
                title = content
                win_class = content
                
            return WindowInfo(
                title=title,
                class_name=win_class,
                raw=content,
                method="simulation"
            )
        except Exception as e:
            logger.error(f"Error reading simulation file: {e}")
            return None

    def _try_kwin_scripting(self) -> WindowInfo | None:
        """Try using KWin scripting D-Bus interface."""
        try:
            # Use KWin's client API through D-Bus
            script = """
            var client = workspace.activeClient;
            if (client) {
                print(client.caption + '|||' + client.resourceClass);
            }
            """

            result = subprocess.run(
                [
                    "qdbus",
                    "org.kde.KWin",
                    "/Scripting",
                    "org.kde.kwin.Scripting.loadScript",
                    script,
                    "temp",
                ],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )

            # This method might not work directly, skip for now
            return None

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return None

    def _try_plasma_taskmanager(self) -> WindowInfo | None:
        """Try getting info from plasma task manager."""
        try:
            # Query plasma shell for active window
            result = subprocess.run(
                [
                    "qdbus",
                    "org.kde.plasmashell",
                    "/PlasmaShell",
                    "org.kde.PlasmaShell.evaluateScript",
                    "var taskmanager = panelById(panelIds[0]); taskmanager;",
                ],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )

            # This is complex, skip for now
            return None

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return None

    def _try_kwin_basic(self) -> WindowInfo | None:
        """Try basic KWin D-Bus interface - using Plasma 6 compatible method."""
        try:
            # For KDE Plasma 6, we need to use a different approach
            # Try to get list of windows and find the active one

            # Method 1: Try using qdbus6 (Plasma 6 uses Qt6)
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    'qdbus6 org.kde.KWin /KWin org.kde.KWin.activeWindow 2>/dev/null '
                    '|| qdbus org.kde.KWin /KWin org.kde.KWin.activeWindow 2>/dev/null || echo ""',
                ],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )

            if result.returncode == 0 and result.stdout.strip():
                # Check if the output is actually an error message
                raw_output = result.stdout.strip()
                if "Error" in raw_output or "No such method" in raw_output:
                    # Fall through to next method
                    pass
                else:
                    window_title = raw_output
                    window_class = WindowUtils.extract_app_from_title(window_title)

                    return WindowInfo(
                        title=window_title,
                        class_name=window_class,
                        raw=window_title,
                        method="kwin_plasma6",
                    )

            # Method 2: Try using busctl to query KWin
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    'busctl --user get-property org.kde.KWin /KWin org.kde.KWin ActiveWindow '
                    '2>/dev/null || echo ""',
                ],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )

            if (
                result.returncode == 0
                and result.stdout.strip()
                and "Error" not in result.stdout
            ):
                window_title = result.stdout.strip()
                # Remove busctl formatting
                if window_title.startswith("s "):
                    window_title = window_title[2:].strip('"')

                window_class = WindowUtils.extract_app_from_title(window_title)

                return WindowInfo(
                    title=window_title,
                    class_name=window_class,
                    raw=window_title,
                    method="busctl",
                )

            # Method 3: Try using xdotool (X11 fallback)
            result = subprocess.run(
                ["bash", "-c", 'xdotool getactivewindow 2>/dev/null || echo ""'],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )

            if result.returncode == 0 and result.stdout.strip():
                window_id = result.stdout.strip()

                # Get window title
                result_title = subprocess.run(
                    ["xdotool", "getwindowname", window_id],
                    capture_output=True,
                    text=True,
                    timeout=1,
                    check=False,
                )

                window_title = result_title.stdout.strip() if result_title.returncode == 0 else ""

                # Get window class (WM_CLASS)
                result_class = subprocess.run(
                    ["xdotool", "getwindowclassname", window_id],
                    capture_output=True,
                    text=True,
                    timeout=1,
                    check=False,
                )

                if result_class.returncode == 0 and result_class.stdout.strip():
                    raw_class = result_class.stdout.strip()
                    window_class = WindowUtils.normalize_class_name(raw_class, window_title)
                else:
                    window_class = WindowUtils.extract_app_from_title(window_title)

                return WindowInfo(
                    title=window_title,
                    class_name=window_class,
                    raw=window_title,
                    method="kwin_basic",
                )

            return None

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return None

    def add_window_rule(self, pattern: str | re.Pattern, callback: Callable[[WindowInfo], None], match_field: str = "class") -> None:
        """
        Add a rule that triggers a callback when a window matching the pattern is focused.

        :param pattern: String or regex pattern to match against window info
        :param callback: Function to call when pattern matches. Signature: callback(window_info: WindowInfo)
        :param match_field: Which field to match against: 'title', 'class', or 'raw'
        """
        rule = {
            "pattern": pattern,
            "callback": callback,
            "match_field": match_field,
            "is_regex": isinstance(pattern, re.Pattern),
        }
        self.window_rules.append(rule)

    def set_default_callback(self, callback: Callable[[WindowInfo], None]) -> None:
        """
        Set a callback to trigger when no window rules match.

        :param callback: Function to call when no rules match. Signature: callback(window_info: WindowInfo)
        """
        self.default_callback = callback

    def _check_rules(self, window_info: WindowInfo) -> None:
        """
        Check if any rules match the current window and execute callbacks.

        :param window_info: WindowInfo object with window information
        """
        if not window_info:
            return

        matched = False

        for rule in self.window_rules:
            # Get field value from WindowInfo dataclass
            if rule["match_field"] == "class":
                field_value = window_info.class_name
            elif rule["match_field"] == "title":
                field_value = window_info.title
            elif rule["match_field"] == "raw":
                field_value = window_info.raw
            else:
                field_value = ""
            
            pattern = rule["pattern"]

            # Check if pattern matches
            match = False
            if rule["is_regex"]:
                match = pattern.search(field_value) is not None
            else:
                match = pattern.lower() in field_value.lower()

            if match:
                matched = True
                try:
                    logger.debug("Window rule matched: %s", window_info)
                    rule["callback"](window_info)
                except Exception as exc:
                    logger.exception("Error executing window rule callback: %s", exc)
                break  # Only trigger first matching rule

        # If no rules matched, call default callback
        if not matched and self.default_callback:
            try:
                logger.debug("No window rule matched, default callback triggered: %s", window_info.class_name)
                self.default_callback(window_info)
            except Exception as exc:
                logger.exception("Error executing default callback: %s", exc)

    def _monitor_loop(self) -> None:
        """
        Main monitoring loop that runs in a separate thread.
        """
        while self.running:
            try:
                window_info = self.get_active_window_info()

                # Check if window has changed
                if window_info:
                    window_id = window_info.class_name

                    if window_id != self.current_window_id:
                        logger.info("Window changed: (detected by %s) %s", self.current_window_detection_method, window_info.class_name)
                        self.current_window_id = window_id
                        self._check_rules(window_info)

                time.sleep(self.poll_interval)

            except Exception as exc:
                logger.exception("Error in window monitor: %s", exc)
                time.sleep(self.poll_interval)

    def start(self) -> None:
        """
        Start monitoring window focus changes in a background thread.
        """
        if self.running:
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop(self) -> None:
        """
        Stop monitoring window focus changes.
        """
        if not self.running:
            return

        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)

    def clear_rules(self) -> None:
        """
        Clear all window rules.
        """
        self.window_rules.clear()

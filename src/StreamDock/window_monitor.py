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

from StreamDock.Models import AppPattern, WindowInfo
from StreamDock.window_utils import WindowUtils
from StreamDock.window_detection import (
    DetectionMethod,
    KdotoolDetection,
    KWinDynamicScriptingDetection,
    PlasmaTaskManagerDetection,
    KWinBasicDetection,
    XWindowDetection,
    SimulationDetection
)

logger = logging.getLogger(__name__)


def _timed(func_name=None):
    """Decorator to log function execution time."""
    def decorator(func):
        name = func_name or func.__name__
        def wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            elapsed = (time.time() - start) * 1000
            logger.debug(f"{name} took {elapsed:.1f}ms")
            return result
        return wrapper
    return decorator


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

        # Initialize detection strategies
        self.strategies: list[DetectionMethod] = []
        
        if self.simulation_mode:
            logger.info(f"WindowMonitor running in SIMULATION MODE. Reading from {self.simulated_window_file}")
            self.strategies.append(SimulationDetection(self.simulated_window_file))
        else:
            # Order matters: preferred methods first
            self.strategies = [
                KWinDynamicScriptingDetection(),
                KdotoolDetection(),
                PlasmaTaskManagerDetection(),
                KWinBasicDetection(),
                XWindowDetection()
            ]

    def get_active_window_info(self) -> WindowInfo | None:
        """
        Get information about the currently active window using multiple methods.
        Tries different approaches for KDE Plasma 6 Wayland compatibility.

        :return: WindowInfo object with window info, or None if unable to get window info
        """
        self.current_window_detection_method = None

        for strategy in self.strategies:
            if not strategy.is_available:
                continue

            try:
                window_info = strategy.detect()
                if window_info:
                    self.current_window_detection_method = strategy.name
                    return window_info
            except Exception as e:
                logger.error(f"Error in strategy {strategy.name}: {e}")

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
            try:
                field_value = window_info.get(rule["match_field"])
            except KeyError:
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
                        logger.debug("Window changed: %s. Detected by %s", window_info.class_name, self.current_window_detection_method)
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
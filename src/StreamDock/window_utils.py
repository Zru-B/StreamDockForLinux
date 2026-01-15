"""
Window utilities for detecting, searching, and manipulating windows.

This module provides a unified interface for window operations across different
display servers (Wayland/KDE and X11) using kdotool and xdotool.

Tool availability is cached on first use for optimal runtime performance.
"""

import logging
import shutil
import subprocess
from typing import Optional

from StreamDock.Models import AppPattern, WindowInfo

logger = logging.getLogger(__name__)

# Module-level cache for tool availability
_kdotool_available: Optional[bool] = None
_xdotool_available: Optional[bool] = None
_wmctrl_available: Optional[bool] = None
_dbus_available: Optional[bool] = None
_pactl_available: Optional[bool] = None

# Application patterns for class name normalization
# Patterns are checked in order, first match wins
APP_PATTERNS = [
    AppPattern([" antigravity"], "Antigravity"),
    AppPattern(["chrome"], "Chrome"),
    AppPattern(["chromium"], "Chromium"),
    AppPattern(["code"], "VSCode"),
    AppPattern(["discord"], "Discord"),
    AppPattern(["dolphin"], "Dolphin"),
    AppPattern(["firefox"], "Firefox"),
    AppPattern(["intellij"], "IntelliJ"),
    AppPattern(["kate"], "Kate"),
    AppPattern(["konsole"], "Konsole", exact_matches=["org.kde.konsole"]),
    AppPattern(["obsidian"], "Obsidian"),
    AppPattern(["pycharm"], "PyCharm"),
    AppPattern(["slack"], "Slack"),
    AppPattern(["spotify"], "Spotify"),
    AppPattern(["telegram", "telegram-desktop"], "Telegram"),
    AppPattern(["yakuake"], "Yakuake", exact_matches=["org.kde.yakuake"]),
    AppPattern(["zoom", "zoom workplace"], "Zoom"),
]


class WindowUtils:
    """Shared utilities for window detection and manipulation."""

    @staticmethod
    def is_kdotool_available() -> bool:
        """
        Check if kdotool is available and functional.
        
        Result is cached on first call for performance.
        
        :return: True if kdotool is available and working, False otherwise
        """
        global _kdotool_available
        
        if _kdotool_available is not None:
            return _kdotool_available
        
        # Check if kdotool exists
        if shutil.which("kdotool") is None:
            logger.debug("kdotool not found in PATH")
            _kdotool_available = False
            return False
        
        # Test if kdotool actually works (it might panic on some systems)
        try:
            result = subprocess.run(
                ["kdotool", "getactivewindow"],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            
            if result.returncode != 0:
                logger.debug(f"kdotool test failed with return code {result.returncode}")
                _kdotool_available = False
                return False
            
            logger.info("kdotool found and functional")
            _kdotool_available = True
            return True
            
        except Exception as exc:
            logger.debug(f"kdotool test failed: {exc}")
            _kdotool_available = False
            return False

    @staticmethod
    def is_xdotool_available() -> bool:
        """
        Check if xdotool is available and functional.
        
        Result is cached on first call for performance.
        
        :return: True if xdotool is available and working, False otherwise
        """
        global _xdotool_available
        
        if _xdotool_available is not None:
            return _xdotool_available
        
        # Check if xdotool exists
        if shutil.which("xdotool") is None:
            logger.debug("xdotool not found in PATH")
            _xdotool_available = False
            return False
        
        # Test if xdotool actually works
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            
            # xdotool might return non-zero if no X11 session, but that's ok
            # We just care that it executes without crashing
            logger.info("xdotool found and functional")
            _xdotool_available = True
            return True
            
        except Exception as exc:
            logger.debug(f"xdotool test failed: {exc}")
            _xdotool_available = False
            return False

    @staticmethod
    def is_wmctrl_available() -> bool:
        """
        Check if wmctrl is available and functional.
        
        Result is cached on first call for performance.
        
        :return: True if wmctrl is available, False otherwise
        """
        global _wmctrl_available
        
        if _wmctrl_available is not None:
            return _wmctrl_available
        
        # Check if wmctrl exists
        if shutil.which("wmctrl") is None:
            logger.debug("wmctrl not found in PATH")
            _wmctrl_available = False
            return False
            
        _wmctrl_available = True
        return True

    @staticmethod
    def refresh_tool_cache() -> None:
        """
        Refresh the cached tool availability status.
        
        Call this if tools are installed/uninstalled during runtime.
        """
        global _kdotool_available, _xdotool_available, _wmctrl_available, _dbus_available, _pactl_available
        _kdotool_available = None
        _xdotool_available = None
        _wmctrl_available = None
        _dbus_available = None
        _pactl_available = None
        logger.debug("Tool availability cache refreshed")

    @staticmethod
    def is_dbus_available() -> bool:
        """
        Check if dbus-send is available.
        
        :return: True if dbus-send is available, False otherwise
        """
        global _dbus_available
        
        if _dbus_available is not None:
            return _dbus_available
            
        if shutil.which("dbus-send") is None:
            logger.debug("dbus-send not found in PATH")
            _dbus_available = False
            return False
            
        _dbus_available = True
        return True

    @staticmethod
    def is_pactl_available() -> bool:
        """
        Check if pactl is available.
        
        :return: True if pactl is available, False otherwise
        """
        global _pactl_available
        
        if _pactl_available is not None:
            return _pactl_available
            
        if shutil.which("pactl") is None:
            logger.debug("pactl not found in PATH")
            _pactl_available = False
            return False
            
        _pactl_available = True
        return True

    # ========== kdotool operations ==========

    @staticmethod
    def kdotool_get_active_window() -> Optional[WindowInfo]:
        """
        Get the currently active window using kdotool.
        
        :return: WindowInfo object with window details, or None if failed
        """
        if not WindowUtils.is_kdotool_available():
            return None
        
        try:
            # Get window ID
            result = subprocess.run(
                ["kdotool", "getactivewindow"],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            
            if result.returncode != 0:
                return None
            
            window_id = result.stdout.strip()
            
            # Get window title
            result = subprocess.run(
                ["kdotool", "getwindowname", window_id],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            
            if result.returncode != 0:
                return None
            
            window_info = WindowInfo(
                title=result.stdout.strip(),
                class_="",
                raw=result.stdout.strip(),
                method="kdotool"
            )
            
            # Try to get actual window class
            result_class = subprocess.run(
                ["kdotool", "getwindowclassname", window_id],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            
            if result_class.returncode == 0 and result_class.stdout.strip():
                raw_class = result_class.stdout.strip()
                window_info.class_ = WindowUtils.normalize_class_name(raw_class, window_info.title)
                logger.debug(f"kdotool: title={window_info.title}, raw_class={raw_class}, normalized={window_info.class_}")
            else:
                # Fallback to extracting from title
                window_info.class_ = WindowUtils.extract_app_from_title(window_info.title)
                logger.debug(f"kdotool: title={window_info.title}, class={window_info.class_}")
            
            return window_info
            
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as exc:
            logger.debug(f"kdotool_get_active_window failed: {exc}")
            return None

    @staticmethod
    def kdotool_search_by_class(class_name: str) -> Optional[str]:
        """
        Search for a window by class name using kdotool.
        
        :param class_name: Window class name to search for
        :return: Window ID if found, None otherwise
        """
        if not WindowUtils.is_kdotool_available():
            return None
        
        try:
            result = subprocess.run(
                ["kdotool", "search", "--class", class_name],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                window_id = result.stdout.strip().split("\n")[0]
                logger.debug(f"Found window (kdotool): {window_id} for class '{class_name}'")
                return window_id
            
            return None
            
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.debug(f"kdotool_search_by_class failed: {exc}")
            return None

    @staticmethod
    def kdotool_search_by_name(name: str) -> Optional[str]:
        """
        Search for a window by name using kdotool.
        
        :param name: Window name to search for
        :return: Window ID if found, None otherwise
        """
        if not WindowUtils.is_kdotool_available():
            return None
        
        try:
            result = subprocess.run(
                ["kdotool", "search", "--name", name],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                window_id = result.stdout.strip().split("\n")[0]
                logger.debug(f"Found window (kdotool): {window_id} for name '{name}'")
                return window_id
            
            return None
            
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.debug(f"kdotool_search_by_name failed: {exc}")
            return None

    @staticmethod
    def kdotool_activate_window(window_id: str) -> bool:
        """
        Activate (focus) a window using kdotool.
        
        :param window_id: Window ID to activate
        :return: True if successful, False otherwise
        """
        if not WindowUtils.is_kdotool_available():
            return False
        
        try:
            result = subprocess.run(
                ["kdotool", "windowactivate", window_id],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            )
            
            logger.debug(f"Activated window (kdotool): {window_id}")
            return True
            
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            logger.debug(f"kdotool_activate_window failed: {exc}")
            return False

    # ========== xdotool operations ==========

    @staticmethod
    def xdotool_get_active_window() -> Optional[WindowInfo]:
        """
        Get the currently active window using xdotool.
        
        :return: WindowInfo object with window details, or None if failed
        """
        if not WindowUtils.is_xdotool_available():
            return None
        
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            
            if result.returncode != 0 or not result.stdout.strip():
                return None
            
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
                class_=window_class,
                raw=window_title,
                method="xdotool",
            )
            
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as exc:
            logger.debug(f"xdotool_get_active_window failed: {exc}")
            return None

    @staticmethod
    def xdotool_search_by_class(class_name: str) -> Optional[str]:
        """
        Search for a window by class name using xdotool.
        
        :param class_name: Window class name to search for
        :return: Window ID of the first found window, None otherwise
        """
        if not WindowUtils.is_xdotool_available():
            return None
        
        try:
            result = subprocess.run(
                ["xdotool", "search", "--all", "--onlyvisible", "--class", class_name],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                window_id = result.stdout.strip().split("\n")[0]
                logger.debug(f"Found window (xdotool): {window_id} for class '{class_name}'")
                return window_id
            
            return None
            
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.debug(f"xdotool_search_by_class failed: {exc}")
            return None

    @staticmethod
    def xdotool_search_by_name(name: str) -> Optional[str]:
        """
        Search for a window by name using xdotool.
        
        :param name: Window name to search for
        :return: Window ID of the first found window, None otherwise
        """
        if not WindowUtils.is_xdotool_available():
            return None
        
        try:
            result = subprocess.run(
                ["xdotool", "search", "--all", "--name", name],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                window_id = result.stdout.strip().split("\n")[0]
                logger.debug(f"Found window (xdotool): {window_id} for name '{name}'")
                return window_id
            
            return None
            
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.debug(f"xdotool_search_by_name failed: {exc}")
            return None

    @staticmethod
    def xdotool_activate_window(window_id: str) -> bool:
        """
        Activate (focus) a window using xdotool.
        
        :param window_id: Window ID to activate
        :return: True if successful, False otherwise
        """
        if not WindowUtils.is_xdotool_available():
            return False
        
        try:
            result = subprocess.run(
                ["xdotool", "windowactivate", window_id],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            )
            
            logger.debug(f"Activated window (xdotool): {window_id}")
            return True
            
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            logger.debug(f"xdotool_activate_window failed: {exc}")
            return False

    @staticmethod
    def xdotool_key(key_sequence: str) -> bool:
        """
        Simulate key presses using xdotool.
        
        :param key_sequence: Key sequence string (e.g. "ctrl+c")
        :return: True if successful, False otherwise
        """
        if not WindowUtils.is_xdotool_available():
            logger.error("xdotool not found")
            return False

        try:
            subprocess.run(['xdotool', 'key', key_sequence], check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error pressing key combination: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in xdotool_key: {e}")
            return False

    @staticmethod
    def xdotool_type(text: str, delay: float = 0.001) -> None:
        """
        Type text using xdotool.
        
        :param text: Text to type
        :param delay: Delay between keystrokes
        """
        if not WindowUtils.is_xdotool_available():
            logger.error("xdotool not found")
            return

        import time
        
        try:
            # Try to get active window ID for synchronization (optional optimization from original code)
            window_args = []
            try:
                # We simply check if we can get the ID, not strictly required but preserved from original logic
                # which attempted to be 'safe' via windowactivate --sync if possible.
                # Here we will simplify: just type into current focus.
                # If we really want the --sync behavior we need the ID.
                res = subprocess.run(['xdotool', 'getactivewindow'], capture_output=True, text=True, check=True)
                window_id = res.stdout.strip()
                if window_id:
                    window_args = ['windowactivate', '--sync', window_id]
            except Exception:
                pass

            # Prepare all key commands at once
            key_commands = []
            for char in text:
                # Handle special characters
                if char == ' ':
                    key = 'space'
                elif char == '\n':
                    key = 'Return'
                elif char == '\t':
                    key = 'Tab'
                elif char in "!@#$%^&*()_+{}|:\"<>?~`-=[]\\;',./":
                    key = char
                else:
                    key = char

                # Build the command
                key_commands.append(['xdotool'] + window_args + ['key', '--clearmodifiers', key])

            # Execute all commands
            for cmd in key_commands:
                try:
                    subprocess.run(cmd, check=True, stderr=subprocess.PIPE, text=True, timeout=0.5)
                    if delay > 0:
                        time.sleep(delay)
                except subprocess.TimeoutExpired:
                    logger.warning(f"[WARNING] Timeout while typing character")
                    continue
                except subprocess.CalledProcessError as e:
                    logger.error(f"[ERROR] Failed to type character: {e}")
                    if e.stderr:
                        logger.error(f"[ERROR] stderr: {e.stderr}")

        except Exception:
            logger.exception("[ERROR] Unexpected error while typing text")
            # Try fallback method
            try:
                subprocess.run(['xdotool', 'type', '--clearmodifiers', '--delay', '1', '--', text], check=True)
            except Exception:
                logger.exception("[ERROR] Fallback typing also failed")

    # ========== wmctrl operations ==========

    @staticmethod
    def wmctrl_activate_window(class_name: str) -> bool:
        """
        Try to activate window using wmctrl.
        
        :param class_name: Window class to search for
        :return: True if successful, False otherwise
        """
        if not WindowUtils.is_wmctrl_available():
            return False

        try:
            result = subprocess.run(
                ['wmctrl', '-xa', class_name],
                capture_output=True,
                text=True,
                timeout=2
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    # ========== System operations ==========

    @staticmethod
    def is_process_running(process_name: str) -> bool:
        """
        Check if a process is running using pgrep.
        
        :param process_name: Process name to search for
        :return: True if process is running, False otherwise or if pgrep unavailable
        """
        try:
            result = subprocess.run(
                ['pgrep', '-x', process_name],
                capture_output=True,
                text=True,
                timeout=1
            )
            return result.returncode == 0 and bool(result.stdout.strip())
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def activate_window(class_name: str, search_by_name: str = None) -> bool:
        """
        Try all available methods to find and focus window.
        
        Auto-detects session type (Wayland vs X11) and connects methods accordingly.
        
        :param class_name: Window class to search for
        :param search_by_name: Optional window name for Chrome apps fallback
        :return: True if window found and focused, False otherwise
        """
        import os
        session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
        
        # Primary method depends on session
        if session_type == 'wayland':
            # Try kdotool first for Wayland
            window_id = WindowUtils.kdotool_search_by_class(class_name)
            if window_id:
                if WindowUtils.kdotool_activate_window(window_id):
                    return True
            
            # Fallback by name using kdotool
            if search_by_name:
                window_id = WindowUtils.kdotool_search_by_name(search_by_name)
                if window_id:
                    if WindowUtils.kdotool_activate_window(window_id):
                        return True
        else:
            # Try xdotool first for X11 / other
            window_id = WindowUtils.xdotool_search_by_class(class_name)
            if window_id:
                if WindowUtils.xdotool_activate_window(window_id):
                    return True
                    
            # Fallback by name using xdotool
            if search_by_name:
                window_id = WindowUtils.xdotool_search_by_name(search_by_name)
                if window_id:
                    if WindowUtils.xdotool_activate_window(window_id):
                        return True

        # Last resort: wmctrl (works on both if XWayland is active)
        if WindowUtils.wmctrl_activate_window(class_name):
            return True

        return False

    # ========== Utility functions ==========

    @staticmethod
    def normalize_class_name(class_name: str, title: str = "") -> str:
        """
        Normalize and translate window class names to human-readable application names.
        
        Handles edge cases and known application patterns using APP_PATTERNS.
        
        :param class_name: Raw window class name
        :param title: Optional window title for additional context
        :return: Normalized application name
        """
        if not class_name:
            return "unknown"
        
        # Iterate through all application patterns to find a match
        for pattern in APP_PATTERNS:
            if pattern.match(class_name, title):
                return pattern.normalized_name
        
        # Return the class name as-is if no translation found
        return class_name

    @staticmethod
    def extract_app_from_title(title: str) -> str:
        """
        Extract application name from window title using common patterns.
        
        Common patterns: "Title - Application" or "Application: Title"
        
        :param title: Window title string
        :return: Extracted application name
        """
        if not title:
            return "unknown"
        
        # First try to normalize if the title itself contains recognizable app names
        normalized = WindowUtils.normalize_class_name(title, title)
        if normalized != title:
            return normalized
        
        # Common patterns in window titles
        # "Document Name - Application"
        if " — " in title:
            extracted = title.split(" — ")[-1].strip()
            return WindowUtils.normalize_class_name(extracted, title)
        if " - " in title:
            extracted = title.split(" - ")[-1].strip()
            return WindowUtils.normalize_class_name(extracted, title)
        if ": " in title:
            extracted = title.split(":")[0].strip()
            return WindowUtils.normalize_class_name(extracted, title)
        
        # Return first word of title as fallback
        fallback = title.split()[0] if title.split() else "unknown"
        return WindowUtils.normalize_class_name(fallback, title)

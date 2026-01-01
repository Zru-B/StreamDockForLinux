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

        if self.simulation_mode:
            logger.info(f"WindowMonitor running in SIMULATION MODE. Reading from {self.simulated_window_file}")

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
        # Method 1: Try KWin DBus scripting (Plasma 6 Wayland)
        window_info = self._try_kwin_scripting()
        if window_info:
            self.current_window_detection_method = "kwin_scripting"
            return window_info

        # Method 2: Try kdotool (legacy fallback)
        if WindowUtils.is_kdotool_available():
            window_info = WindowUtils.kdotool_get_active_window()
            if window_info:
                self.current_window_detection_method = "kdotool"
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
                class_=win_class,
                raw=content,
                method="simulation"
            )
        except Exception as e:
            logger.error(f"Error reading simulation file: {e}")
            return None

    def _prepare_kwin_script(self):
        """
        Prepare KWin script for execution.
        
        Returns:
            tuple[str, str] | None: (script_path, marker) or None on failure
        """
        import os
        import tempfile
        
        try:
            # Locate the source script
            base_dir = os.path.dirname(os.path.abspath(__file__))
            script_source = os.path.join(base_dir, "scripts", "kwin_detect.js")
            
            if not os.path.exists(script_source):
                logger.error(f"KWin script not found at {script_source}")
                return None
            
            with open(script_source, "r") as f:
                content = f.read()
            
            # Inject unique marker
            marker = f"STREAMDOCK_QUERY_{int(time.time() * 1000)}"
            content = content.replace("MARKER_ID", marker)
            
            # Write to temp file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as tmp_script:
                tmp_script.write(content)
                script_path = tmp_script.name
            
            return (script_path, marker)
        
        except Exception as e:
            logger.error(f"Failed to prepare KWin script: {e}")
            return None
    
    def _load_kwin_script(self, script_path, plugin_name):
        """
        Load KWin script via DBus.
        
        Returns:
            int | None: script_id or None on failure
        """
        try:
            # Start scripting service
            subprocess.run(
                ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.start"],
                capture_output=True, timeout=1, check=False
            )
            
            # Unload existing script (clean state)
            subprocess.run(
                ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", plugin_name],
                capture_output=True, timeout=1, check=False
            )
            
            # Load the script
            res = subprocess.run(
                ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", script_path, plugin_name],
                capture_output=True, text=True, timeout=1, check=False
            )
            
            if res.returncode != 0:
                # Fallback to older qdbus for older KDE
                res = subprocess.run(
                    ["qdbus", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", script_path, plugin_name],
                    capture_output=True, text=True, timeout=1, check=False
                )
            
            # Validate script ID
            if res.returncode != 0 or not res.stdout.strip().lstrip('-').isdigit():
                logger.debug(f"loadScript failed: {res.stdout.strip()} {res.stderr.strip()}")
                return None
            
            script_id = int(res.stdout.strip())
            if script_id < 0:
                logger.debug("KWin returned invalid script ID")
                return None
            
            return script_id
        
        except Exception as e:
            logger.debug(f"Failed to load KWin script: {e}")
            return None
    
    def _parse_journal_for_window(self, marker):
        """
        Parse journal logs for window information.
        
        Returns:
            WindowInfo | None: Parsed window info or None
        """
        try:
            res_journal = subprocess.run(
                ["journalctl", "--user", "--no-pager", "-n", "100"],
                capture_output=True, text=True, timeout=5, check=False
            )
            logger.debug(f"Journal size: {len(res_journal.stdout)}")
            
            if marker not in res_journal.stdout:
                logger.debug(f"Marker {marker} not found in journal. Output snippet: {res_journal.stdout[:200]}...")
                return None
            
            # Find marker in reversed log
            for line in reversed(res_journal.stdout.splitlines()):
                if marker in line:
                    logger.debug(f"Found marker {marker} in line: {line}")
                    payload = line.split(f"{marker}:")[-1].strip()
                    
                    if "|" in payload:
                        title, raw_class = payload.split("|", 1)
                        
                        if title == "None" and raw_class == "None":
                            return None
                        
                        window_class = WindowUtils.normalize_class_name(raw_class, title)
                        return WindowInfo(
                            title=title,
                            class_=window_class,
                            raw=payload,
                            method="kwin_scripting"
                        )
            
            return None
        
        except Exception as e:
            logger.debug(f"Failed to parse journal: {e}")
            return None
    
    def _cleanup_kwin_script(self, script_path, script_id, plugin_name):
        """Cleanup KWin script and temp file."""
        import os
        
        # Unload script if we have an ID
        if script_id is not None:
            try:
                subprocess.run(
                    ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", plugin_name],
                    capture_output=True, timeout=1, check=False
                )
            except Exception:
                pass
        
        # Delete temp file
        if script_path and os.path.exists(script_path):
            try:
                os.unlink(script_path)
            except Exception:
                pass

    def _try_kwin_scripting(self) -> WindowInfo | None:
        """
        Try using KWin DBus scripting to get active window.
        Orchestrates helper methods for preparation, execution, and parsing.
        """
        # Prepare script
        script_info = self._prepare_kwin_script()
        if not script_info:
            return None
        
        script_path, marker = script_info
        plugin_name = "streamdock_query"
        script_id = None
        
        try:
            # Load script
            script_id = self._load_kwin_script(script_path, plugin_name)
            if script_id is None:
                return None
            
            # Run the script
            script_obj = f"/Scripting/Script{script_id}"
            subprocess.run(
                ["qdbus6", "org.kde.KWin", script_obj, "org.kde.kwin.Script.run"],
                capture_output=True, timeout=1, check=False
            )
            
            # Wait for journal to sync
            time.sleep(0.2)
            
            # Parse journal for result
            return self._parse_journal_for_window(marker)
        
        except Exception as e:
            logger.debug(f"kwin_scripting failed: {e}")
            return None
        finally:
            self._cleanup_kwin_script(script_path, script_id, plugin_name)

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
                        class_=window_class,
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
                    class_=window_class,
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
                    class_=window_class,
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
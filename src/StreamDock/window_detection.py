"""
Window detection strategies for KDE Plasma Wayland.

This module implements a strategy pattern for detecting active windows using
multiple methods (kdotool, KWin D-Bus, xdotool, etc.) with automatic fallback.
"""
import logging
import subprocess
from abc import ABC, abstractmethod
from typing import Optional

from StreamDock.Models import WindowInfo


class DetectionMethod(ABC):
    """
    Abstract base class for window detection strategies.
    
    Each detection method implements the detect() method and shares
    common subprocess execution logic with proper error handling.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._is_available = True
        self._consecutive_failures = 0
        self._max_failures = 3  # Disable after 3 consecutive failures
        self.last_error: Optional[str] = None
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this detection method."""
        pass
    
    @property
    def is_available(self) -> bool:
        """Whether this detection method is currently available/enabled."""
        return self._is_available
    
    def disable(self, reason: str):
        """Disable this detection method due to repeated failures."""
        if self._is_available:
            self._is_available = False
            self.logger.warning(
                f"Disabling detection method '{self.name}': {reason}"
            )
    
    @abstractmethod
    def detect(self) -> Optional[WindowInfo]:
        """
        Attempt to detect the active window.
        
        Returns:
            WindowInfo if successful, None if detection failed.
        """
        pass
    
    def _run_command(
        self,
        cmd: list,
        timeout: float = 1.0,
        check_returncode: bool = True
    ) -> Optional[subprocess.CompletedProcess]:
        """
        Run a subprocess command with timeout and error handling.
        
        Args:
            cmd: Command and arguments as list
            timeout: Timeout in seconds
            check_returncode: If True, return None on non-zero return code
            
        Returns:
            CompletedProcess if successful, None on failure
        """
        try:
            self.logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            self.logger.debug(
                f"Command {cmd[0]} completed: returncode={result.returncode}, "
                f"stdout_len={len(result.stdout)}, stderr_len={len(result.stderr)}"
            )
            
            if result.stderr:
                self.logger.debug(f"Command {cmd[0]} stderr: {result.stderr[:200]}")
            
            if check_returncode and result.returncode != 0:
                self.logger.debug(
                    f"Command {cmd[0]} returned code {result.returncode}"
                )
                return None
            
            return result
            
        except subprocess.TimeoutExpired:
            self.logger.debug(f"Command {cmd[0]} timed out after {timeout}s")
            return None
        except FileNotFoundError:
            self.logger.debug(f"Command {cmd[0]} not found")
            return None
        except Exception as e:
            self.logger.debug(f"Command {cmd[0]} failed: {e}")
            return None
    
    def _handle_success(self) -> None:
        """Reset failure counter on successful detection."""
        self._consecutive_failures = 0
        self.last_error = None
    
    def _handle_failure(self, error_msg: str) -> None:
        """Handle detection failure with automatic disabling."""
        self._consecutive_failures += 1
        self.last_error = error_msg
        
        if self._consecutive_failures >= self._max_failures:
            self.disable(
                f"Failed {self._max_failures} consecutive times. "
                f"Last error: {error_msg}"
            )


class KdotoolDetection(DetectionMethod):
    """Detection using kdotool (best for KDE Wayland)."""
    
    @property
    def name(self) -> str:
        return "kdotool"
    
    def detect(self) -> Optional[WindowInfo]:
        """Detect active window using kdotool."""
        from .window_utils import WindowUtils
        
        try:
            window_info = WindowUtils.kdotool_get_active_window()
            
            if window_info:
                self._handle_success()
                return window_info
            else:
                self._handle_failure("kdotool detection returned None")
                return None
            
        except Exception as e:
            self._handle_failure(f"Unexpected error: {e}")
            return None


class KWinDynamicScriptingDetection(DetectionMethod):
    """
    Detection using a dynamically generated KWin script.
    More robust than kwin_scripting as it uses unique markers per query.
    """
    
    def __init__(self):
        super().__init__()
        self._use_qdbus6 = True
        
    @property
    def name(self) -> str:
        return "kwin_dynamic"
        
    def detect(self) -> Optional[WindowInfo]:
        """Detect active window by loading and running a temporary KWin script."""
        import os
        import tempfile
        import time
        import json
        
        temp_file = None
        try:
            # Prepare script with unique marker
            marker = f"STREAMDOCK_QUERY_{int(time.time() * 1000)}"
            script_content = f"""
            var activeClient = workspace.activeWindow;
            if (activeClient) {{
                print("{marker}:" + activeClient.caption + "|" + activeClient.resourceClass);
            }} else {{
                print("{marker}:None|None");
            }}
            """
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as tf:
                tf.write(script_content)
                temp_file = tf
            
            qdbus_cmd = 'qdbus6' if self._use_qdbus6 else 'qdbus'
            plugin_name = marker  # Use marker as unique plugin name
            
            # Helper to try loading script with a specific dbus command
            def _load_script_with_command(cmd_name: str) -> Optional[str]:
                # 1. Start setup: Ensure scripting service is running
                self._run_command(
                    [cmd_name, 'org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting.start'],
                    timeout=1.0,
                    check_returncode=False
                )

                # 2. Clean slate: Unload any existing script with same name
                self._run_command(
                    [cmd_name, 'org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting.unloadScript', plugin_name],
                    timeout=1.0,
                    check_returncode=False
                )
                
                # 3. Load script with plugin name (Required for Plasma 6)
                res = self._run_command(
                    [cmd_name, 'org.kde.KWin', '/Scripting',
                     'org.kde.kwin.Scripting.loadScript', temp_file.name, plugin_name],
                    timeout=2.0,
                    check_returncode=False
                )
                
                if res and res.returncode == 0:
                     sid = res.stdout.strip()
                     if sid != '-1' and sid.lstrip('-').isdigit():
                         return sid
                return None

            # Try primary command
            script_id = _load_script_with_command(qdbus_cmd)
            
            # Fallback if failed and using qdbus6
            if not script_id and self._use_qdbus6:
                self._use_qdbus6 = False
                qdbus_cmd = 'qdbus'
                script_id = _load_script_with_command(qdbus_cmd)
            
            if not script_id:
                self._handle_failure("Failed to load dynamic script or invalid ID")
                return None
            
            # Run the script
            run_result = self._run_command(
                [qdbus_cmd, 'org.kde.KWin', f'/Scripting/Script{script_id}',
                 'org.kde.kwin.Script.run'],
                timeout=2.0,
                check_returncode=False
            )
            
            # Cleanup script immediately
            self._run_command([qdbus_cmd, 'org.kde.KWin', f'/Scripting/Script{script_id}', 'org.kde.kwin.Script.stop'], timeout=0.5)
            self._run_command([qdbus_cmd, 'org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting.unloadScript', plugin_name], timeout=0.5)
            
            if not run_result or run_result.returncode != 0:
                self._handle_failure("Script execution failed")
                return None
            
            # Parse journal with retry
            wait_times = [0.05, 0.05, 0.10]
            for i, wait in enumerate(wait_times):
                time.sleep(wait)
                
                # Check recent journal entries
                journal_result = self._run_command(
                    ['journalctl', '--user', '-n', '50', '--no-pager'],
                    timeout=1.0,
                    check_returncode=False
                )
                
                if journal_result:
                    # Search reversed to find latest
                    for line in reversed(journal_result.stdout.splitlines()):
                        if marker in line:
                            payload = line.split(f"{marker}:")[-1].strip()
                            if "|" in payload:
                                title, raw_class = payload.split("|", 1)
                                if title == "None" and raw_class == "None":
                                    return None
                                
                                from .window_utils import WindowUtils
                                window_class = WindowUtils.normalize_class_name(raw_class, title)
                                
                                self._handle_success()
                                return WindowInfo(
                                    title=title,
                                    class_=window_class,
                                    method=self.name
                                )
            
            self._handle_failure(f"Marker {marker} not found in journal after retries")
            return None
            
        except Exception as e:
            self._handle_failure(f"Dynamic scripting error: {e}")
            return None
        finally:
            if temp_file and os.path.exists(temp_file.name):
                try: os.unlink(temp_file.name)
                except: pass


class PlasmaTaskManagerDetection(DetectionMethod):
    """Detection using Plasma task manager (experimental)."""
    
    @property
    def name(self) -> str:
        return "plasma_taskmanager"
    
    def detect(self) -> Optional[WindowInfo]:
        """Detect active window using Plasma task manager."""
        # This method is complex and often unreliable
        # Keeping as placeholder for future implementation
        self._handle_failure("Not implemented - experimental method")
        return None


class KWinBasicDetection(DetectionMethod):
    """Detection using basic KWin D-Bus interface."""
    
    @property
    def name(self) -> str:
        return "kwin_basic"
    
    def detect(self) -> Optional[WindowInfo]:
        """
        Detect active window using basic KWin D-Bus.
        Tries multiple approaches for KDE Plasma 6 Wayland compatibility.
        """
        from .window_utils import WindowUtils
        
        # Method 1: Try using qdbus6 (Plasma 6 uses Qt6)
        try:
            result = self._run_command(
                [
                    "bash",
                    "-c",
                    'qdbus6 org.kde.KWin /KWin org.kde.KWin.activeWindow 2>/dev/null '
                    '|| qdbus org.kde.KWin /KWin org.kde.KWin.activeWindow 2>/dev/null || echo ""',
                ],
                timeout=1.0,
                check_returncode=False
            )

            if result and result.returncode == 0 and result.stdout.strip():
                raw_output = result.stdout.strip()
                # Check if the output is actually an error message
                if "Error" not in raw_output and "No such method" not in raw_output:
                    window_title = raw_output
                    window_class = WindowUtils.extract_app_from_title(window_title)

                    self._handle_success()
                    return WindowInfo(
                        title=window_title,
                        class_=window_class,
                        raw=window_title,
                        method="kwin_plasma6",
                    )
        except Exception as e:
            self.logger.debug(f"KWin basic method 1 failed: {e}")

        # Method 2: Try using busctl (non-interactive)
        try:
            result = self._run_command(
                [
                    "bash",
                    "-c",
                    'busctl --user get-property org.kde.KWin /KWin org.kde.KWin ActiveWindow '
                    '2>/dev/null || echo ""',
                ],
                timeout=1.0,
                check_returncode=False
            )

            if (
                result
                and result.returncode == 0
                and result.stdout.strip()
                and "Error" not in result.stdout
            ):
                window_title = result.stdout.strip()
                # Remove busctl formatting (e.g., 's "Title"')
                if window_title.startswith("s "):
                    window_title = window_title[2:].strip('"')

                window_class = WindowUtils.extract_app_from_title(window_title)

                self._handle_success()
                return WindowInfo(
                    title=window_title,
                    class_=window_class,
                    raw=window_title,
                    method="busctl",
                )
        except Exception as e:
            self.logger.debug(f"KWin basic method 2 failed: {e}")

        # Method 3: Fallback to XWindowDetection logic (often works via XWayland)
        # We invoke xdotool directly here to keep this strategy self-contained for "basic" approaches
        try:
            result = self._run_command(
                ["bash", "-c", 'xdotool getactivewindow 2>/dev/null || echo ""'],
                timeout=1.0,
                check_returncode=False
            )

            if result and result.returncode == 0 and result.stdout.strip():
                window_id = result.stdout.strip()

                # Get window title
                result_title = self._run_command(
                    ["xdotool", "getwindowname", window_id],
                    check_returncode=False
                )
                window_title = result_title.stdout.strip() if result_title and result_title.returncode == 0 else ""

                # Get window class
                result_class = self._run_command(
                    ["xdotool", "getwindowclassname", window_id],
                    check_returncode=False
                )
                
                raw_class = ""
                if result_class and result_class.returncode == 0 and result_class.stdout.strip():
                    raw_class = result_class.stdout.strip()
                    window_class = WindowUtils.normalize_class_name(raw_class, window_title)
                else:
                    window_class = WindowUtils.extract_app_from_title(window_title)

                self._handle_success()
                return WindowInfo(
                    title=window_title,
                    class_=window_class,
                    raw=window_title,
                    method="kwin_basic_x11",
                )
        except Exception as e:
            self.logger.debug(f"KWin basic method 3 failed: {e}")

        self._handle_failure("All basic KWin methods failed")
        return None


class XWindowDetection(DetectionMethod):
    """Detection using X11 tools (xdotool + xprop) as fallback."""
    
    @property
    def name(self) -> str:
        return "x11"
    
    def detect(self) -> Optional[WindowInfo]:
        """Detect active window using X11 tools."""
        from .window_utils import WindowUtils
        
        try:
            window_info = WindowUtils.xdotool_get_active_window()
            
            if window_info:
                self._handle_success()
                return window_info
            else:
                self._handle_failure("xdotool detection returned None")
                return None
            
        except Exception as e:
            self._handle_failure(f"Unexpected error: {e}")
            return None


class SimulationDetection(DetectionMethod):
    """Detection for simulation mode (reads from file)."""
    
    def __init__(self, file_path: str = "/tmp/streamdock_fake_window"):
        super().__init__()
        self.file_path = file_path
        
    @property
    def name(self) -> str:
        return "simulation"
        
    def detect(self) -> Optional[WindowInfo]:
        """Read active window from simulation file."""
        import os
        try:
            if not os.path.exists(self.file_path):
                return None

            with open(self.file_path, 'r') as f:
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

            self._handle_success()
            return WindowInfo(
                title=title,
                class_=win_class,
                raw=content,
                method="simulation"
            )
        except Exception as e:
            self._handle_failure(f"Error reading simulation file: {e}")
            return None

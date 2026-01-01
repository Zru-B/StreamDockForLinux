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
            # Delegate to WindowUtils which has the full implementation
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


class KWinScriptingDetection(DetectionMethod):
    """Detection using KWin scripting D-Bus interface (native Python implementation)."""
    
    def __init__(self):
        super().__init__()
        self._use_qdbus6 = True  # Try qdbus6 first (Plasma 6)
    
    @property
    def name(self) -> str:
        return "kwin_scripting"
    
    def detect(self) -> Optional[WindowInfo]:
        """
        Detect active window using KWin scripting API.
        
        Uses the installed KWin script at ~/.local/share/kwin/scripts/streamdock-activemon/
        """
        import os
        from pathlib import Path
        
        try:
            # Path to installed KWin script
            script_path = Path.home() / '.local/share/kwin/scripts/streamdock-activemon/contents/code/main.js'
            
            if not script_path.exists():
                self._handle_failure(f"KWin script not installed at {script_path}")
                return None
            
            qdbus_cmd = 'qdbus6' if self._use_qdbus6 else 'qdbus'
            
            # Load the installed script
            load_result = self._run_command(
                [qdbus_cmd, 'org.kde.KWin', '/Scripting',
                 'org.kde.kwin.Scripting.loadScript', str(script_path), 'streamdock-activemon'],
                timeout=2.0,
                check_returncode=False
            )
            
            # Try qdbus if qdbus6 fails
            if not load_result and self._use_qdbus6:
                self.logger.debug("qdbus6 failed, trying qdbus")
                self._use_qdbus6 = False
                qdbus_cmd = 'qdbus'
                load_result = self._run_command(
                    [qdbus_cmd, 'org.kde.KWin', '/Scripting',
                     'org.kde.kwin.Scripting.loadScript', str(script_path), 'streamdock-activemon'],
                    timeout=2.0,
                    check_returncode=False
                )
            
            if not load_result or load_result.returncode != 0:
                self._handle_failure("Failed to load KWin script")
                return None
            
            script_id = load_result.stdout.strip()
            
            # script_id of -1 means the script failed to load
            if script_id == '-1':
                self._handle_failure("KWin rejected script (returned -1)")
                return None
            
            if not script_id or not script_id.lstrip('-').isdigit():
                self._handle_failure(f"Invalid script ID: {script_id}")
                return None
            
            self.logger.debug(f"KWin script loaded with ID: {script_id}")
            
            # Run the script - output will be in journalctl
            run_result = self._run_command(
                [qdbus_cmd, 'org.kde.KWin', f'/Scripting/Script{script_id}',
                 'org.kde.kwin.Script.run'],
                timeout=2.0,
                check_returncode=False
            )
            
            # Stop and unload the script
            self._run_command(
                [qdbus_cmd, 'org.kde.KWin', f'/Scripting/Script{script_id}',
                 'org.kde.kwin.Script.stop'],
                timeout=1.0,
                check_returncode=False
            )
            self._run_command(
                [qdbus_cmd, 'org.kde.KWin', '/Scripting',
                 'org.kde.kwin.Scripting.unloadScript', 'streamdock-activemon'],
                timeout=1.0,
                check_returncode=False
            )
            
            if not run_result or run_result.returncode != 0:
                error_msg = f"Script execution failed with code {run_result.returncode if run_result else 'N/A'}"
                self._handle_failure(error_msg)
                return None
            
            # Capture output from journalctl (script output goes there)
            journal_result = self._run_command(
                ['journalctl', '--user', '-n', '20', '--since', '2 seconds ago'],
                timeout=2.0,
                check_returncode=False
            )
            
            if not journal_result:
                self._handle_failure("Failed to read journal")
                return None
            
            # Parse JSON output from journal
            import json
            try:
                # Look for our JSON output in recent journal entries
                for line in journal_result.stdout.split('\n'):
                    line = line.strip()
                    # Look for lines containing our JSON (starts with js: and has caption field)
                    if 'js:' in line and 'caption' in line:
                        # Extract JSON part after "js: "
                        json_start = line.find('{')
                        if json_start != -1:
                            json_str = line[json_start:]
                            # Handle potential truncation or extra text
                            json_end = json_str.rfind('}') + 1
                            if json_end > 0:
                                json_str = json_str[:json_end]
                                
                                data = json.loads(json_str)
                                window_class = data.get('resourceClass') or data.get('resourceName') or 'unknown'
                                window_title = data.get('caption', 'Unknown')
                                window_id = str(data.get('windowId', ''))
                                
                                self.logger.debug(f"Parsed window from journal: {window_title} ({window_class})")
                                
                                self._handle_success()
                                return WindowInfo(
                                    title=window_title,
                                    class_=window_class,
                                    window_id=window_id,
                                    method=self.name
                                )
            except (json.JSONDecodeError, ValueError) as e:
                self.logger.debug(f"Failed to parse journal output: {e}")
            
            self._handle_failure("No valid JSON output found in journal")
            return None
            
        except Exception as e:
            self._handle_failure(f"Unexpected error: {e}")
            self.logger.exception(f"Exception in {self.name} detection")
            return None


class PlasmaTaskManagerDetection(DetectionMethod):
    """Detection using Plasma task manager (experimental)."""
            
            # Load script from file
            load_result = self._run_command(
                [qdbus_cmd, 'org.kde.KWin', '/Scripting',
                 'org.kde.kwin.Scripting.loadScript', temp_file.name],
                timeout=2.0,
                check_returncode=False
            )
            
            # Try qdbus if qdbus6 fails
            if not load_result and self._use_qdbus6:
                self.logger.debug("qdbus6 failed, trying qdbus")
                self._use_qdbus6 = False
                qdbus_cmd = 'qdbus'
                load_result = self._run_command(
                    [qdbus_cmd, 'org.kde.KWin', '/Scripting',
                     'org.kde.kwin.Scripting.loadScript', temp_file.name],
                    timeout=2.0,
                    check_returncode=False
                )
            
            if not load_result or load_result.returncode != 0:
                self._handle_failure("Failed to load KWin script")
                return None
            
            script_id = load_result.stdout.strip()
            self.logger.debug(f"KWin script loaded with ID: {script_id}")
            
            # script_id of -1 means the script failed to load
            if script_id == '-1':
                self._handle_failure("KWin rejected script (returned -1)")
                return None
            
            if not script_id or not script_id.lstrip('-').isdigit():
                self._handle_failure(f"Invalid script ID: {script_id}")
                return None
            
            # Run the script
            run_result = self._run_command(
                [qdbus_cmd, 'org.kde.KWin', f'/Scripting/Script{script_id}',
                 'org.kde.kwin.Script.run'],
                timeout=2.0,
                check_returncode=False
            )
            
            # Stop and unload the script (cleanup)
            self._run_command(
                [qdbus_cmd, 'org.kde.KWin', f'/Scripting/Script{script_id}',
                 'org.kde.kwin.Script.stop'],
                timeout=1.0,
                check_returncode=False
            )
            self._run_command(
                [qdbus_cmd, 'org.kde.KWin', '/Scripting',
                 'org.kde.kwin.Scripting.unloadScript', script_id],
                timeout=1.0,
                check_returncode=False
            )
            
            if not run_result or run_result.returncode != 0:
                error_msg = f"Script execution failed with code {run_result.returncode if run_result else 'N/A'}"
                if run_result and run_result.stdout:
                    self.logger.debug(f"Script stdout: {run_result.stdout[:500]}")
                    error_msg += f": {run_result.stdout[:200]}"
                if run_result and run_result.stderr:
                    self.logger.debug(f"Script stderr: {run_result.stderr[:500]}")
                self._handle_failure(error_msg)
                return None
            
            # Parse JSON output from script
            import json
            try:
                output_lines = run_result.stdout.strip().split('\n')
                for line in output_lines:
                    line = line.strip()
                    if line.startswith('{'):
                        data = json.loads(line)
                        window_class = data.get('resourceClass') or data.get('resourceName') or 'unknown'
                        window_title = data.get('caption', 'Unknown')
                        window_id = str(data.get('windowId', ''))
                        
                        self.logger.debug(f"Parsed window: {window_title} ({window_class})")
                        
                        self._handle_success()
                        return WindowInfo(
                            title=window_title,
                            class_=window_class,
                            window_id=window_id,
                            method=self.name
                        )
            except (json.JSONDecodeError, ValueError) as e:
                self.logger.debug(f"Failed to parse script output: {e}, output: {run_result.stdout[:200]}")
            
            self._handle_failure("No valid JSON output from script")
            return None
            
        except Exception as e:
            self._handle_failure(f"Unexpected error: {e}")
            self.logger.exception(f"Exception in {self.name} detection")
            return None
        finally:
            # Clean up temporary file
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except:
                    pass


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
        return "kwin_dbus"
    
    def detect(self) -> Optional[WindowInfo]:
        """
        Detect active window using KWin D-Bus.
        
        Uses ONLY the non-interactive busctl method.
        NOTE: queryWindowInfo is NOT used as it prompts user to select window.
        """
        # The ActiveWindow property doesn't exist on many KWin installations
        # Disable this method to avoid repeated failures
        if self._is_available:
            self.disable("KWin ActiveWindow property not available on this system")
        
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
            # Delegate to WindowUtils which has the full implementation
            window_info = WindowUtils.xdotool_get_active_window()
            
            if window_info:
                self._handle_success()
                return window_info
            else:
                self._handle_failure("xdotool detection returned None")
                return None
            
        except Exception as e:
            self._handle_failure(f"Unexpected error: {e}")
            self.logger.exception(f"Exception in {self.name} detection")
            return None

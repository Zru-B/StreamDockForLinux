"""
Tests for LinuxWindowManager.

Verifies subprocess commands, haircross safety, class-name normalisation,
and tool-availability caching.  All patches target the
``StreamDock.infrastructure.linux_window_manager`` module namespace so no
real processes are spawned.
"""

import subprocess
import pytest
from unittest.mock import MagicMock, call, patch

from StreamDock.domain.Models import WindowInfo
from StreamDock.infrastructure.linux_window_manager import LinuxWindowManager

MODULE = "StreamDock.infrastructure.linux_window_manager"


@pytest.fixture
def manager():
    """Fresh LinuxWindowManager with cleared tool cache."""
    m = LinuxWindowManager()
    m.reset_tool_cache()
    return m


def _run(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


# ---------------------------------------------------------------------------
# Tool availability
# ---------------------------------------------------------------------------

class TestToolAvailability:

    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_kdotool_available_when_installed_and_working(self, mock_run, mock_which, manager):
        mock_which.return_value = "/usr/bin/kdotool"
        mock_run.return_value = _run(0, "12345")

        assert manager.is_kdotool_available() is True
        # Verify the non-interactive availability probe command
        mock_run.assert_called_once_with(
            ["kdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=1, check=False,
        )

    @patch(f"{MODULE}.shutil.which")
    def test_kdotool_unavailable_when_not_installed(self, mock_which, manager):
        mock_which.return_value = None
        assert manager.is_kdotool_available() is False

    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_kdotool_unavailable_when_command_fails(self, mock_run, mock_which, manager):
        mock_which.return_value = "/usr/bin/kdotool"
        mock_run.return_value = _run(1)
        assert manager.is_kdotool_available() is False

    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_kdotool_availability_is_cached(self, mock_run, mock_which, manager):
        mock_which.return_value = "/usr/bin/kdotool"
        mock_run.return_value = _run(0, "1")
        manager.is_kdotool_available()
        manager.is_kdotool_available()
        # shutil.which and subprocess.run each called only once (cache hit second time)
        assert mock_run.call_count == 1

    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_xdotool_available_when_installed(self, mock_run, mock_which, manager):
        mock_which.return_value = "/usr/bin/xdotool"
        mock_run.return_value = _run(0)
        assert manager.is_xdotool_available() is True
        mock_run.assert_called_once_with(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=1, check=False,
        )

    @patch(f"{MODULE}.shutil.which")
    def test_xdotool_unavailable_when_not_installed(self, mock_which, manager):
        mock_which.return_value = None
        assert manager.is_xdotool_available() is False


# ---------------------------------------------------------------------------
# Haircross safety — get_active_window must use getactivewindow only
# ---------------------------------------------------------------------------

class TestHaircrossSafety:
    """
    These tests are the primary guard against the haircross bug.

    If get_active_window() ever calls selectwindow, standalone xprop (without
    -id), or any other mouse-interactive command, these tests will fail.
    """

    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_kdotool_path_uses_getactivewindow_not_selectwindow(self, mock_run, mock_which, manager):
        """kdotool path: must call 'kdotool getactivewindow', never 'selectwindow'."""
        mock_which.side_effect = lambda name: "/usr/bin/kdotool" if name == "kdotool" else None

        # availability probe + getactivewindow + getwindowname + getwindowclassname
        mock_run.side_effect = [
            _run(0, "1"),           # is_kdotool_available probe
            _run(0, "999"),         # getactivewindow
            _run(0, "Firefox"),     # getwindowname
            _run(0, "firefox"),     # getwindowclassname
        ]

        result = manager.get_active_window()
        assert result is not None

        all_cmds = [str(c.args[0]) for c in mock_run.call_args_list]
        assert any("getactivewindow" in cmd for cmd in all_cmds), \
            "Expected 'getactivewindow' in subprocess calls"
        assert not any("selectwindow" in cmd for cmd in all_cmds), \
            "Haircross bug: 'selectwindow' found in subprocess calls"
        assert not any("xprop" in cmd for cmd in all_cmds), \
            "Haircross bug: bare 'xprop' found in subprocess calls"

    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_xdotool_path_uses_getactivewindow_not_selectwindow(self, mock_run, mock_which, manager):
        """xdotool fallback: must call 'xdotool getactivewindow', never 'selectwindow'."""
        mock_which.side_effect = lambda name: "/usr/bin/xdotool" if name == "xdotool" else None

        mock_run.side_effect = [
            _run(0),                # is_xdotool_available probe
            _run(0, "42"),          # getactivewindow
            _run(0, "Konsole"),     # getwindowname
            _run(0, "org.kde.konsole"),  # getwindowclassname
        ]

        result = manager.get_active_window()
        assert result is not None

        all_cmds = [str(c.args[0]) for c in mock_run.call_args_list]
        assert any("getactivewindow" in cmd for cmd in all_cmds)
        assert not any("selectwindow" in cmd for cmd in all_cmds), \
            "Haircross bug: 'selectwindow' found in subprocess calls"


# ---------------------------------------------------------------------------
# get_active_window — result correctness
# ---------------------------------------------------------------------------

class TestGetActiveWindowResults:

    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_kdotool_returns_correct_window_info(self, mock_run, mock_which, manager):
        mock_which.side_effect = lambda n: "/usr/bin/kdotool" if n == "kdotool" else None
        mock_run.side_effect = [
            _run(0, "1"),
            _run(0, "123"),
            _run(0, "Firefox - GitHub"),
            _run(0, "firefox"),
        ]
        result = manager.get_active_window()
        assert result is not None
        assert isinstance(result, WindowInfo)
        assert result.method == "kdotool"
        assert result.class_ == "Firefox"

    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_xdotool_fallback_returns_correct_window_info(self, mock_run, mock_which, manager):
        mock_which.side_effect = lambda n: "/usr/bin/xdotool" if n == "xdotool" else None
        mock_run.side_effect = [
            _run(0),
            _run(0, "77"),
            _run(0, "Konsole"),
            _run(0, "org.kde.konsole"),
        ]
        result = manager.get_active_window()
        assert result is not None
        assert result.method == "xdotool"
        assert result.class_ == "Konsole"

    @patch(f"{MODULE}.os.environ.get")
    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_qdbus_fallback_returns_correct_window_info(self, mock_run, mock_which, mock_env, manager):
        mock_env.return_value = "wayland-0"
        mock_which.side_effect = lambda n: "/usr/bin/qdbus6" if n == "qdbus6" else None
        
        # We don't patch uuid, we just let it generate a real uuid
        # and we mock subprocess.run to return a line that happens to match our test logic
        # by patching the return of the script load/run.
        def mock_subprocess_run(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd)
            print("MOCK CALLED WITH:", cmd_str)
            if "kdotool" in cmd_str:
                return _run(1)  # Force kdotool to be unavailable
            if "loadScript" in cmd_str:
                return _run(0, "42")
            if "unloadScript" in cmd_str:
                return _run(0)
            if "Script.run" in cmd_str:
                return _run(0)
            if "journalctl" in cmd_str:
                # To bypass the unique marker, we just force the test string to have |||
                # Actually, the logic looks for marker_id in line. So we must extract marker_id 
                # from the dumped script file.
                marker_id = "unknown"
                try:
                    with open(manager._kwin_script_path, "r") as f:
                        content = f.read()
                        # print("{marker_id}|" + active.caption ...
                        marker_id = content.split('print("')[1].split('|')[0]
                except Exception as e:
                    print("Failed to read script path", e)
                
                print("USING MARKER", marker_id)
                return _run(0, f"some line\njs: {marker_id}|Vivaldi|||vivaldi-stable\nother line")
            
            # Default success for availability checks
            return _run(0)

        mock_run.side_effect = mock_subprocess_run
        
        manager._kwin_script_path = "/tmp/fake_fake.js"
        # Write dummy file so open() doesn't crash in mock
        with open(manager._kwin_script_path, "w") as f:
            f.write('print("fakehash123|Vivaldi|||vivaldi-stable");')
            
        result = manager.get_active_window()
        assert result is not None
        assert result.method == "qdbus_kwin"
        assert result.class_ == "vivaldi-stable"

    @patch(f"{MODULE}.shutil.which")
    def test_returns_none_when_no_tools_available(self, mock_which, manager):
        mock_which.return_value = None
        assert manager.get_active_window() is None

    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_returns_none_when_getactivewindow_fails(self, mock_run, mock_which, manager):
        mock_which.side_effect = lambda n: "/usr/bin/kdotool" if n == "kdotool" else None
        mock_run.side_effect = [
            _run(0, "1"),   # availability probe succeeds
            _run(1),        # getactivewindow fails
        ]
        assert manager.get_active_window() is None


# ---------------------------------------------------------------------------
# Class-name normalisation
# ---------------------------------------------------------------------------

class TestNormalization:

    def test_firefox_keyword_match(self):
        assert LinuxWindowManager.normalize_class_name("firefox") == "Firefox"

    def test_konsole_exact_match(self):
        assert LinuxWindowManager.normalize_class_name("org.kde.konsole") == "Konsole"

    def test_unknown_class_returned_verbatim(self):
        assert LinuxWindowManager.normalize_class_name("my.custom.app") == "my.custom.app"

    def test_empty_class_returns_unknown(self):
        assert LinuxWindowManager.normalize_class_name("") == "unknown"

    def test_extract_from_dash_title(self):
        assert LinuxWindowManager.extract_app_from_title("Document - Firefox") == "Firefox"

    def test_extract_fallback(self):
        result = LinuxWindowManager.extract_app_from_title("SomeUnknownApp")
        assert result == "SomeUnknownApp"


# ---------------------------------------------------------------------------
# search_window_by_name
# ---------------------------------------------------------------------------

class TestSearchWindowByName:
    
    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_kdotool_search_by_name(self, mock_run, mock_which, manager):
        mock_which.side_effect = lambda n: "/usr/bin/kdotool" if n == "kdotool" else None
        mock_run.side_effect = [
            _run(0, "1"),           # availability probe
            _run(0, "12345\n678"),  # search --name
        ]
        
        result = manager.search_window_by_name("Test App")
        assert result == "12345"
        
        all_cmds = [str(c.args[0]) for c in mock_run.call_args_list]
        assert "search" in all_cmds[1]
        assert "--name" in all_cmds[1]
        assert "Test App" in all_cmds[1]

    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_xdotool_fallback_search_by_name(self, mock_run, mock_which, manager):
        mock_which.side_effect = lambda n: "/usr/bin/xdotool" if n == "xdotool" else None
        mock_run.side_effect = [
            _run(0),
            _run(0, "11\n22\n33"),
        ]
        
        result = manager.search_window_by_name("Fallback App")
        assert result == "33"  # Expected bottom of stack for xdotool


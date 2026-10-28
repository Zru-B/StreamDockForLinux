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


def _fake_kwin(payload: str, calls: list = None):
    """subprocess.run stand-in for the KWin-script path; the journal echoes ``payload``."""
    loaded = {}

    def fake(cmd, *args, **kwargs):
        if calls is not None:
            calls.append(list(cmd))
        cmd_str = " ".join(cmd)
        if "kdotool" in cmd_str:
            return _run(1)
        if "loadScript" in cmd_str and "unloadScript" not in cmd_str:
            with open(cmd[-2]) as f:
                loaded["marker"] = f.read().split('print("')[1].split("|")[0]
            return _run(0, "42")
        if "journalctl" in cmd_str:
            return _run(0, f"some line\njs: {loaded.get('marker')}|{payload}\nother line")
        return _run(0)

    return fake


def _xdotool_out(window_id: str, title: str, class_: str) -> str:
    """What `xdotool getactivewindow getwindowgeometry --shell getwindowname getwindowclassname` prints."""
    return (f"WINDOW={window_id}\nX=0\nY=0\nWIDTH=800\nHEIGHT=600\nSCREEN=0\n"
            f"{title}\n{class_}\n")


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

        mock_run.side_effect = [
            _run(0, "1"),                        # is_kdotool_available probe
            _run(0, "999\nFirefox\nfirefox\n"),  # chained id/name/class
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
            _run(0, _xdotool_out("42", "Konsole", "org.kde.konsole")),
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
            _run(0, "{abc-123}\nFirefox - GitHub\nfirefox\n"),
        ]
        result = manager.get_active_window()
        assert result is not None
        assert isinstance(result, WindowInfo)
        assert result.method == "kdotool"
        assert result.class_ == "Firefox"
        assert result.title == "Firefox - GitHub"
        assert result.window_id == "{abc-123}"

    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_xdotool_fallback_returns_correct_window_info(self, mock_run, mock_which, manager):
        mock_which.side_effect = lambda n: "/usr/bin/xdotool" if n == "xdotool" else None
        mock_run.side_effect = [
            _run(0),
            _run(0, _xdotool_out("77", "Konsole", "org.kde.konsole")),
        ]
        result = manager.get_active_window()
        assert result is not None
        assert result.method == "xdotool"
        assert result.class_ == "Konsole"
        assert result.title == "Konsole"
        assert result.window_id == "77"

    @patch(f"{MODULE}.os.environ.get")
    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_qdbus_fallback_returns_correct_window_info(self, mock_run, mock_which, mock_env, manager):
        mock_env.return_value = "wayland-0"
        mock_which.side_effect = lambda n: "/usr/bin/qdbus6" if n == "qdbus6" else None
        mock_run.side_effect = _fake_kwin("Vivaldi|||vivaldi-stable")

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
        def mock_run_eff(*args, **kwargs):
            cmd = args[0]
            if "--version" in cmd:
                return _run(0, "1")
            if "search" in cmd:
                return _run(0, "12345\n678")
            return _run(0, "")
            
        mock_run.side_effect = mock_run_eff
        
        result = manager.search_window_by_name("Test App")
        assert result == "12345"
        
        search_cmds = [str(c.args[0]) for c in mock_run.call_args_list if "search" in str(c.args[0])]
        assert len(search_cmds) >= 1
        assert "search" in search_cmds[-1]
        assert "--name" in search_cmds[-1]
        assert "[Tt][Ee][Ss][Tt]\\\\ [Aa][Pp][Pp]" in search_cmds[-1]

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


# ---------------------------------------------------------------------------
# Polling cost, kdotool back-off and the qdbus fallback
# ---------------------------------------------------------------------------

class TestActiveWindowPolling:

    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_kdotool_poll_is_a_single_process(self, mock_run, mock_which, manager):
        # Guards three kdotool processes per 0.5 s poll.
        mock_which.side_effect = lambda n: "/usr/bin/kdotool" if n == "kdotool" else None
        mock_run.return_value = _run(0, "{id}\nTitle\nfirefox\n")
        manager.is_kdotool_available()
        mock_run.reset_mock()

        manager.get_active_window()

        assert mock_run.call_count == 1

    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_xdotool_poll_is_a_single_process(self, mock_run, mock_which, manager):
        mock_which.side_effect = lambda n: "/usr/bin/xdotool" if n == "xdotool" else None
        mock_run.return_value = _run(0, _xdotool_out("5", "T", "c"))
        manager.is_xdotool_available()
        mock_run.reset_mock()

        manager.get_active_window()

        assert mock_run.call_count == 1

    @patch(f"{MODULE}.shutil.which")
    @patch(f"{MODULE}.subprocess.run")
    def test_xdotool_null_class_falls_back_to_title(self, mock_run, mock_which, manager):
        mock_which.side_effect = lambda n: "/usr/bin/xdotool" if n == "xdotool" else None
        mock_run.side_effect = [_run(0), _run(0, _xdotool_out("5", "Doc - Firefox", "(null)"))]

        result = manager.get_active_window()

        assert result.class_ == "Firefox"

    @patch(f"{MODULE}.os.environ.get", return_value="wayland-0")
    @patch(f"{MODULE}.shutil.which", return_value="/usr/bin/tool")
    @patch(f"{MODULE}.subprocess.run")
    def test_null_active_window_is_no_window_without_fallback(self, mock_run, mock_which, mock_env, manager):
        # Guards the lock screen pushing every poll onto the journal-writing qdbus path.
        null = _run(1, "", "TypeError: Cannot read property 'internalId' of null")
        mock_run.return_value = null

        assert manager.get_active_window() is None

        cmds = [" ".join(c.args[0]) for c in mock_run.call_args_list]
        assert manager.is_kdotool_available() is True
        assert not any("qdbus6" in c or "journalctl" in c or "xdotool" in c for c in cmds)

    @patch(f"{MODULE}.os.environ.get", return_value="wayland-0")
    @patch(f"{MODULE}.shutil.which", return_value="/usr/bin/tool")
    @patch(f"{MODULE}.subprocess.run")
    @patch(f"{MODULE}.time.monotonic")
    def test_kdotool_timeout_backs_off_then_reprobes(self, mock_clock, mock_run, mock_which, mock_env, manager):
        # Guards one slow KWin reply disabling kdotool for the whole session,
        # and the qdbus fallback being used while kdotool merely backs off.
        mock_clock.return_value = 1000.0
        manager._kdotool_available = True

        def timeout_kdotool(cmd, *args, **kwargs):
            if cmd[0] == "kdotool":
                raise subprocess.TimeoutExpired(cmd, 1)
            return _run(1)
        mock_run.side_effect = timeout_kdotool

        manager.get_active_window()
        mock_run.reset_mock()
        manager.get_active_window()

        cmds = [" ".join(c.args[0]) for c in mock_run.call_args_list]
        assert not any(c.startswith("kdotool") for c in cmds)
        assert not any("qdbus6" in c or "journalctl" in c for c in cmds)

        mock_clock.return_value = 1000.0 + 61
        mock_run.side_effect = None
        mock_run.return_value = _run(0, "{id}\nTitle\nfirefox\n")

        result = manager.get_active_window()

        assert result is not None and result.method == "kdotool"

    @patch(f"{MODULE}.shutil.which", return_value="/usr/bin/qdbus6")
    @patch(f"{MODULE}.subprocess.run")
    def test_qdbus_runs_with_c_locale(self, mock_run, mock_which, manager):
        # Guards qdbus6 writing a locale warning to the journal on every call.
        mock_run.return_value = _run(0)

        manager.is_qdbus_kwin_available()

        assert mock_run.call_args.kwargs["env"]["LC_ALL"] == "C.UTF-8"


# ---------------------------------------------------------------------------
# KWin one-shot scripts
# ---------------------------------------------------------------------------

class TestKWinScript:

    def test_caption_containing_separator_is_kept(self, manager):
        # Guards a caption with "|||" in it losing the window or its class.
        with patch(f"{MODULE}.subprocess.run", side_effect=_fake_kwin("a|||b|||konsole")), \
                patch(f"{MODULE}.time.sleep"):
            result = manager._qdbus_get_active_window()

        assert result.title == "a|||b"
        assert result.class_ == "Konsole"

    def test_script_file_is_fresh_private_and_removed(self, manager, tmp_path, monkeypatch):
        # Guards script files piling up in /tmp or being reused across calls.
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        calls = []
        with patch(f"{MODULE}.subprocess.run", side_effect=_fake_kwin("T|||c", calls)), \
                patch(f"{MODULE}.time.sleep"):
            manager._qdbus_get_active_window()
            manager._qdbus_get_active_window()

        loads = [c for c in calls if c[-3].endswith(".loadScript")]
        assert len(loads) == 2
        assert loads[0][-2] != loads[1][-2]
        assert all(c[-2].startswith(str(tmp_path)) for c in loads)
        assert list(tmp_path.iterdir()) == []

    def test_script_unloaded_and_removed_when_run_fails(self, manager, tmp_path, monkeypatch):
        # Guards a failing call leaving the script loaded in KWin or on disk.
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        calls = []

        def fake(cmd, *args, **kwargs):
            calls.append(list(cmd))
            if "Script.run" in " ".join(cmd):
                raise subprocess.TimeoutExpired(cmd, 1)
            return _run(0, "42")

        with patch(f"{MODULE}.subprocess.run", side_effect=fake):
            assert manager._qdbus_get_active_window() is None

        assert any(c[-2].endswith("unloadScript") for c in calls)
        assert list(tmp_path.iterdir()) == []

    def test_journal_read_is_bounded_by_time_not_line_count(self, manager):
        # Guards the result scrolling out of a fixed "-n 20" window on a busy journal.
        calls = []
        with patch(f"{MODULE}.subprocess.run", side_effect=_fake_kwin("T|||c", calls)), \
                patch(f"{MODULE}.time.sleep"):
            manager._qdbus_get_active_window()

        journal = next(c for c in calls if c[0] == "journalctl")
        assert any(a.startswith("--since=@") for a in journal)
        assert "-n" not in journal
        assert ["-o", "cat"] == journal[journal.index("-o"):journal.index("-o") + 2]

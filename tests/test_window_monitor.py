import re
from unittest.mock import MagicMock, call, patch

import subprocess
import pytest

from StreamDock.Models import WindowInfo
from StreamDock.window_monitor import WindowMonitor


@pytest.fixture
def monitor():
    return WindowMonitor(poll_interval=0.1)

class TestWindowMonitor:
    def test_init(self, monitor):
        """Test initialization state."""
        assert monitor.poll_interval == 0.1
        assert monitor.window_rules == []
        assert monitor.running == False
        assert monitor.current_window_id is None

    def test_add_window_rule(self, monitor):
        """Test adding window rules."""
        callback = MagicMock()
        
        # Add string rule
        monitor.add_window_rule("Firefox", callback, match_field='title')
        assert len(monitor.window_rules) == 1
        rule = monitor.window_rules[0]
        assert rule['pattern'] == "Firefox"
        assert rule['callback'] == callback
        assert rule['match_field'] == 'title'
        assert rule['is_regex'] == False

        # Add regex rule
        regex = re.compile(r"^.* - YouTube$")
        monitor.add_window_rule(regex, callback)
        assert len(monitor.window_rules) == 2
        assert monitor.window_rules[1]['is_regex'] == True

    def test_clean_rules(self, monitor):
        """Test clearing rules."""
        monitor.add_window_rule("Test", lambda x: None)
        monitor.clear_rules()
        assert len(monitor.window_rules) == 0

    def test_set_default_callback(self, monitor):
        """Test setting default callback."""
        callback = MagicMock()
        monitor.set_default_callback(callback)
        assert monitor.default_callback == callback

    def test_extract_app_from_title(self, monitor):
        """Test app name extraction logic - now in WindowUtils."""
        from StreamDock.window_utils import WindowUtils

        # Common separators
        assert WindowUtils.extract_app_from_title("Doc - Word") == "Word"
        assert WindowUtils.extract_app_from_title("Song — Spotify") == "Spotify"
        assert WindowUtils.extract_app_from_title("Error: Log") == "Error"
        
        # Known apps fallback
        assert WindowUtils.extract_app_from_title("Inbox (1) - Gmail - Mozilla Firefox") == "Firefox"
        assert WindowUtils.extract_app_from_title("main.py - VSCode") == "VSCode"
        
        # Simple fallback
        assert WindowUtils.extract_app_from_title("Terminal") == "Terminal"
        assert WindowUtils.extract_app_from_title("") == "unknown"

    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available', return_value=True)
    @patch('subprocess.run')
    def test_kdotool_detection_via_utils(self, mock_run, mock_kdotool_check, monitor):
        """Test kdotool method success path via WindowUtils."""
        from StreamDock.window_utils import WindowUtils

        # Setup sequence of subprocess calls: 
        # 1. getactivewindow -> "123"
        # 2. getwindowname -> "My Window"
        # 3. getwindowclassname -> "my.class"
        
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="123\n"),
            MagicMock(returncode=0, stdout="My Window\n"),
            MagicMock(returncode=0, stdout="my.class\n")
        ]
        
        info = WindowUtils.kdotool_get_active_window()
        
        assert info is not None
        assert info.method == 'kdotool'
        assert info.title == "My Window"
        assert info.class_name == "my.class"

    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available', return_value=True)
    @patch('subprocess.run')
    def test_kdotool_fallback_class(self, mock_run, mock_kdotool_check, monitor):
        """Test kdotool relying on title extraction when class lookup fails."""
        from StreamDock.window_utils import WindowUtils
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="123\n"),
            MagicMock(returncode=0, stdout="My Window - Firefox\n"),
            MagicMock(returncode=1, stdout="") # Class lookup fails
        ]
        
        info = WindowUtils.kdotool_get_active_window()
        
        assert info is not None
        assert info.class_name == "Firefox" # Extracted from title

    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available', return_value=True)
    @patch('subprocess.run')
    def test_kdotool_failure(self, mock_run, mock_kdotool_check, monitor):
        """Test kdotool returning None on failure."""
        from StreamDock.window_utils import WindowUtils
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert WindowUtils.kdotool_get_active_window() is None

        @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available', return_value=False)
        @patch('subprocess.run')
        @patch('builtins.open', new_callable=MagicMock)
        @patch('os.path.exists', return_value=True)
        @patch('tempfile.NamedTemporaryFile')
        @patch('time.time')
        def test_kwin_scripting_native_success(self, mock_time, mock_tempfile, mock_exists, mock_open, mock_run, mock_kdotool_check, monitor):
            """Test kwin_scripting_native method success."""
            
            # Setup time for marker generation
            mock_time.return_value = 12.345
        
            # Mock file read for the source script
            mock_file_read = MagicMock()
            mock_file_read.read.return_value = 'print("MARKER_ID:" + "My Window Title|MyClass");'
        
            # Mock temp file for writing
            mock_tmp_file = MagicMock()
            mock_tmp_file.name = "/tmp/test_script.js"
            mock_tempfile.return_value.__enter__.return_value = mock_tmp_file
        
            # Configure open to return the read mock when reading
            mock_open.return_value.__enter__.return_value = mock_file_read
        
            # Helper to match journalctl command
            def run_side_effect(*args, **kwargs):
                cmd = args[0]
                if cmd[0] == 'journalctl':
                    # Return mocked journal output with marker matching the mocked time
                    # 12.345 * 1000 = 12345
                    return MagicMock(returncode=0, stdout="Jan 01 10:00:00 host kwin: js: STREAMDOCK_QUERY_12345:My Window Title|MyClass\n")
        
                if 'loadScript' in cmd:
                    return MagicMock(returncode=0, stdout="1\n")
        
                return MagicMock(returncode=0, stdout="")
        
            mock_run.side_effect = run_side_effect
        
            info = monitor.get_active_window_info()
        
            assert info is not None
            assert info.method == "kwin_scripting_native"
            assert info.title == "My Window Title"
            assert info.class_name == "MyClass"

    @patch('subprocess.run')
    def test_get_active_window_info_chain(self, mock_run, monitor):
        """Test that get_active_window_info tries methods in order."""
        # Test with simulation mode disabled - kdotool method should be tried via WindowUtils
        monitor.kdotool_available = False  # Skip kdotool
        
        # Mock the internal helper methods to verify the chain logic
        with patch.object(monitor, '_try_kwin_scripting', return_value=None) as m2, \
             patch.object(monitor, '_try_plasma_taskmanager', return_value=None) as m3, \
             patch.object(monitor, '_try_kwin_basic', return_value=WindowInfo(title='Win', class_='App', raw='Win', method='kwin')) as m4:
             
             result = monitor.get_active_window_info()
             
             assert result.title == 'Win'
             m2.assert_called_once()
             m3.assert_called_once()
             m4.assert_called_once()

    def test_check_rules_matching(self, monitor):
        """Test rule matching logic."""
        callback1 = MagicMock()
        callback2 = MagicMock()
        default_cb = MagicMock()
        
        monitor.add_window_rule("Firefox", callback1, match_field='class')
        monitor.add_window_rule("Chrome", callback2, match_field='class')
        monitor.set_default_callback(default_cb)
        
        # Case 1: Match first rule
        info = WindowInfo(title='Page', class_='Mozilla Firefox', raw='Page', method='test')
        monitor._check_rules(info)
        callback1.assert_called_with(info)
        callback2.assert_not_called()
        default_cb.assert_not_called()
        
        # Case 2: Match no rules (Default)
        callback1.reset_mock()
        info = WindowInfo(title='Terminal', class_='Konsole', raw='Terminal', method='test')
        monitor._check_rules(info)
        callback1.assert_not_called()
        default_cb.assert_called_with(info)

    def test_check_rules_regex(self, monitor):
        """Test regex rule matching."""
        callback = MagicMock()
        pattern = re.compile(r"^.*\.py - VSCode$")
        monitor.add_window_rule(pattern, callback, match_field='title')
        
        # Match
        monitor._check_rules(WindowInfo(title='test.py - VSCode', class_='Code', raw='test', method='test'))
        callback.assert_called()
        
        # No Match
        callback.reset_mock()
        monitor._check_rules(WindowInfo(title='readme.md - VSCode', class_='Code', raw='readme', method='test'))
        callback.assert_not_called()

    @patch('time.sleep') # Don't actually sleep
    @patch.object(WindowMonitor, 'get_active_window_info')
    def test_monitor_loop(self, mock_get_info, mock_sleep, monitor):
        """Test main monitor loop detects changes."""
        monitor.running = True
        
        # Sequence:
        # 1. Window A
        # 2. Window A (no change)
        # 3. Window B (change)
        # 4. Stop
        
        info_a = WindowInfo(title='A', class_='AppA', raw='A', method='test')
        info_b = WindowInfo(title='B', class_='AppB', raw='B', method='test')
        
        mock_get_info.side_effect = [info_a, info_a, info_b]
        
        # Stop loop after 3 iterations via side effect on sleep or checking count
        # Easier way: simulate threading by running one iteration logic manually 
        # OR use a counter side effect to set running=False
        
        def stop_after_3(*args):
            if mock_get_info.call_count >= 3:
                monitor.running = False
        
        mock_sleep.side_effect = stop_after_3
        
        # Spy on check_rules
        with patch.object(monitor, '_check_rules') as mock_check:
            monitor._monitor_loop()
            
            # _check_rules should be called for initial window A, and then for B
            # It should NOT be called for the second A
            assert mock_check.call_count == 2
            mock_check.assert_has_calls([call(info_a), call(info_b)])


    @patch('subprocess.run')
    def test_xdotool_fallback_logic(self, mock_run, monitor):
        """
        Verify that if kdotool/qdbus fail, we fall back to xdotool
        and correctly parse window class.
        """
        # Setup the sequence of mock responses for subprocess.run
        
        # 1. kdotool getactivewindow -> Fails (simulating crash or missing)
        kdotool_fail = MagicMock()
        kdotool_fail.returncode = 1
        
        # 2. kwin scripting -> Fails
        # 3. plasma taskmanager -> Fails
        
        # 4. kwin basic (Method 4)
        # 4a. qdbus6 -> Fails (rc=1 or empty)
        qdbus_fail = MagicMock()
        qdbus_fail.returncode = 1
        
        # 4b. busctl -> Fails or empty
        busctl_fail = MagicMock()
        busctl_fail.returncode = 0
        busctl_fail.stdout = ""
        
        # 4c. xdotool getactivewindow -> Succeeds (returns ID)
        xdotool_id_success = MagicMock()
        xdotool_id_success.returncode = 0
        xdotool_id_success.stdout = "12345\n"
        
        # 4d. xdotool getwindowname -> Succeeds
        xdotool_name_success = MagicMock()
        xdotool_name_success.returncode = 0
        xdotool_name_success.stdout = "My Window Title\n"
        
        # 4e. xdotool getwindowclassname -> Succeeds
        xdotool_class_success = MagicMock()
        xdotool_class_success.returncode = 0
        xdotool_class_success.stdout = "MyAppClass\n"
        
        # Configure side_effect to return these mocks in order
        def side_effect(*args, **kwargs):
            cmd = args[0]
            if 'kdotool' in cmd:
                return kdotool_fail
            if 'qdbus' in cmd[0] or (len(cmd) > 1 and 'qdbus' in cmd[1]): 
                return qdbus_fail 
            if 'busctl' in cmd[0] or (len(cmd) > 1 and 'busctl' in cmd[1]):
                return busctl_fail
            if 'xdotool' in cmd and 'getactivewindow' in cmd[0]:
                return xdotool_id_success
            if len(cmd) > 1 and 'xdotool' in cmd[2]: 
                 if 'getactivewindow' in cmd[2]: return xdotool_id_success

            # Direct list calls
            if cmd[0] == 'xdotool' and cmd[1] == 'getwindowname':
                return xdotool_name_success
                
            if cmd[0] == 'xdotool' and cmd[1] == 'getwindowclassname':
                return xdotool_class_success
                
            # Default fail for others
            m = MagicMock()
            m.returncode = 1
            return m

        mock_run.side_effect = side_effect
        
        # Execute
        info = monitor.get_active_window_info()
        
        # Verify
        assert info is not None, "Should return window info"
        assert info.class_name == "MyAppClass", "Should parse class from xdotool output"
        assert info.method == "kwin_basic", "Should use correct fallback method name (kwin_basic wraps xdotool)"

    # === Additional Coverage Tests - Page 2 ===
    
    def test_simulation_no_file(self, monitor):
        """Simulation mode - file doesn't exist."""
        monitor.simulation_mode = True
        import os
        if os.path.exists(monitor.simulated_window_file):
            os.remove(monitor.simulated_window_file)
        result = monitor.get_active_window_info()
        assert result is None
    
    def test_simulation_empty(self, monitor):
        """Simulation mode - empty file."""
        monitor.simulation_mode = True
        import os
        with open(monitor.simulated_window_file, 'w') as f:
            f.write("")
        try:
            result = monitor.get_active_window_info()
            assert result is None
        finally:
            os.remove(monitor.simulated_window_file)
    
    def test_check_rules_none(self, monitor):
        """_check_rules with None window."""
        callback = MagicMock()
        monitor.add_window_rule("Test", callback)
        monitor._check_rules(None)
        callback.assert_not_called()
    
    def test_all_methods_fail(self, monitor):
        """All detection methods fail."""
        monitor.simulation_mode = False
        with patch('StreamDock.window_monitor.WindowUtils.is_kdotool_available', return_value=False):
            with patch.object(monitor, '_try_kwin_scripting', return_value=None):
                with patch.object(monitor, '_try_plasma_taskmanager', return_value=None):
                    with patch.object(monitor, '_try_kwin_basic', return_value=None):
                        result = monitor.get_active_window_info()
                        assert result is None
    
    @patch('StreamDock.window_monitor.subprocess.run')
    def test_plasma_timeout(self, mock_run, monitor):
        """Plasma taskmanager timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired('cmd', 1)
        result = monitor._try_plasma_taskmanager()
        assert result is None
    
    @patch('StreamDock.window_monitor.subprocess.run')
    def test_kwin_basic_fail(self, mock_run, monitor):
        """KWin basic all fail."""
        mock_ret = MagicMock()
        mock_ret.returncode = 1
        mock_ret.stdout = ""
        mock_run.return_value = mock_ret
        result = monitor._try_kwin_basic()
        assert result is None
    
    def test_callback_exception(self, monitor):
        """Callback exception handling."""
        def bad_callback(win):
            raise RuntimeError("Error")
        monitor.add_window_rule("Test", bad_callback)
        win_info = WindowInfo(title="Test", class_="test", raw="test", method="test")
        try:
            monitor._check_rules(win_info)
        except RuntimeError:
            pytest.fail("Should catch exception")
    
    def test_window_id_tracking(self, monitor):
        """Test window ID tracking works."""
        monitor.simulation_mode = True
        import os
        with open(monitor.simulated_window_file, 'w') as f:
            f.write("Firefox|firefox")
        try:
            info1 = monitor.get_active_window_info()
            info2 = monitor.get_active_window_info()
            assert info1 is not None
            assert info2 is not None
        finally:
            if os.path.exists(monitor.simulated_window_file):
                os.remove(monitor.simulated_window_file)

    # === KWin Helper Function Tests ===
    
    @patch('os.path.exists')
    def test_prepare_kwin_script_no_file(self, mock_exists, monitor):
        """Test _prepare_kwin_script when script file doesn't exist."""
        mock_exists.return_value = False
        result = monitor._prepare_kwin_script()
        assert result is None
    
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    def test_prepare_kwin_script_success(self, mock_exists, mock_tempfile, monitor):
        """Test _prepare_kwin_script successful execution."""
        mock_exists.return_value = True
        
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = "MARKER_ID content"
        
        # Mock temp file
        mock_temp = MagicMock()
        mock_temp.name = "/tmp/test.js"
        mock_tempfile.return_value.__enter__.return_value = mock_temp
        
        with patch('builtins.open', return_value=mock_file):
            result = monitor._prepare_kwin_script()
        
        assert result is not None
        assert len(result) == 2
        script_path, marker = result
        assert script_path == "/tmp/test.js"
        assert "STREAMDOCK_QUERY" in marker
    
    @patch('StreamDock.window_monitor.subprocess.run')
    def test_load_kwin_script_success(self, mock_run, monitor):
        """Test _load_kwin_script successful load."""
        mock_ret = MagicMock()
        mock_ret.returncode = 0
        mock_ret.stdout = "123"
        mock_ret.stderr = ""
        mock_run.return_value = mock_ret
        
        result = monitor._load_kwin_script("/tmp/test.js", "plugin")
        assert result == 123
    
    @patch('StreamDock.window_monitor.subprocess.run')
    def test_load_kwin_script_invalid_id(self, mock_run, monitor):
        """Test _load_kwin_script with invalid script ID."""
        mock_ret = MagicMock()
        mock_ret.returncode = 0
        mock_ret.stdout = "-1"
        mock_ret.stderr = ""
        mock_run.return_value = mock_ret
        
        result = monitor._load_kwin_script("/tmp/test.js", "plugin")
        assert result is None
    
    @patch('StreamDock.window_monitor.subprocess.run')
    def test_load_kwin_script_command_fail(self, mock_run, monitor):
        """Test _load_kwin_script when command fails."""
        mock_ret = MagicMock()
        mock_ret.returncode = 1
        mock_ret.stdout = ""
        mock_ret.stderr = "error"
        mock_run.return_value = mock_ret
        
        result = monitor._load_kwin_script("/tmp/test.js", "plugin")
        assert result is None
    
    @patch('StreamDock.window_monitor.subprocess.run')
    def test_parse_journal_marker_found(self, mock_run, monitor):
        """Test _parse_journal_for_window finds marker."""
        mock_ret = MagicMock()
        mock_ret.returncode = 0
        mock_ret.stdout = "TEST_MARKER_123:Firefox|firefox\n"
        mock_run.return_value = mock_ret
        
        result = monitor._parse_journal_for_window("TEST_MARKER_123")
        assert result is not None
        assert result.title == "Firefox"
        assert result.class_ == "Firefox"  # Normalized by WindowUtils
    
    @patch('StreamDock.window_monitor.subprocess.run')
    def test_parse_journal_marker_not_found(self, mock_run, monitor):
        """Test _parse_journal_for_window marker not found."""
        mock_ret = MagicMock()
        mock_ret.returncode = 0
        mock_ret.stdout = "other log output\n"
        mock_run.return_value = mock_ret
        
        result = monitor._parse_journal_for_window("TEST_MARKER_123")
        assert result is None
    
    @patch('StreamDock.window_monitor.subprocess.run')
    def test_parse_journal_none_window(self, mock_run, monitor):
        """Test _parse_journal_for_window with None|None window."""
        mock_ret = MagicMock()
        mock_ret.returncode = 0
        mock_ret.stdout = "TEST_MARKER_456:None|None\n"
        mock_run.return_value = mock_ret
        
        result = monitor._parse_journal_for_window("TEST_MARKER_456")
        assert result is None
    
    @patch('StreamDock.window_monitor.subprocess.run')
    @patch('os.path.exists')
    @patch('os.unlink')
    def test_cleanup_kwin_script(self, mock_unlink, mock_exists, mock_run, monitor):
        """Test _cleanup_kwin_script cleans up properly."""
        mock_exists.return_value = True
        
        monitor._cleanup_kwin_script("/tmp/test.js", 123, "plugin")
        
        # Should call unload
        assert any('unloadScript' in str(call) for call in mock_run.call_args_list)
        # Should delete file
        mock_unlink.assert_called_with("/tmp/test.js")
    
    @patch('os.path.exists')
    def test_cleanup_kwin_script_no_script_id(self, mock_exists, monitor):
        """Test _cleanup_kwin_script with no script ID."""
        mock_exists.return_value = False
        
        # Should not crash
        monitor._cleanup_kwin_script("/tmp/test.js", None, "plugin")

import re
from unittest.mock import MagicMock, call, patch

import pytest

from StreamDock.window_monitor import WindowMonitor
from StreamDock.Models import WindowInfo


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
        from StreamDock.WindowUtils import WindowUtils
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

    @patch('StreamDock.WindowUtils.WindowUtils.is_kdotool_available', return_value=True)
    @patch('subprocess.run')
    def test_kdotool_detection_via_utils(self, mock_run, mock_kdotool_check, monitor):
        """Test kdotool method success path via WindowUtils."""
        from StreamDock.WindowUtils import WindowUtils
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

    @patch('StreamDock.WindowUtils.WindowUtils.is_kdotool_available', return_value=True)
    @patch('subprocess.run')
    def test_kdotool_fallback_class(self, mock_run, mock_kdotool_check, monitor):
        """Test kdotool relying on title extraction when class lookup fails."""
        from StreamDock.WindowUtils import WindowUtils
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="123\n"),
            MagicMock(returncode=0, stdout="My Window - Firefox\n"),
            MagicMock(returncode=1, stdout="") # Class lookup fails
        ]
        
        info = WindowUtils.kdotool_get_active_window()
        
        assert info is not None
        assert info.class_name == "Firefox" # Extracted from title

    @patch('StreamDock.WindowUtils.WindowUtils.is_kdotool_available', return_value=True)
    @patch('subprocess.run')
    def test_kdotool_failure(self, mock_run, mock_kdotool_check, monitor):
        """Test kdotool returning None on failure."""
        from StreamDock.WindowUtils import WindowUtils
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert WindowUtils.kdotool_get_active_window() is None

    @patch('subprocess.run')
    def test_get_active_window_info_chain(self, mock_run, monitor):
        """Test that get_active_window_info tries methods in order."""
        # Test with simulation mode disabled - kdotool method should be tried via WindowUtils
        monitor.kdotool_available = False  # Skip kdotool
        
        # Mock the internal helper methods to verify the chain logic
        with patch.object(monitor, '_try_kwin_scripting', return_value=None) as m2, \
             patch.object(monitor, '_try_plasma_taskmanager', return_value=None) as m3, \
             patch.object(monitor, '_try_kwin_basic', return_value=WindowInfo(title='Win', class_name='App', raw='Win', method='kwin')) as m4:
             
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
        info = WindowInfo(title='Page', class_name='Mozilla Firefox', raw='Page', method='test')
        monitor._check_rules(info)
        callback1.assert_called_with(info)
        callback2.assert_not_called()
        default_cb.assert_not_called()
        
        # Case 2: Match no rules (Default)
        callback1.reset_mock()
        info = WindowInfo(title='Terminal', class_name='Konsole', raw='Terminal', method='test')
        monitor._check_rules(info)
        callback1.assert_not_called()
        default_cb.assert_called_with(info)

    def test_check_rules_regex(self, monitor):
        """Test regex rule matching."""
        callback = MagicMock()
        pattern = re.compile(r"^.*\.py - VSCode$")
        monitor.add_window_rule(pattern, callback, match_field='title')
        
        # Match
        monitor._check_rules(WindowInfo(title='test.py - VSCode', class_name='Code', raw='test', method='test'))
        callback.assert_called()
        
        # No Match
        callback.reset_mock()
        monitor._check_rules(WindowInfo(title='readme.md - VSCode', class_name='Code', raw='readme', method='test'))
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
        
        info_a = WindowInfo(title='A', class_name='AppA', raw='A', method='test')
        info_b = WindowInfo(title='B', class_name='AppB', raw='B', method='test')
        
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
    def test_xprop_fallback_logic(self, mock_run, monitor):
        """
        Verify that if kdotool/qdbus fail, we fall back to xdotool+xprop 
        and correctly parse WM_CLASS.
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
        
        # 4e. xprop -id 12345 WM_CLASS -> Succeeds
        xprop_success = MagicMock()
        xprop_success.returncode = 0
        xprop_success.stdout = 'WM_CLASS(STRING) = "my_app_instance", "MyAppClass"\n'
        
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
                
            if cmd[0] == 'xprop' and cmd[1] == '-id' and cmd[3] == 'WM_CLASS':
                return xprop_success
                
            # Default fail for others
            m = MagicMock()
            m.returncode = 1
            return m

        mock_run.side_effect = side_effect
        
        # Execute
        info = monitor.get_active_window_info()
        
        # Verify
        assert info is not None, "Should return window info"
        assert info['class'] == "MyAppClass", "Should parse class from xprop output"
        assert info['method'] == "xdotool_xprop", "Should use correct fallback method"

import pytest
from unittest.mock import MagicMock, call, patch
import re
from src.StreamDock.window_monitor import WindowMonitor

@pytest.fixture
def monitor():
    return WindowMonitor(poll_interval=0.1)

class TestWindowMonitor:
    def test_init(self, monitor):
        """Test initialization state."""
        assert monitor.poll_interval == 0.1
        assert monitor.window_rules == []
        assert monitor.running == False
        assert monitor.current_window is None

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
        """Test app name extraction logic."""
        # Common separators
        assert monitor._extract_app_from_title("Doc - Word") == "Word"
        assert monitor._extract_app_from_title("Song — Spotify") == "Spotify"
        assert monitor._extract_app_from_title("Error: Log") == "Error"
        
        # Known apps fallback
        assert monitor._extract_app_from_title("Inbox (1) - Gmail - Mozilla Firefox") == "Mozilla Firefox"
        assert monitor._extract_app_from_title("main.py - VSCode") == "VSCode"
        
        # Simple fallback
        assert monitor._extract_app_from_title("Terminal") == "Terminal"
        assert monitor._extract_app_from_title("") == "unknown"

    @patch('subprocess.run')
    def test_try_kdotool_success(self, mock_run, monitor):
        """Test kdotool method success path."""
        # Setup sequence of subprocess calls: 
        # 1. getactivewindow -> "123"
        # 2. getwindowname -> "My Window"
        # 3. getwindowclassname -> "my.class"
        
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="123\n"),
            MagicMock(returncode=0, stdout="My Window\n"),
            MagicMock(returncode=0, stdout="my.class\n")
        ]
        
        info = monitor._try_kdotool()
        
        assert info is not None
        assert info['method'] == 'kdotool'
        assert info['title'] == "My Window"
        assert info['class'] == "my.class"

    @patch('subprocess.run')
    def test_try_kdotool_fallback_class(self, mock_run, monitor):
        """Test kdotool relying on title extraction when class lookup fails."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="123\n"),
            MagicMock(returncode=0, stdout="My Window - Firefox\n"),
            MagicMock(returncode=1, stdout="") # Class lookup fails
        ]
        
        info = monitor._try_kdotool()
        
        assert info is not None
        assert info['class'] == "Firefox" # Extracted from title

    @patch('subprocess.run')
    def test_try_kdotool_failure(self, mock_run, monitor):
        """Test kdotool returning None on failure."""
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert monitor._try_kdotool() is None

    @patch('subprocess.run')
    def test_get_active_window_info_chain(self, mock_run, monitor):
        """Test that get_active_window_info tries methods in order."""
        # 1. kdotool fails
        # 2. kwin script fails
        # 3. plasma taskmanager fails
        # 4. kwin basic succeeds
        
        # We mock the internal helper methods to verify the chain logic simpler
        with patch.object(monitor, '_try_kdotool', return_value=None) as m1, \
             patch.object(monitor, '_try_kwin_scripting', return_value=None) as m2, \
             patch.object(monitor, '_try_plasma_taskmanager', return_value=None) as m3, \
             patch.object(monitor, '_try_kwin_basic', return_value={'title': 'Win'}) as m4:
             
             result = monitor.get_active_window_info()
             
             assert result == {'title': 'Win'}
             m1.assert_called_once()
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
        info = {'class': 'Mozilla Firefox', 'title': 'Page'}
        monitor._check_rules(info)
        callback1.assert_called_with(info)
        callback2.assert_not_called()
        default_cb.assert_not_called()
        
        # Case 2: Match no rules (Default)
        callback1.reset_mock()
        info = {'class': 'Konsole', 'title': 'Terminal'}
        monitor._check_rules(info)
        callback1.assert_not_called()
        default_cb.assert_called_with(info)

    def test_check_rules_regex(self, monitor):
        """Test regex rule matching."""
        callback = MagicMock()
        pattern = re.compile(r"^.*\.py - VSCode$")
        monitor.add_window_rule(pattern, callback, match_field='title')
        
        # Match
        monitor._check_rules({'title': 'test.py - VSCode', 'class': 'Code'})
        callback.assert_called()
        
        # No Match
        callback.reset_mock()
        monitor._check_rules({'title': 'readme.md - VSCode', 'class': 'Code'})
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
        
        info_a = {'title': 'A', 'class': 'AppA'}
        info_b = {'title': 'B', 'class': 'AppB'}
        
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


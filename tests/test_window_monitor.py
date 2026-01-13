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

    @patch('StreamDock.window_monitor.WindowMonitor.get_active_window_info')
    def test_monitor_loop(self, mock_get_info, monitor):
        """Test main monitor loop detects changes."""
        monitor.running = True
        
        info_a = WindowInfo(title='A', class_='AppA', raw='A', method='test')
        info_b = WindowInfo(title='B', class_='AppB', raw='B', method='test')
        
        mock_get_info.side_effect = [info_a, info_a, info_b]
        
        # Spy on check_rules
        with patch.object(monitor, '_check_rules') as mock_check:
            # Run minimal iterations to simulate loop
            # Iteration 1
            info = monitor.get_active_window_info() # info_a
            if info.class_name != monitor.current_window_id:
                monitor.current_window_id = info.class_name
                monitor._check_rules(info)
            
            # Iteration 2
            info = monitor.get_active_window_info() # info_a
            if info.class_name != monitor.current_window_id:
                 monitor.current_window_id = info.class_name
                 monitor._check_rules(info)

            # Iteration 3
            info = monitor.get_active_window_info() # info_b
            if info.class_name != monitor.current_window_id:
                 monitor.current_window_id = info.class_name
                 monitor._check_rules(info)
            
            assert mock_check.call_count == 2
            mock_check.assert_has_calls([call(info_a), call(info_b)])

    def test_strategies_initialization(self, monitor):
        """Test that strategies are initialized correctly."""
        monitor.simulation_mode = False
        # Re-init to trigger standard strategy population
        monitor.__init__(poll_interval=0.1, simulation_mode=False)
        assert len(monitor.strategies) > 0
        assert any(s.name == "kwin_dynamic" for s in monitor.strategies)
        assert any(s.name == "kdotool" for s in monitor.strategies)

    def test_get_active_window_info_strategy_fallback(self, monitor):
        """Test that get_active_window_info falls back through strategies."""
        # Create mock strategies
        strat1 = MagicMock()
        strat1.is_available = True
        strat1.detect.return_value = None
        strat1.name = "strat1"
        
        strat2 = MagicMock()
        strat2.is_available = True
        strat2.detect.return_value = WindowInfo(title="Success", class_="App", method="strat2")
        strat2.name = "strat2"
        
        monitor.strategies = [strat1, strat2]
        
        info = monitor.get_active_window_info()
        
        assert info is not None
        assert info.title == "Success"
        assert info.method == "strat2"
        strat1.detect.assert_called_once()
        strat2.detect.assert_called_once()
        assert monitor.current_window_detection_method == "strat2"

    def test_get_active_window_info_all_fail(self, monitor):
        """Test when all strategies fail."""
        strat1 = MagicMock()
        strat1.is_available = True
        strat1.detect.return_value = None
        
        monitor.strategies = [strat1]
        
        assert monitor.get_active_window_info() is None


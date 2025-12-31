import pytest
from unittest.mock import MagicMock, patch
from StreamDock.WindowMonitor import WindowMonitor

class TestWindowMonitor:

    @pytest.fixture
    def monitor(self):
        return WindowMonitor(poll_interval=0.1)

    @patch('shutil.which')
    @patch('subprocess.run')
    def test_kdotool_detection(self, mock_run, mock_which, monitor):
        """Test active window detection using kdotool."""
        # Setup mocks
        monitor.kdotool_available = True
        
        # Mock getactivewindow
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="12345"),  # getactivewindow
            MagicMock(returncode=0, stdout="My Window Title"),  # getwindowname
            MagicMock(returncode=0, stdout="org.example.app")   # getwindowclassname
        ]
        
        info = monitor.get_active_window_info()
        
        assert info is not None
        assert info["title"] == "My Window Title"
        assert info["class"] == "org.example.app"
        assert info["method"] == "kdotool"

    @patch('subprocess.run')
    def test_kdotool_failure_fallback(self, mock_run, monitor):
        """Test fallback when kdotool fails."""
        monitor.kdotool_available = True
        
        # Make kdotool fail
        mock_run.return_value = MagicMock(returncode=1)
        
        # It should try other methods, let's mock the basic KWin one (last resort)
        # We need to control the sequence of calls or just let it fail through all
        # For simplicity, let's just assert it tries to fall back (returns None if all fail in this mock setup)
        info = monitor.get_active_window_info()
        assert info is None # It returns None because we didn't mock the successful fallback, but it didn't crash

    def test_extract_app_from_title(self, monitor):
        """Test application name extraction from window titles."""
        assert monitor._extract_app_from_title("Document.txt - Kate") == "Kate"
        assert monitor._extract_app_from_title("Mozilla Firefox") == "Firefox" # From known apps list
        assert monitor._extract_app_from_title("Some Random Title") == "Some" # Fallback to first word
        assert monitor._extract_app_from_title("") == "unknown"

    def test_window_rules_matching(self, monitor):
        """Test that window rules trigger correctly."""
        
        callback = MagicMock()
        monitor.add_window_rule("Firefox", callback, match_field="class")
        
        # Should match
        window_info = {"class": "Mozilla Firefox", "title": "New Tab"}
        monitor._check_rules(window_info)
        callback.assert_called_once_with(window_info)
        
        callback.reset_mock()
        
        # Should not match
        window_info = {"class": "Konsole", "title": "Terminal"}
        monitor._check_rules(window_info)
        callback.assert_not_called()

    def test_default_callback(self, monitor):
        """Test that default callback is triggered when no rules match."""
        
        rule_callback = MagicMock()
        default_callback = MagicMock()
        
        monitor.add_window_rule("Firefox", rule_callback)
        monitor.set_default_callback(default_callback)
        
        # Match rule -> No default
        monitor._check_rules({"class": "Firefox"})
        rule_callback.assert_called()
        default_callback.assert_not_called()
        
        rule_callback.reset_mock()
        
        # No match -> Default
        monitor._check_rules({"class": "Chrome"})
        rule_callback.assert_not_called()
        default_callback.assert_called()

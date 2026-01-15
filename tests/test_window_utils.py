import unittest
from unittest.mock import MagicMock, patch, call
import subprocess
import os
from StreamDock.window_utils import WindowUtils

class TestWindowUtils(unittest.TestCase):
    
    def setUp(self):
        # Reset cache before each test
        WindowUtils.refresh_tool_cache()

    @patch('shutil.which')
    @patch('subprocess.run')
    def test_kdotool_availability(self, mock_run, mock_which):
        """Test kdotool availability check and caching."""
        # Case 1: kdotool missing
        mock_which.return_value = None
        self.assertFalse(WindowUtils.is_kdotool_available())
        mock_which.assert_called_with('kdotool')
        
        # Verify caching (should not call which again)
        mock_which.reset_mock()
        self.assertFalse(WindowUtils.is_kdotool_available())
        mock_which.assert_not_called()
        
        # Case 2: kdotool present but failing
        WindowUtils.refresh_tool_cache()
        mock_which.return_value = '/usr/bin/kdotool'
        mock_run.return_value.returncode = 1
        self.assertFalse(WindowUtils.is_kdotool_available())
        
        # Case 3: kdotool present and working
        WindowUtils.refresh_tool_cache()
        mock_run.return_value.returncode = 0
        self.assertTrue(WindowUtils.is_kdotool_available())

    @patch('shutil.which')
    @patch('subprocess.run')
    def test_xdotool_availability(self, mock_run, mock_which):
        """Test xdotool availability check and caching."""
        # Case 1: Working
        mock_which.return_value = '/usr/bin/xdotool'
        mock_run.return_value.returncode = 0
        self.assertTrue(WindowUtils.is_xdotool_available())
        
        # Verify caching
        mock_which.reset_mock()
        self.assertTrue(WindowUtils.is_xdotool_available())
        mock_which.assert_not_called()

    @patch('shutil.which')
    def test_wmctrl_availability(self, mock_which):
        """Test wmctrl availability check and caching."""
        # Case 1: Present
        mock_which.return_value = '/usr/bin/wmctrl'
        self.assertTrue(WindowUtils.is_wmctrl_available())
        
        # Case 2: Reset and Missing
        WindowUtils.refresh_tool_cache()
        mock_which.return_value = None
        self.assertFalse(WindowUtils.is_wmctrl_available())

    @patch('subprocess.run')
    def test_is_process_running(self, mock_run):
        """Test process running check."""
        # Case 1: Running
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "1234\n"
        self.assertTrue(WindowUtils.is_process_running("firefox"))
        mock_run.assert_called_with(['pgrep', '-x', 'firefox'], capture_output=True, text=True, timeout=1)
        
        # Case 2: Not Running
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        self.assertFalse(WindowUtils.is_process_running("firefox"))
        
        # Case 3: Error/Timeout
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='pgrep', timeout=1)
        self.assertFalse(WindowUtils.is_process_running("firefox"))

    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available')
    @patch('StreamDock.window_utils.WindowUtils.kdotool_search_by_class')
    @patch('StreamDock.window_utils.WindowUtils.kdotool_activate_window')
    @patch('os.environ.get')
    def test_activate_window_wayland(self, mock_env_get, mock_activate, mock_search, mock_is_avail):
        """Test window activation in Wayland session."""
        mock_env_get.return_value = 'wayland'
        mock_is_avail.return_value = True
        
        # Found by class
        mock_search.return_value = '100'
        mock_activate.return_value = True
        
        self.assertTrue(WindowUtils.activate_window('firefox'))
        mock_search.assert_called_with('firefox')
        mock_activate.assert_called_with('100')

    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    @patch('StreamDock.window_utils.WindowUtils.xdotool_search_by_class')
    @patch('StreamDock.window_utils.WindowUtils.xdotool_activate_window')
    @patch('os.environ.get')
    def test_activate_window_x11(self, mock_env_get, mock_activate, mock_search, mock_is_avail):
        """Test window activation in X11 session."""
        mock_env_get.return_value = 'x11'
        mock_is_avail.return_value = True
        
        # Found by class
        mock_search.return_value = '200'
        mock_activate.return_value = True
        
        self.assertTrue(WindowUtils.activate_window('firefox'))
        mock_search.assert_called_with('firefox')
        mock_activate.assert_called_with('200')

    @patch('StreamDock.window_utils.WindowUtils.is_wmctrl_available')
    @patch('StreamDock.window_utils.WindowUtils.wmctrl_activate_window')
    @patch('os.environ.get')
    def test_activate_window_fallback(self, mock_env_get, mock_wmctrl_act, mock_wmctrl_avail):
        """Test fallback to wmctrl if primary method fails."""
        mock_env_get.return_value = 'x11'
        
        # Mock xdotool failure (indirectly by mocking the search method to return None)
        with patch('StreamDock.window_utils.WindowUtils.xdotool_search_by_class', return_value=None):
            mock_wmctrl_avail.return_value = True
            mock_wmctrl_act.return_value = True
            
            self.assertTrue(WindowUtils.activate_window('firefox'))
            mock_wmctrl_act.assert_called_with('firefox')


    @patch('shutil.which')
    def test_dbus_availability(self, mock_which):
        """Test dbus-send availability check."""
        mock_which.return_value = '/usr/bin/dbus-send'
        self.assertTrue(WindowUtils.is_dbus_available())
        
        WindowUtils.refresh_tool_cache()
        mock_which.return_value = None
        self.assertFalse(WindowUtils.is_dbus_available())

    @patch('shutil.which')
    def test_pactl_availability(self, mock_which):
        """Test pactl availability check."""
        mock_which.return_value = '/usr/bin/pactl'
        self.assertTrue(WindowUtils.is_pactl_available())
        
        WindowUtils.refresh_tool_cache()
        mock_which.return_value = None
        self.assertFalse(WindowUtils.is_pactl_available())

    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    @patch('subprocess.run')
    def test_xdotool_key(self, mock_run, mock_is_avail):
        """Test xdotool key simulation."""
        mock_is_avail.return_value = True
        
        # Success
        mock_run.return_value.returncode = 0
        self.assertTrue(WindowUtils.xdotool_key("ctrl+c"))
        mock_run.assert_called_with(['xdotool', 'key', 'ctrl+c'], check=True, capture_output=True)
        
        # Failure
        mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
        self.assertFalse(WindowUtils.xdotool_key("ctrl+c"))
        
        # Unavailable
        mock_is_avail.return_value = False
        self.assertFalse(WindowUtils.xdotool_key("ctrl+c"))

    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    @patch('subprocess.run')
    def test_xdotool_type(self, mock_run, mock_is_avail):
        """Test xdotool text typing."""
        mock_is_avail.return_value = True
        
        # Should call xdotool key for each char with some logic
        # We just verify it calls subprocess, implementation details are complex
        WindowUtils.xdotool_type("a")
        self.assertTrue(mock_run.called)
        
        # Verify fallback is working if main fails? 
        # The main implementation has a broad try/except. 
        # If we make the main block fail, should stick to fallback.
        
        mock_run.reset_mock()
        mock_run.side_effect = Exception("Main block fail")
        
        WindowUtils.xdotool_type("b") 
        # Should trigger fallback: xdotool type ...
        calls = mock_run.call_args_list
        # We expect at least one call that matches the fallback signature
        fallback_called = any('type' in call.args[0] for call in calls)
        self.assertTrue(fallback_called)

if __name__ == '__main__':
    unittest.main()

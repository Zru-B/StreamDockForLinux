import unittest
from unittest.mock import MagicMock, patch

from StreamDock.business_logic.action_type import ActionType
from StreamDock.business_logic.action_executor import ActionExecutor
from StreamDock.infrastructure.system_interface import SystemInterface


class TestActionExecutor(unittest.TestCase):

    def setUp(self):
        self.mock_system = MagicMock(spec=SystemInterface)
        self.executor = ActionExecutor(self.mock_system)
        
    def test_execute_command(self):
        """Test executing a shell command via SystemInterface."""
        self.executor.execute_action((ActionType.EXECUTE_COMMAND, "echo hello"))
        self.mock_system.execute_command.assert_called_once_with("echo hello")

    def test_key_press(self):
        """Test key combination emulation via SystemInterface."""
        self.executor.execute_action((ActionType.KEY_PRESS, "CTRL+C"))
        self.mock_system.send_key_combo.assert_called_once_with("ctrl+c")
        
        self.mock_system.reset_mock()
        self.executor.execute_action((ActionType.KEY_PRESS, "ALT+F4"))
        self.mock_system.send_key_combo.assert_called_once_with("alt+F4")

    def test_type_text(self):
        """Test typing text via SystemInterface."""
        self.executor.execute_action((ActionType.TYPE_TEXT, "Hello world"))
        self.mock_system.type_text.assert_called_once_with("Hello world")

    def test_brightness_adjust(self):
        """Test changing brightness."""
        mock_device = MagicMock()
        mock_device._current_brightness = 50
        
        # Up
        self.executor.execute_action((ActionType.DEVICE_BRIGHTNESS_UP, None), device=mock_device)
        mock_device.set_brightness.assert_called_with(60)
        
        # Down
        self.executor.execute_action((ActionType.DEVICE_BRIGHTNESS_DOWN, None), device=mock_device)
        mock_device.set_brightness.assert_called_with(50)

    @patch('StreamDock.business_logic.action_executor.subprocess.run')
    def test_dbus_command(self, mock_run):
        """Test D-Bus command dispatch."""
        self.executor.execute_action((ActionType.DBUS, {"action": "play_pause"}))
        mock_run.assert_called_once()
        self.assertIn("PlayPause", mock_run.call_args[0][0])

    @patch('StreamDock.business_logic.action_executor._launch_detached')
    @patch('StreamDock.window_utils.WindowUtils.is_process_running')
    def test_launch_app_force_new(self, mock_is_running, mock_launch):
        """Test forced app launch."""
        self.executor.execute_action((ActionType.LAUNCH_APPLICATION, {"command": ["firefox"], "force_new": True}))
        mock_launch.assert_called_once_with(["firefox"])
        mock_is_running.assert_not_called()

    @patch('StreamDock.business_logic.action_executor._launch_detached')
    @patch('StreamDock.window_utils.WindowUtils.is_process_running')
    def test_launch_app_not_running(self, mock_is_running, mock_launch):
        """Test launching app when not running."""
        mock_is_running.return_value = False
        self.executor.execute_action((ActionType.LAUNCH_APPLICATION, {"command": ["firefox"]}))
        mock_launch.assert_called_once_with(["firefox"])

    @patch('StreamDock.business_logic.action_executor._launch_detached')
    @patch('StreamDock.window_utils.WindowUtils.is_process_running')
    @patch('StreamDock.window_utils.WindowUtils.activate_window')
    def test_launch_app_focuses(self, mock_activate, mock_is_running, mock_launch):
        """Test focusing existing app."""
        mock_is_running.return_value = True
        self.mock_system.search_window_by_class.return_value = "12345"
        self.mock_system.activate_window.return_value = True
        
        self.executor.execute_action((ActionType.LAUNCH_APPLICATION, {"command": ["firefox"]}))
        
        self.mock_system.search_window_by_class.assert_called_once_with("firefox")
        self.mock_system.activate_window.assert_called_once_with("12345")
        mock_launch.assert_not_called()

    @patch('StreamDock.business_logic.action_executor.time.sleep')
    def test_wait(self, mock_sleep):
        """Test WAIT action."""
        self.executor.execute_action((ActionType.WAIT, 0.5))
        mock_sleep.assert_called_once_with(0.5)

    def test_change_layout(self):
        """Test CHANGE_LAYOUT action."""
        mock_device = MagicMock()
        mock_layout = MagicMock()
        mock_layout.clear_all = True
        
        self.executor.execute_action((ActionType.CHANGE_LAYOUT, {"layout": mock_layout}), device=mock_device)
        mock_layout.apply.assert_called_once()

    def test_change_key_image(self):
        """Test CHANGE_KEY_IMAGE action."""
        mock_device = MagicMock()
        self.executor.execute_action((ActionType.CHANGE_KEY_IMAGE, "test.png"), device=mock_device, key_number=1)
        mock_device.set_key_image.assert_called_once_with(1, "test.png")

if __name__ == '__main__':
    unittest.main()

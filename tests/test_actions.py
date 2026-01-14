import subprocess
import sys
import unittest
from unittest.mock import MagicMock, call, patch

from StreamDock.actions import (ActionType, adjust_device_brightness,
                                emulate_key_combo, execute_action,
                                execute_command, launch_or_focus_application,
                                send_dbus_command, type_text)


class TestActions(unittest.TestCase):

    @patch('StreamDock.actions.subprocess.Popen')
    def test_execute_command(self, mock_popen):
        """Test executing a shell command detached."""
        command = "echo hello"
        execute_command(command)
        
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        
        # Verify nohup command construction
        self.assertIn("nohup echo hello", args[0])
        self.assertTrue(kwargs['start_new_session'])
        self.assertTrue(kwargs['close_fds'])

    @patch('StreamDock.actions.WindowUtils.is_xdotool_available')
    @patch('StreamDock.actions.subprocess.run')
    def test_emulate_key_combo(self, mock_run, mock_is_available):
        """Test key combination emulation."""
        mock_is_available.return_value = True
        
        emulate_key_combo("CTRL+C")
        mock_run.assert_called_with(['xdotool', 'key', 'ctrl+c'], check=True)
        
        emulate_key_combo("ALT+F4")
        mock_run.assert_called_with(['xdotool', 'key', 'alt+F4'], check=True)

    @patch('StreamDock.actions.WindowUtils.is_xdotool_available')
    @patch('StreamDock.actions.WindowUtils.xdotool_get_active_window')
    @patch('StreamDock.actions.subprocess.run')
    @patch('StreamDock.actions.subprocess.check_output')
    def test_type_text(self, mock_check_output, mock_run, mock_get_window, mock_is_available):
        """Test typing text."""
        # Mock availability
        mock_is_available.return_value = True
        
        # Mock getting active window ID
        mock_get_window.return_value = MagicMock() # Return truthy
        mock_check_output.return_value = b'12345\n'
        
        type_text("Hi")
        
        # Verify calls for each character
        # 'H'
        mock_run.assert_any_call(
            ['xdotool', 'windowactivate', '--sync', '12345', 'key', '--clearmodifiers', 'H'],
            check=True, stderr=subprocess.PIPE, text=True, timeout=0.5
        )
        # 'i'
        mock_run.assert_any_call(
            ['xdotool', 'windowactivate', '--sync', '12345', 'key', '--clearmodifiers', 'i'],
            check=True, stderr=subprocess.PIPE, text=True, timeout=0.5
        )

    def test_adjust_device_brightness(self):
        """Test adjusting device brightness."""
        mock_device = MagicMock()
        mock_device._current_brightness = 50
        
        # Increase
        adjust_device_brightness(mock_device, 10)
        mock_device.set_brightness.assert_called_with(60)
        self.assertEqual(mock_device._current_brightness, 60)
        
        # Decrease below 0
        mock_device._current_brightness = 5
        adjust_device_brightness(mock_device, -10)
        mock_device.set_brightness.assert_called_with(0)
        self.assertEqual(mock_device._current_brightness, 0)
        
        # Max out
        mock_device._current_brightness = 95
        adjust_device_brightness(mock_device, 10)
        mock_device.set_brightness.assert_called_with(100)

    @patch('StreamDock.actions.subprocess.run')
    def test_send_dbus_command(self, mock_run):
        """Test D-Bus commands."""
        # Shortcut
        send_dbus_command({"action": "volume_up"})
        mock_run.assert_called_with(
            "pactl set-sink-volume @DEFAULT_SINK@ +5%",
            shell=True, check=True, capture_output=True
        )
        
        # Direct string
        send_dbus_command("dbus-send ...")
        mock_run.assert_called_with(
            "dbus-send ...",
            shell=True, check=True, capture_output=True
        )

    @patch('StreamDock.actions.parse_desktop_file')
    @patch('StreamDock.actions.WindowUtils.is_process_running')
    @patch('StreamDock.actions._launch_detached')
    def test_launch_app_not_running(self, mock_launch, mock_is_running, mock_parse):
        """Test launching app when not running."""
        # Mock pgrep to return failure (process not found)
        mock_is_running.return_value = False
        
        launch_or_focus_application({"command": ["firefox"]})
        
        mock_launch.assert_called_with(["firefox"])

    @patch('StreamDock.actions.WindowUtils.activate_window')
    @patch('StreamDock.actions.WindowUtils.is_process_running')
    def test_launch_app_focus_xdotool(self, mock_is_running, mock_activate):
        """Test focusing existing app using xdotool (fallback)."""
        # Mock process running
        mock_is_running.return_value = True
        
        # Mock activation success
        mock_activate.return_value = True
        
        launch_or_focus_application("firefox")
        
        # Verify checking and activation called
        mock_is_running.assert_called_with('firefox')
        mock_activate.assert_called_with('firefox', None)

    @patch('StreamDock.actions._launch_detached')
    @patch('StreamDock.actions.WindowUtils.is_process_running')
    def test_launch_app_string_format(self, mock_is_running, mock_launch):
        """Test simple string command format."""
        mock_is_running.return_value = False
        launch_or_focus_application("firefox")
        # Should eventually call launch
        # This tests config parsing of string format
        
    @patch('StreamDock.actions._launch_detached')
    @patch('StreamDock.actions.WindowUtils.is_process_running')
    def test_launch_app_list_format(self, mock_is_running, mock_launch):
        """Test list command format."""
        mock_is_running.return_value = False
        launch_or_focus_application(["firefox", "--private-window"])
        # Should eventually call launch
        # This tests config parsing of list format
        
    @patch('StreamDock.actions.parse_desktop_file')
    @patch('StreamDock.actions._launch_detached')
    @patch('StreamDock.actions.WindowUtils.is_process_running')
    def test_launch_app_dict_with_desktop_file(self, mock_is_running, mock_launch, mock_parse):
        """Test desktop file loading in dict config."""
        mock_is_running.return_value = False
        mock_parse.return_value = {
            'command': ['kate'],
            'class_name': 'kate',
            'name': 'Kate'
        }
        
        launch_or_focus_application({"desktop_file": "org.kde.kate.desktop"})
        
        mock_parse.assert_called_with("org.kde.kate.desktop")
        
    @patch('StreamDock.actions._launch_detached')
    @patch('StreamDock.actions.WindowUtils.is_process_running')
    def test_launch_app_force_new(self, mock_is_running, mock_launch):
        """Test force_new flag skips window detection."""
        # Even if we mock process running, force_new should skip it
        launch_or_focus_application({
            "command": ["firefox"],
            "force_new": True
        })
        
        # Should launch directly without window detection
        mock_launch.assert_called_once_with(["firefox"])
        mock_is_running.assert_not_called()
        
    @patch('StreamDock.actions.WindowUtils.activate_window')
    @patch('StreamDock.actions.WindowUtils.is_process_running')
    def test_launch_app_focus_kdotool(self, mock_is_running, mock_activate):
        """Test focusing existing app using kdotool (KDE Wayland)."""
        mock_is_running.return_value = True
        mock_activate.return_value = True
        
        launch_or_focus_application("firefox")
        
        # Verify kdotool activation called via activate_window
        mock_activate.assert_called_with('firefox', None)
        
    @patch('StreamDock.actions.WindowUtils.activate_window')
    @patch('StreamDock.actions.WindowUtils.is_process_running')
    @patch('StreamDock.actions.parse_desktop_file')
    def test_launch_app_chrome_by_name(self, mock_parse, mock_is_running, mock_activate):
        """Test Chrome app searched by name fallback."""
        # Mock desktop file for Chrome app
        mock_parse.return_value = {
            'command': ['chromium', '--app=...'],
            'class_name': 'chromium',
            'name': 'My Chrome App'
        }
        
        mock_is_running.return_value = True
        mock_activate.return_value = True
        
        launch_or_focus_application({"desktop_file": "chrome_app.desktop"})
        
        # Verify search by name was attempted via activate_window
        mock_activate.assert_called_with('chromium', 'My Chrome App')
        
    def test_launch_app_invalid_config(self):
        """Test error handling for invalid config."""
        # Should log error and return without crashing
        launch_or_focus_application(12345)  # Invalid type
        launch_or_focus_application({})  # Missing command
        
    @patch('StreamDock.actions._launch_detached')
    @patch('StreamDock.actions.WindowUtils.activate_window')
    @patch('StreamDock.actions.WindowUtils.is_process_running')
    def test_launch_app_process_running_no_window(self, mock_is_running, mock_activate, mock_launch):
        """Test fallback launch when process exists but window not found."""
        mock_is_running.return_value = True
        mock_activate.return_value = False # Window not found/activated
        
        launch_or_focus_application("firefox")
        
        # Should launch new instance since window not found
        mock_launch.assert_called()


    @patch('StreamDock.actions.os.path.exists')
    @patch('StreamDock.actions.configparser.ConfigParser')
    def test_parse_desktop_file(self, mock_parser_cls, mock_exists):
        """Test parsing of .desktop files."""
        # Mock successful parsing
        mock_exists.return_value = True
        mock_config = MagicMock()
        mock_parser_cls.return_value = mock_config
        
        # Setup mock config content
        mock_config.__contains__.side_effect = lambda k: k == 'Desktop Entry'
        mock_config.__getitem__.return_value = {
            'Exec': 'firefox %u',
            'StartupWMClass': 'Firefox',
            'Name': 'Firefox Web Browser'
        }
        
        from StreamDock.actions import parse_desktop_file
        
        result = parse_desktop_file('firefox.desktop')
        
        self.assertEqual(result['command'], ['firefox'])
        self.assertEqual(result['class_name'], 'firefox')
        self.assertEqual(result['name'], 'Firefox Web Browser')

    @patch('tempfile.mkstemp')  # Global patch
    @patch('os.close')          # Global patch
    @patch('os.remove')         # Global patch
    @patch('threading.Thread')  # Global patch
    def test_change_key_text(self, mock_thread, mock_remove, mock_close, mock_mkstemp):
        """Test changing key text."""
        mock_mkstemp.return_value = (123, "/tmp/test.png")
        
        # Mock the helper module to avoid importing heavy dependencies (cairosvg/ctypes)
        mock_pil_helper = MagicMock()
        mock_create_img = MagicMock()
        mock_pil_helper.create_text_image = mock_create_img
        
        with patch.dict(sys.modules, {'StreamDock.image_helpers.pil_helper': mock_pil_helper}):
            # We need to reload or re-import? No, the import is inside the function
            # so it should pick up the mocked module from sys.modules
            
            mock_device = MagicMock()
            action = (ActionType.CHANGE_KEY_TEXT, "Hello")
            
            execute_action(action, device=mock_device, key_number=5)
            
            mock_create_img.assert_called_with(
                text="Hello",
                size=(112, 112),
                text_color='white',
                background_color='black',
                font_size=20,
                bold=True
            )
            mock_device.set_key_image.assert_called_with(5, "/tmp/test.png")

    @patch('StreamDock.actions.execute_command')
    def test_execute_action_dispatch(self, mock_exec):
        """Test dispatching actions."""
        # Execute command
        execute_action((ActionType.EXECUTE_COMMAND, "cmd"))
        mock_exec.assert_called_with("cmd")
        
        # Key press
        with patch('StreamDock.actions.emulate_key_combo') as mock_key:
            execute_action((ActionType.KEY_PRESS, "CTRL+C"))
            mock_key.assert_called_with("CTRL+C")
            
        # Change Layout
        mock_device = MagicMock()
        mock_layout = MagicMock()
        mock_layout.clear_all = True
        
        execute_action(
            (ActionType.CHANGE_LAYOUT, {"layout": mock_layout}),
            device=mock_device
        )
        mock_layout.apply.assert_called_once()
        
        # Device Brightness Up
        with patch('StreamDock.actions.adjust_device_brightness') as mock_adj:
            execute_action((ActionType.DEVICE_BRIGHTNESS_UP, None), device=mock_device)
            mock_adj.assert_called_with(mock_device, 10)

        # Device Brightness Down
        with patch('StreamDock.actions.adjust_device_brightness') as mock_adj:
            execute_action((ActionType.DEVICE_BRIGHTNESS_DOWN, None), device=mock_device)
            mock_adj.assert_called_with(mock_device, -10)
            
        # DBus
        with patch('StreamDock.actions.send_dbus_command') as mock_dbus:
            execute_action((ActionType.DBUS, "cmd"))
            mock_dbus.assert_called_with("cmd")
            
        # Launch Application
        with patch('StreamDock.actions.launch_or_focus_application') as mock_launch:
            execute_action((ActionType.LAUNCH_APPLICATION, "app"))
            mock_launch.assert_called_with("app")
            
        # Wait (simple sleep)
        with patch('StreamDock.actions.time.sleep') as mock_sleep:
            execute_action((ActionType.WAIT, 0.1))
            mock_sleep.assert_called_with(0.1)


if __name__ == '__main__':
    unittest.main()

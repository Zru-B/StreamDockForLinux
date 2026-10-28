import unittest
from unittest.mock import MagicMock, patch

from StreamDock.business_logic.action_type import ActionType
from StreamDock.business_logic.action_executor import ActionExecutor
from StreamDock.infrastructure.system_interface import SystemInterface
from StreamDock.infrastructure.window_interface import WindowInterface


class TestActionExecutor(unittest.TestCase):

    def setUp(self):
        self.mock_system = MagicMock(spec=SystemInterface)
        self.mock_windows = MagicMock(spec=WindowInterface)
        self.executor = ActionExecutor(self.mock_system, self.mock_windows)
        
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

    @patch('StreamDock.business_logic.action_executor.mpris')
    def test_media_shortcuts_go_to_the_player_in_use(self, mock_mpris):
        """Guards against Play/Pause reaching an idle browser tab listed before Spotify."""
        mock_mpris.current.return_value.player = 'org.mpris.MediaPlayer2.spotify'
        for action, method in (("play_pause", "PlayPause"), ("next_any", "Next"),
                               ("previous", "Previous"), ("stop_any", "Stop")):
            self.executor.execute_action((ActionType.DBUS, {"action": action}))
            mock_mpris.call.assert_called_with('org.mpris.MediaPlayer2.spotify', method)
        mock_mpris.current.assert_called_with(with_metadata=False)

    @patch('StreamDock.business_logic.action_executor.mpris')
    def test_media_shortcut_without_a_player_does_nothing(self, mock_mpris):
        mock_mpris.current.return_value.player = None
        self.executor.execute_action((ActionType.DBUS, {"action": "play_pause"}))
        mock_mpris.call.assert_not_called()

    @patch('StreamDock.business_logic.action_executor.subprocess.run')
    def test_dbus_raw_command_still_runs(self, mock_run):
        self.executor.execute_action((ActionType.DBUS, "dbus-send --session --dest=x /x x.Y"))
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args[0][0], "dbus-send --session --dest=x /x x.Y")

    @patch('StreamDock.business_logic.action_executor._launch_detached')
    def test_launch_app_force_new(self, mock_launch):
        """Test forced app launch."""
        self.executor.execute_action((ActionType.LAUNCH_APPLICATION, {"command": ["firefox"], "force_new": True}))
        mock_launch.assert_called_once_with(["firefox"])
        self.mock_system.is_process_running.assert_not_called()

    @patch('StreamDock.business_logic.action_executor._launch_detached')
    def test_launch_app_not_running(self, mock_launch):
        """Test launching app when not running."""
        self.mock_system.is_process_running.return_value = False
        self.executor.execute_action((ActionType.LAUNCH_APPLICATION, {"command": ["firefox"]}))
        mock_launch.assert_called_once_with(["firefox"])

    @patch('StreamDock.business_logic.action_executor._launch_detached')
    def test_launch_app_focuses(self, mock_launch):
        """Test focusing existing app."""
        self.mock_system.is_process_running.return_value = True
        self.mock_windows.search_window_by_class.return_value = "12345"
        self.mock_windows.activate_window.return_value = True
        
        self.executor.execute_action((ActionType.LAUNCH_APPLICATION, {"command": ["firefox"]}))
        
        self.mock_windows.search_window_by_class.assert_called_once_with("firefox")
        self.mock_windows.activate_window.assert_called_once_with("12345")
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

    def test_key_press_plus_key(self):
        # Guards 'CTRL++' being split into empty tokens and rejected.
        self.executor.execute_action((ActionType.KEY_PRESS, "CTRL++"))
        self.mock_system.send_key_combo.assert_called_once_with("ctrl+plus")

        self.mock_system.reset_mock()
        self.executor.execute_action((ActionType.KEY_PRESS, "+"))
        self.mock_system.send_key_combo.assert_called_once_with("plus")

    def test_key_press_unknown_keysym_passes_through_in_its_case(self):
        # xdotool validates keysyms, and they are case-sensitive.
        self.executor.execute_action((ActionType.KEY_PRESS, "XF86AudioPlay"))
        self.mock_system.send_key_combo.assert_called_once_with("XF86AudioPlay")

        self.mock_system.reset_mock()
        self.executor.execute_action((ActionType.KEY_PRESS, "shift+KP_Add"))
        self.mock_system.send_key_combo.assert_called_once_with("shift+KP_Add")

    def test_key_press_empty_token_is_rejected(self):
        self.executor.execute_action((ActionType.KEY_PRESS, "CTRL+"))
        self.mock_system.send_key_combo.assert_not_called()

    @patch('StreamDock.business_logic.action_executor._launch_detached')
    def test_launch_app_string_is_split_into_argv(self, mock_launch):
        # Guards "code --new-window" being run as one binary name.
        self.mock_system.is_process_running.return_value = False
        self.executor.execute_action((ActionType.LAUNCH_APPLICATION, "/usr/bin/code --new-window"))
        mock_launch.assert_called_once_with(["/usr/bin/code", "--new-window"])
        self.mock_system.is_process_running.assert_called_once_with("code")

    @patch('StreamDock.business_logic.action_executor._launch_detached')
    def test_launch_app_dict_command_string_is_split(self, mock_launch):
        self.mock_system.is_process_running.return_value = True
        self.mock_windows.search_window_by_class.return_value = "1"
        self.mock_windows.activate_window.return_value = True
        self.executor.execute_action((ActionType.LAUNCH_APPLICATION,
                                      {"command": "/opt/app/firefox --new-window"}))
        self.mock_system.is_process_running.assert_called_once_with("firefox")
        self.mock_windows.search_window_by_class.assert_called_once_with("firefox")
        mock_launch.assert_not_called()

    @patch('StreamDock.business_logic.action_executor.subprocess.run')
    def test_dbus_raw_command_discards_output_and_times_out(self, mock_run):
        # Guards a hung or chatty command blocking the key's action thread.
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("x", 5)
        self.executor.execute_action((ActionType.DBUS, "dbus-send x"))
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs['timeout'], 5)
        self.assertIs(kwargs['stdout'], subprocess.DEVNULL)
        self.assertIs(kwargs['stderr'], subprocess.DEVNULL)
        self.assertNotIn('capture_output', kwargs)

    @patch('StreamDock.business_logic.action_executor.time.sleep')
    def test_a_failed_wait_stops_the_macro(self, mock_sleep):
        # Steps after a WAIT depend on the pause; without it they go astray.
        mock_sleep.side_effect = TypeError("bad duration")
        self.executor.execute_actions([(ActionType.TYPE_TEXT, "a"), (ActionType.WAIT, "x"),
                                       (ActionType.TYPE_TEXT, "b")])
        self.mock_system.type_text.assert_called_once_with("a")

    def test_other_failed_actions_do_not_stop_the_macro(self):
        self.mock_system.execute_command.side_effect = RuntimeError("boom")
        self.executor.execute_actions([(ActionType.EXECUTE_COMMAND, "x"),
                                       (ActionType.TYPE_TEXT, "b")])
        self.mock_system.type_text.assert_called_once_with("b")


    # -- device writes go through the orchestrator's device lock --

    def _record_exclusive(self):
        calls = []

        def run_exclusive(operation):
            calls.append(operation)
            return operation()
        self.executor.set_run_exclusive(run_exclusive)
        return calls

    def test_device_writes_run_exclusively(self):
        # Interleaved HID packets from a key worker and a layout render blank keys.
        calls = self._record_exclusive()
        device = MagicMock()
        device._current_brightness = 50
        layout = MagicMock()
        layout.clear_all = False
        for action in ((ActionType.CHANGE_KEY_IMAGE, "x.png"),
                       (ActionType.CHANGE_KEY_TEXT, "Hi"),
                       (ActionType.CHANGE_KEY, "x.png"),
                       (ActionType.DEVICE_BRIGHTNESS_UP, None),
                       (ActionType.DEVICE_BRIGHTNESS_DOWN, None),
                       (ActionType.CHANGE_LAYOUT, {"layout": layout})):
            calls.clear()
            self.assertTrue(self.executor.execute_action(action, device=device, key_number=1))
            self.assertEqual(len(calls), 1, action[0])

    def test_writes_still_run_without_a_lock(self):
        device = MagicMock()
        self.executor.execute_action((ActionType.CHANGE_KEY_IMAGE, "x.png"), device=device, key_number=1)
        device.set_key_image.assert_called_once_with(1, "x.png")

    def test_change_key_text_sends_the_image_itself(self):
        # A temp JPEG per press, removed by a thread a second later, was the old way.
        device = MagicMock()
        self.executor.execute_action((ActionType.CHANGE_KEY_TEXT, {"text": "Hi"}),
                                     device=device, key_number=4)
        device.set_key_image.assert_not_called()
        key, image = device.set_key_pil_image.call_args[0]
        self.assertEqual(key, 4)
        self.assertEqual(image.size, (112, 112))

    # -- brightness steps from what the device last reported --

    def test_brightness_steps_from_the_device(self):
        # A slider change must not be undone by the next key press.
        device = MagicMock()
        device._current_brightness = 73
        self.executor.set_default_brightness(20)
        self.executor.execute_action((ActionType.DEVICE_BRIGHTNESS_UP, None), device=device)
        device.set_brightness.assert_called_with(83)
        self.assertEqual(device._current_brightness, 83)

    def test_brightness_falls_back_to_the_configured_value(self):
        device = MagicMock(spec=['set_brightness'])
        self.executor.set_default_brightness(40)
        self.executor.execute_action((ActionType.DEVICE_BRIGHTNESS_UP, None), device=device)
        device.set_brightness.assert_called_with(50)

    def test_brightness_down_stops_at_the_minimum(self):
        # The device ignores anything dimmer, so the key would appear to do nothing.
        from StreamDock.application.configuration_manager import MIN_BRIGHTNESS
        device = MagicMock()
        device._current_brightness = MIN_BRIGHTNESS + 3
        self.executor.execute_action((ActionType.DEVICE_BRIGHTNESS_DOWN, None), device=device)
        device.set_brightness.assert_called_with(MIN_BRIGHTNESS)

    def test_brightness_up_stops_at_100(self):
        device = MagicMock()
        device._current_brightness = 95
        self.executor.execute_action((ActionType.DEVICE_BRIGHTNESS_UP, None), device=device)
        device.set_brightness.assert_called_with(100)

    # -- LAUNCH_APPLICATION window matching --

    def _running_with_window(self, focused_class, focused_title="Window"):
        from StreamDock.domain.Models import WindowInfo
        self.mock_system.is_process_running.return_value = True
        self.mock_windows.search_window_by_class.return_value = "42"
        self.mock_windows.activate_window.return_value = True
        self.mock_windows.activate_tray_app.return_value = False
        self.mock_windows.get_active_window.return_value = WindowInfo(
            title=focused_title, class_=focused_class, raw="")

    @patch('StreamDock.business_logic.action_executor._launch_detached')
    def test_exact_match_accepts_an_equal_class(self, mock_launch):
        self._running_with_window("Code")
        self.executor.execute_action((ActionType.LAUNCH_APPLICATION,
                                      {"command": ["code"], "match_type": "exact"}))
        mock_launch.assert_not_called()

    @patch('StreamDock.business_logic.action_executor._launch_detached')
    def test_exact_match_rejects_a_class_that_only_contains_it(self, mock_launch):
        # "code" must not settle for a "code-oss-helper" window.
        self._running_with_window("code-oss-helper")
        self.executor.execute_action((ActionType.LAUNCH_APPLICATION,
                                      {"command": ["code"], "match_type": "exact"}))
        mock_launch.assert_called_once_with(["code"])

    @patch('StreamDock.business_logic.action_executor._launch_detached')
    def test_contains_match_accepts_a_longer_class(self, mock_launch):
        self._running_with_window("code-oss-helper")
        self.executor.execute_action((ActionType.LAUNCH_APPLICATION, {"command": ["code"]}))
        mock_launch.assert_not_called()
        self.mock_windows.get_active_window.assert_not_called()

    def _chrome_app(self, focused_title):
        self._running_with_window("google-chrome", focused_title)
        self.mock_windows.search_window_by_class.return_value = None
        self.mock_windows.search_window_by_name.return_value = "7"
        desktop = {'command': ['google-chrome', '--app-id=abc'], 'class_name': 'crx_abc',
                   'name': 'YouTube Music'}
        return patch('StreamDock.business_logic.action_executor.parse_desktop_file',
                     return_value=desktop)

    @patch('StreamDock.business_logic.action_executor._launch_detached')
    def test_title_fallback_accepts_the_apps_own_window(self, mock_launch):
        with self._chrome_app("Liked songs - YouTube Music"):
            self.executor.execute_action((ActionType.LAUNCH_APPLICATION,
                                          {"desktop_file": "chrome-abc.desktop"}))
        mock_launch.assert_not_called()

    @patch('StreamDock.business_logic.action_executor._launch_detached')
    def test_title_fallback_rejects_a_tab_mentioning_the_app(self, mock_launch):
        # A browser tab about the app is not the app.
        with self._chrome_app("YouTube Music review - Google Chrome"):
            self.executor.execute_action((ActionType.LAUNCH_APPLICATION,
                                          {"desktop_file": "chrome-abc.desktop"}))
        mock_launch.assert_called_once()

    # -- logging --

    def test_a_malformed_action_is_logged_without_its_value(self):
        # Actions carry typed text and commands, which must not reach the log.
        from StreamDock.business_logic.action_executor import parse_action_list
        with self.assertLogs('StreamDock.business_logic.action_executor', 'WARNING') as logs:
            parse_action_list(["TYPE_TEXT hunter2"])
        self.assertNotIn("hunter2", "\n".join(logs.output))
        self.assertIn("#0", "\n".join(logs.output))

if __name__ == '__main__':
    unittest.main()

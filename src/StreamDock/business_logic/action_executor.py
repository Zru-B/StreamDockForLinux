import configparser
import logging
import os
import re
import shlex
import subprocess
import tempfile
import threading
import time
from typing import Callable, List, Tuple

from StreamDock.business_logic.action_type import ActionType
from StreamDock.domain.key import Key
from StreamDock.image_helpers.pil_helper import render_key_image
from StreamDock.infrastructure.system_interface import SystemInterface
from StreamDock.window_utils import WindowUtils

logger = logging.getLogger(__name__)

def _launch_detached(command):
    """Launch a command completely detached from the current process."""
    if isinstance(command, str):
        cmd_str = command
    else:
        cmd_str = ' '.join(shlex.quote(arg) for arg in command)

    shell_cmd = f"nohup {cmd_str} >/dev/null 2>&1 &"
    # pylint: disable=consider-using-with
    subprocess.Popen(
        shell_cmd,
        shell=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True
    )

def parse_desktop_file(desktop_file):
    """Parse a .desktop file and extract application launch information."""
    search_paths = [
        '/usr/share/applications/',
        '/usr/local/share/applications/',
        os.path.expanduser('~/.local/share/applications/'),
        '/var/lib/flatpak/exports/share/applications/',
        os.path.expanduser('~/.local/share/flatpak/exports/share/applications/'),
    ]

    desktop_path = None
    if os.path.isabs(desktop_file) and os.path.exists(desktop_file):
        desktop_path = desktop_file
    else:
        filename = desktop_file if desktop_file.endswith('.desktop') else f"{desktop_file}.desktop"
        for search_path in search_paths:
            potential_path = os.path.join(search_path, filename)
            if os.path.exists(potential_path):
                desktop_path = potential_path
                break

    if not desktop_path:
        logger.warning("Desktop file not found: %s", desktop_file)
        return None

    try:
        config = configparser.ConfigParser(interpolation=None)
        with open(desktop_path, 'r', encoding='utf-8') as f:
            config.read_file(f)

        if 'Desktop Entry' not in config:
            logger.error("Invalid desktop file (no [Desktop Entry] section): %s", desktop_path)
            return None

        entry = config['Desktop Entry']
        exec_line = entry.get('Exec', '')
        if not exec_line:
            logger.error("No Exec field in desktop file: %s", desktop_path)
            return None

        exec_line = re.sub(r'%[fFuUdDnNickvm]', '', exec_line).strip()
        command = shlex.split(exec_line)

        class_name = entry.get('StartupWMClass', '')
        if not class_name and command:
            class_name = os.path.basename(command[0])

        app_name = entry.get('Name', '')

        return {
            'command': command,
            'class_name': class_name.lower(),
            'name': app_name
        }

    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Error parsing desktop file %s", desktop_path)
        return None

def _parse_app_config(app_config):
    """Parse and normalize app_config from various formats."""
    force_new = False
    command = None
    class_name = None
    match_type = "contains"

    if isinstance(app_config, str):
        command = [app_config]
        class_name = app_config.lower()
    elif isinstance(app_config, list):
        command = app_config
        class_name = app_config[0].lower()
    elif isinstance(app_config, dict):
        desktop_file = app_config.get("desktop_file")
        if desktop_file:
            desktop_info = parse_desktop_file(desktop_file)
            if desktop_info:
                command = desktop_info['command']
                class_name = desktop_info['class_name']
                if "class_name" in app_config:
                    class_name = app_config["class_name"].lower()
            else:
                logger.error("Failed to parse desktop file: %s", desktop_file)
                return None
        else:
            command = app_config.get("command")
            if isinstance(command, str):
                command = [command]
            if command:
                class_name = app_config.get("class_name", command[0]).lower()

        match_type = app_config.get("match_type", "contains")
        force_new = app_config.get("force_new", False)
    else:
        logger.error("Invalid LAUNCH_APPLICATION parameter: %s", app_config)
        return None

    if not command:
        logger.error("Error: LAUNCH_APPLICATION requires either 'command' or 'desktop_file'")
        return None

    process_name = None
    if isinstance(app_config, dict):
        process_name = app_config.get("process_name")

    if not process_name:
        process_name = command[0] if isinstance(command, list) else command
        process_name = os.path.basename(process_name)

    return {
        'command': command,
        'class_name': class_name,
        'match_type': match_type,
        'force_new': force_new,
        'process_name': process_name
    }

class ActionExecutor:
    """Executes actions in response to button presses."""

    def __init__(self, system_interface: SystemInterface):
        self._system = system_interface
        self._action_handlers = {}
        self._register_built_in_handlers()

    def _register_built_in_handlers(self):
        self.register_action_type(ActionType.EXECUTE_COMMAND, self._handle_execute_command)
        self.register_action_type(ActionType.KEY_PRESS, self._handle_key_press)
        self.register_action_type(ActionType.TYPE_TEXT, self._handle_type_text)
        self.register_action_type(ActionType.WAIT, self._handle_wait)
        self.register_action_type(ActionType.CHANGE_KEY_IMAGE, self._handle_change_key_image)
        self.register_action_type(ActionType.CHANGE_KEY_TEXT, self._handle_change_key_text)
        self.register_action_type(ActionType.CHANGE_KEY, self._handle_change_key)
        self.register_action_type(ActionType.CHANGE_LAYOUT, self._handle_change_layout)
        self.register_action_type(ActionType.DBUS, self._handle_dbus)
        self.register_action_type(ActionType.DEVICE_BRIGHTNESS_UP, self._handle_brightness_up)
        self.register_action_type(ActionType.DEVICE_BRIGHTNESS_DOWN, self._handle_brightness_down)
        self.register_action_type(ActionType.LAUNCH_APPLICATION, self._handle_launch_application)

    def register_action_type(self, action_type: ActionType, handler: Callable) -> None:
        self._action_handlers[action_type] = handler

    def execute_action(self, action: Tuple, device=None, key_number=None) -> None:
        if not isinstance(action, tuple) or len(action) != 2:
            logger.error("Invalid action format: %s. Expected (ActionType, parameter)", action)
            return

        action_type, parameter = action
        handler = self._action_handlers.get(action_type)
        if handler:
            try:
                handler(parameter, device, key_number)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Error executing action %s: %s", action_type, e)
        else:
            logger.error("Unknown action type: %s", action_type)

    def execute_actions(self, actions: List[Tuple], device=None, key_number=None) -> None:
        if not isinstance(actions, list):
            actions = [actions]
        for action in actions:
            self.execute_action(action, device=device, key_number=key_number)

    def _handle_execute_command(self, parameter, unused_device, unused_key_number):
        self._system.execute_command(parameter)

    def _handle_key_press(self, parameter, unused_device, unused_key_number):
        # Translate to xdotool compatible key sequences, handled by SystemInterface
        # Emulate legacy behavior using send_key_combo
        key_mapping = {
            'CTRL': 'ctrl', 'CONTROL': 'ctrl',
            'ALT': 'alt', 'SHIFT': 'shift',
            'META': 'super', 'SUPER': 'super', 'WIN': 'super', 'COMMAND': 'super', 'CMD': 'super',
            'ENTER': 'Return', 'RETURN': 'Return', 'TAB': 'Tab', 'SPACE': 'space',
            'BACKSPACE': 'BackSpace', 'DELETE': 'Delete', 'DEL': 'Delete',
            'ESC': 'Escape', 'ESCAPE': 'Escape',
            'HOME': 'Home', 'END': 'End', 'PAGEUP': 'Page_Up', 'PAGEDOWN': 'Page_Down',
            'UP': 'Up', 'DOWN': 'Down', 'LEFT': 'Left', 'RIGHT': 'Right',
            'F1': 'F1', 'F2': 'F2', 'F3': 'F3', 'F4': 'F4',
            'F5': 'F5', 'F6': 'F6', 'F7': 'F7', 'F8': 'F8',
            'F9': 'F9', 'F10': 'F10', 'F11': 'F11', 'F12': 'F12',
            ',': 'comma', '.': 'period', '/': 'slash',
            ';': 'semicolon', "'": 'apostrophe',
            '[': 'bracketleft', ']': 'bracketright', '\\': 'backslash',
            '=': 'equal', '-': 'minus', '`': 'grave',
        }
        keys = [k.strip().upper() for k in parameter.split('+')]
        if not keys:
            logger.error("Invalid key combination: %s", parameter)
            return

        xdotool_keys = []
        for key in keys:
            if key in key_mapping:
                xdotool_keys.append(key_mapping[key])
            elif len(key) == 1:
                xdotool_keys.append(key.lower())
            else:
                logger.error("Unknown key: %s", key)
                return

        combo_str = '+'.join(xdotool_keys)
        self._system.send_key_combo(combo_str)

    def _handle_type_text(self, parameter, unused_device, unused_key_number):
        if parameter:
            self._system.type_text(parameter)

    def _handle_wait(self, parameter, unused_device, unused_key_number):
        time.sleep(parameter)

    def _handle_change_key_image(self, parameter, device, key_number):
        if device is None or key_number is None:
            logger.error("Error: CHANGE_KEY_IMAGE requires device and key_number")
            return
        device.set_key_image(key_number, parameter)

    def _handle_change_key_text(self, parameter, device, key_number):
        if device is None or key_number is None:
            logger.error("Error: CHANGE_KEY_TEXT requires device and key_number")
            return

        if isinstance(parameter, dict):
            text = parameter.get('text', '')
            text_color = parameter.get('text_color', 'white')
            background_color = parameter.get('background_color', 'black')
            font_size = int(parameter.get('font_size', 20))
            bold = bool(parameter.get('bold', True))
            text_position = parameter.get('text_position', 'bottom')
            icon_path = parameter.get('icon', '')
        elif isinstance(parameter, str):
            text = parameter
            text_color = 'white'
            background_color = 'black'
            font_size = 20
            bold = True
            text_position = 'bottom'
            icon_path = ''
        else:
            logger.error("Error: CHANGE_KEY_TEXT parameter must be dict or string")
            return

        try:
            rendered = render_key_image(
                size=(112, 112),
                icon_path=icon_path,
                text=text,
                text_color=text_color,
                background_color=background_color,
                font_size=font_size,
                bold=bold,
                text_position=text_position,
            )
            temp_fd, temp_path = tempfile.mkstemp(suffix='.jpg', prefix='sdkey_txt_')
            os.close(temp_fd)
            rendered.save(temp_path, format='JPEG', quality=95)
            device.set_key_image(key_number, temp_path)

            def cleanup():
                time.sleep(1.0)
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            threading.Thread(target=cleanup, daemon=True).start()
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Error creating text image for CHANGE_KEY_TEXT")

    def _handle_change_key(self, parameter, device, key_number):
        if device is None:
            logger.error("Error: CHANGE_KEY requires device")
            return

        target_key = None

        if isinstance(parameter, Key):
            target_key = parameter
        elif isinstance(parameter, str):
            if key_number is None:
                logger.error("Error: CHANGE_KEY with string requires key_number")
                return
            target_key = Key(device, key_number, image_path=parameter)
        elif isinstance(parameter, dict):
            if key_number is None:
                logger.error("Error: CHANGE_KEY with dict requires key_number")
                return
            image_path = parameter.get('image', '')
            on_press = parameter.get('actions') or parameter.get('on_press')
            on_release = parameter.get('on_release')
            on_double_press = parameter.get('on_double_press')
            target_key = Key(
                device, key_number,
                image_path=image_path,
                on_press=on_press,
                on_release=on_release,
                on_double_press=on_double_press
            )
        else:
            logger.error("Error: CHANGE_KEY parameter has invalid type: %s", type(parameter))
            return

        if target_key:
            # pylint: disable=protected-access
            target_key._configure()

    def _handle_change_layout(self, parameter, device, unused_key_number):
        if device is None:
            logger.error("Error: CHANGE_LAYOUT requires device")
            return

        layout = parameter["layout"]
        action_clear_all = parameter.get("clear_all", False)
        if action_clear_all and not layout.clear_all:
            device.clear_all_icons()
        layout.apply()

    def _handle_dbus(self, parameter, unused_device, unused_key_number):
        shortcuts = {
            "play_pause": (
                "dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify "
                "/org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.PlayPause"
            ),
            "play_pause_any": (
                "dbus-send --type=method_call --dest=org.freedesktop.DBus /org/freedesktop/DBus "
                "org.freedesktop.DBus.ListNames | grep -o 'org.mpris.MediaPlayer2.[^\"]*' | head -1 | "
                "xargs -I {} dbus-send --print-reply --dest={} /org/mpris/MediaPlayer2 "
                "org.mpris.MediaPlayer2.Player.PlayPause"
            ),
            "next": (
                "dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify "
                "/org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Next"
            ),
            "previous": (
                "dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify "
                "/org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Previous"
            ),
            "stop": (
                "dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify "
                "/org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Stop"
            ),
        }

        # Determine command string
        if isinstance(parameter, dict):
            action = parameter.get("action")
            if action in shortcuts:
                command = shortcuts[action]
            elif action == "volume_up":
                self._system.set_volume(getattr(self, '_current_vol', 50) + 5) # approximation
                return
            elif action == "volume_down":
                self._system.set_volume(getattr(self, '_current_vol', 50) - 5) # approximation
                return
            elif action == "mute":
                # SystemInterface set_volume doesn't natively expose mute. We fall through to dbus/pactl execution
                command = "pactl set-sink-mute @DEFAULT_SINK@ toggle"
            else:
                logger.error("Unknown D-Bus shortcut: %s", action)
                return
        elif isinstance(parameter, str):
            command = parameter
        else:
            logger.error("Invalid D-Bus command format: %s", type(parameter))
            return

        try:
            subprocess.run(command, shell=True, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            logger.error("Error executing D-Bus command: %s", e)

    def _handle_brightness_up(self, unused_parameter, device, unused_key_number):
        if device:
            self._adjust_brightness(device, 10)

    def _handle_brightness_down(self, unused_parameter, device, unused_key_number):
        if device:
            self._adjust_brightness(device, -10)

    def _adjust_brightness(self, device, amount):
        try:
            current = getattr(device, '_current_brightness', 50)
            new_val = max(0, min(100, current + amount))
            device.set_brightness(new_val)
            # pylint: disable=protected-access
            device._current_brightness = new_val
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Error adjusting brightness")

    def _handle_launch_application(self, parameter, unused_device, unused_key_number):
        config = _parse_app_config(parameter)
        if not config:
            return

        command = config['command']
        class_name = config['class_name']
        force_new = config['force_new']
        process_name = config['process_name']

        if force_new:
            _launch_detached(command)
            return

        try:
            if not WindowUtils.is_process_running(process_name):
                _launch_detached(command)
                return

            search_by_name = None
            if 'chromium' in command[0].lower() or 'chrome' in command[0].lower():
                if isinstance(parameter, dict) and parameter.get('desktop_file'):
                    desktop_info = parse_desktop_file(parameter.get('desktop_file'))
                    if desktop_info:
                        search_by_name = desktop_info['name']

            # Use WindowUtils locally or SystemInterface
            window_id = self._system.search_window_by_class(class_name)
            if not window_id and search_by_name:
                # Need to use WindowUtils to search by name as a fallback?
                pass

            activated = False
            if window_id:
                activated = self._system.activate_window(window_id)
            else:
                # Fallback to WindowUtils directly
                activated = WindowUtils.activate_window(class_name, search_by_name)

            if not activated:
                logger.warning("Window not found for class '%s', launching a new instance", class_name)
                _launch_detached(command)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Error in LAUNCH_APPLICATION")

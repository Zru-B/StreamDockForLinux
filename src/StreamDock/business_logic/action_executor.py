import configparser
import logging
import os
import re
import shlex
import subprocess
import time
from typing import Callable, List, Optional, Tuple

from StreamDock.business_logic.action_type import ActionType
from StreamDock.domain.key import Key
from StreamDock.image_helpers.pil_helper import render_key_image
from StreamDock.infrastructure import mpris
from StreamDock.infrastructure.system_interface import SystemInterface
from StreamDock.infrastructure.window_interface import WindowInterface

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

def parse_action_list(action_configs) -> List[Tuple]:
    """
    Parse a list of {ACTION_TYPE: parameter} dicts into (ActionType, parameter) tuples.

    Lives here rather than in the layout factory because CHANGE_KEY builds
    keys at runtime and must parse their actions exactly as the factory does.
    Action names are matched case-insensitively, as the validator accepts them.
    """
    actions: List[Tuple] = []
    if not action_configs:
        return actions

    for index, action_config in enumerate(action_configs):
        if not isinstance(action_config, dict):
            # Only the shape: the value may be text the user types or runs.
            logger.warning("Skipping action #%d: expected a mapping, got %s",
                           index, type(action_config).__name__)
            continue
        for action_type_str, param in action_config.items():
            name = action_type_str.upper() if isinstance(action_type_str, str) else action_type_str
            try:
                action_type = ActionType[name]
            except KeyError:
                logger.warning("Unknown action type: %r", action_type_str)
                continue
            # CHANGE_LAYOUT shorthand: a bare layout name. The name stays a
            # string; the executor resolves it when the action runs, since
            # layouts are not built yet while keys are being parsed.
            if action_type is ActionType.CHANGE_LAYOUT and isinstance(param, str):
                param = {'layout': param}
            actions.append((action_type, param))

    return actions


def _parse_app_config(app_config):
    """Parse and normalize app_config from various formats."""
    force_new = False
    command = None
    class_name = None
    match_type = "contains"

    if isinstance(app_config, str):
        # A string is a command line: "code --new-window" must run `code`
        # with an argument, not look for a binary named "code --new-window".
        command = shlex.split(app_config)
        class_name = os.path.basename(command[0]).lower() if command else None
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
                command = shlex.split(command)
            if command:
                class_name = app_config.get("class_name", os.path.basename(command[0])).lower()

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

    def __init__(self, system_interface: SystemInterface, window_manager: WindowInterface):
        self._system = system_interface
        self._windows = window_manager
        self._action_handlers = {}
        self._layouts = {}  # layout_name -> Layout object, populated after factory creates layouts
        self._layout_switcher = None
        self._key_builder = None
        self._run_exclusive: Callable[[Callable[[], object]], object] = lambda operation: operation()
        self._default_brightness = 50
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

    def set_layouts(self, layouts: dict) -> None:
        """Provide the layouts registry so CHANGE_LAYOUT can resolve names to Layout objects."""
        self._layouts = layouts

    def set_layout_switcher(self, switcher: Callable[[str, bool], None]) -> None:
        """
        Route CHANGE_LAYOUT by name through the orchestrator.

        Applying a layout directly skips the device lock and the orchestrator's
        current-layout tracking, so the GUI never learns of the switch.
        """
        self._layout_switcher = switcher

    def set_run_exclusive(self, run_exclusive: Callable[[Callable[[], object]], object]) -> None:
        """
        Route device writes through the orchestrator's device lock.

        Key images are multi-packet HID transfers; written from a key worker
        while a layout or widget frame is being drawn, their packets interleave
        and keys come up blank.
        """
        self._run_exclusive = run_exclusive

    def set_default_brightness(self, brightness: int) -> None:
        """Configured brightness, stepped from when the device has not reported one."""
        self._default_brightness = brightness

    def set_key_builder(self, builder: Callable[[str, int], Optional[Key]]) -> None:
        """
        Resolve CHANGE_KEY key names: builder(key_name, key_number) returns the
        configured key built for that slot, or None for an unknown name.
        """
        self._key_builder = builder

    def execute_action(self, action: Tuple, device=None, key_number=None) -> bool:
        """Run one action; returns False when it could not run or raised."""
        if not isinstance(action, tuple) or len(action) != 2:
            logger.error("Invalid action format: %s. Expected (ActionType, parameter)", action)
            return False

        action_type, parameter = action
        handler = self._action_handlers.get(action_type)
        if handler:
            try:
                handler(parameter, device, key_number)
                return True
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Error executing action %s: %s", action_type, e)
                return False
        logger.error("Unknown action type: %s", action_type)
        return False

    def execute_actions(self, actions: List[Tuple], device=None, key_number=None) -> None:
        if not isinstance(actions, list):
            actions = [actions]
        for i, action in enumerate(actions):
            ok = self.execute_action(action, device=device, key_number=key_number)
            # A WAIT separates steps that depend on each other (open a window,
            # then type into it); running the rest without the pause sends
            # them to the wrong place, so the macro stops instead.
            if not ok and isinstance(action, tuple) and action and action[0] is ActionType.WAIT:
                logger.error("WAIT failed, skipping the remaining %d action(s)",
                             len(actions) - i - 1)
                break

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
        combo = parameter.strip()
        # '+' separates keys, so the plus key itself can only be written as a
        # trailing '+' after a separator ("CTRL++") or on its own ("+").
        with_plus = combo == '+' or combo.endswith('++')
        if with_plus:
            combo = combo[:-2] if combo != '+' else ''
        keys = [k.strip() for k in combo.split('+')] if combo else []
        if any(not k for k in keys) or not (keys or with_plus):
            logger.error("Invalid key combination: %s", parameter)
            return

        xdotool_keys = []
        for key in keys:
            if key.upper() in key_mapping:
                xdotool_keys.append(key_mapping[key.upper()])
            elif len(key) == 1:
                xdotool_keys.append(key.lower())
            else:
                # Any other X keysym (XF86AudioPlay, KP_Add, ...) goes through
                # as written: keysyms are case-sensitive and xdotool knows them all.
                xdotool_keys.append(key)
        if with_plus:
            xdotool_keys.append('plus')

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
        self._run_exclusive(lambda: device.set_key_image(key_number, parameter))

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
            self._run_exclusive(lambda: device.set_key_pil_image(key_number, rendered))
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
            # The editor writes the name of a configured key; older configs
            # hold an image path, which still just swaps the picture.
            if self._key_builder is not None:
                target_key = self._key_builder(parameter, key_number)
            if target_key is None:
                target_key = Key(device, key_number, image_path=parameter)
        elif isinstance(parameter, dict):
            if key_number is None:
                logger.error("Error: CHANGE_KEY with dict requires key_number")
                return
            image_path = parameter.get('image', '')
            on_press = parse_action_list(parameter.get('actions') or parameter.get('on_press'))
            on_release = parse_action_list(parameter.get('on_release'))
            on_double_press = parse_action_list(parameter.get('on_double_press'))
            on_long_press = parse_action_list(parameter.get('on_long_press'))
            target_key = Key(
                device, key_number,
                image_path=image_path,
                on_press=on_press,
                on_release=on_release,
                on_double_press=on_double_press,
                on_long_press=on_long_press,
                action_executor=self,
            )
        else:
            logger.error("Error: CHANGE_KEY parameter has invalid type: %s", type(parameter))
            return

        if target_key:
            target_key.prepare()
            # pylint: disable=protected-access
            self._run_exclusive(target_key._configure)

    def _handle_change_layout(self, parameter, device, unused_key_number):
        if device is None:
            logger.error("Error: CHANGE_LAYOUT requires device")
            return

        layout = parameter["layout"]
        action_clear_all = parameter.get("clear_all", False)

        if isinstance(layout, str) and self._layout_switcher is not None:
            if layout not in self._layouts:
                logger.error("CHANGE_LAYOUT: unknown layout '%s'", layout)
                return
            clear_icons = action_clear_all and not self._layouts[layout].clear_all
            self._layout_switcher(layout, clear_icons)
            return

        # If layout is still a name string (resolved lazily after factory builds layouts),
        # look it up in the registry now.
        if isinstance(layout, str):
            resolved = self._layouts.get(layout)
            if resolved is None:
                logger.error("CHANGE_LAYOUT: unknown layout '%s'", layout)
                return
            layout = resolved

        def apply():
            if action_clear_all and not layout.clear_all:
                device.clear_all_icons()
            layout.apply()
        self._run_exclusive(apply)

    # Shortcut names (with or without the legacy _any suffix) -> MPRIS Player method.
    _MEDIA_SHORTCUTS = {
        'play_pause': 'PlayPause',
        'next': 'Next',
        'previous': 'Previous',
        'stop': 'Stop',
    }

    def _handle_dbus(self, parameter, unused_device, unused_key_number):
        if isinstance(parameter, dict):
            action = parameter.get("action")
            method = self._MEDIA_SHORTCUTS.get(action[:-4] if isinstance(action, str) and action.endswith('_any')
                                               else action)
            if method:
                self._control_media(method)
            elif action == "volume_up":
                self._system.set_volume("+5%")
            elif action == "volume_down":
                self._system.set_volume("-5%")
            elif action == "mute":
                self._system.toggle_mute()
            else:
                logger.error("Unknown D-Bus shortcut: %s", action)
            return

        if not isinstance(parameter, str):
            logger.error("Invalid D-Bus command format: %s", type(parameter))
            return
        # Output is discarded rather than captured: nothing reads it, and a
        # chatty or hung command would otherwise buffer or block the key's
        # action thread indefinitely.
        try:
            subprocess.run(parameter, shell=True, check=True, timeout=5,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            logger.error("Error executing D-Bus command: %s", e)
        except subprocess.TimeoutExpired:
            logger.error("D-Bus command timed out after 5s: %s", parameter)

    @staticmethod
    def _control_media(method: str) -> None:
        """
        Send a Player method to the media player the user means.

        That is the one playing, else one paused, else any: taking the first
        player on the bus sent Play/Pause to an idle browser tab as soon as a
        browser registered as a player next to Spotify.
        """
        player = mpris.current(with_metadata=False).player
        if player is None:
            logger.warning("No media player found for %s", method)
            return
        mpris.call(player, method)

    def _handle_brightness_up(self, unused_parameter, device, unused_key_number):
        if device:
            self._adjust_brightness(device, 10)

    def _handle_brightness_down(self, unused_parameter, device, unused_key_number):
        if device:
            self._adjust_brightness(device, -10)

    def _adjust_brightness(self, device, amount):
        # The device's own record is the one source of truth: the GUI slider,
        # a reload and these keys all set it, so stepping from a copy kept here
        # would jump back to a stale value. Never below MIN_BRIGHTNESS: the
        # device ignores dimmer values.
        # Imported here: the application package imports this module.
        from StreamDock.application.configuration_manager import MIN_BRIGHTNESS  # pylint: disable=import-outside-toplevel
        try:
            current = getattr(device, '_current_brightness', None)
            if isinstance(current, bool) or not isinstance(current, (int, float)):
                current = self._default_brightness
            new_val = int(max(MIN_BRIGHTNESS, min(100, current + amount)))

            def write():
                device.set_brightness(new_val)
                # pylint: disable=protected-access
                device._current_brightness = new_val
            self._run_exclusive(write)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Error adjusting brightness")

    def _focused_window_matches(self, predicate) -> bool:
        window = self._windows.get_active_window()
        return window is not None and bool(predicate(window))

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
            if not self._system.is_process_running(process_name):
                _launch_detached(command)
                return

            search_by_name = None
            if 'chromium' in command[0].lower() or 'chrome' in command[0].lower():
                if isinstance(parameter, dict) and parameter.get('desktop_file'):
                    desktop_info = parse_desktop_file(parameter.get('desktop_file'))
                    if desktop_info:
                        search_by_name = desktop_info['name']

            # The window lookups only match substrings and return an id, so a
            # stricter match is checked on the window once it has focus.
            window_id = self._windows.search_window_by_class(class_name)
            confirm = None
            if window_id and str(config['match_type']).lower() == 'exact':
                confirm = lambda window: (window.class_ or '').lower() == class_name
            if not window_id and search_by_name:
                window_id = self._windows.search_window_by_name(search_by_name)
                # Any tab whose title mentions the app would match; the app's
                # own window is titled "... - <app name>" or just the name.
                app_name = search_by_name.strip().lower()
                confirm = lambda window: (window.title or '').strip().lower().endswith(app_name)

            activated = False
            if window_id:
                activated = self._windows.activate_window(window_id)
                if activated and confirm is not None and not self._focused_window_matches(confirm):
                    logger.info("Found window is not '%s'; not using it", class_name)
                    activated = False

            if not activated:
                activated = self._windows.activate_tray_app(class_name)

            if not activated:
                logger.warning("Window not found for class '%s', launching a new instance", class_name)
                _launch_detached(command)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Error in LAUNCH_APPLICATION")

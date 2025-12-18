import configparser
import logging
import os
import shlex
import subprocess
import time
from enum import Enum
from threading import Thread

from .VirtualKeyboard import VirtualKeyboard
from .WindowUtils import WindowUtils

logger = logging.getLogger(__name__)
# Initialize Virtual Keyboard
try:
    vk = VirtualKeyboard()
except Exception as e:
    logger.error(f"Failed to initialize virtual keyboard: {e}")
    vk = None


class ActionType(Enum):
    """Enumeration of supported StreamDock actions."""

    EXECUTE_COMMAND = "execute_command"
    KEY_PRESS = "key_press"
    TYPE_TEXT = "type_text"
    WAIT = "wait"
    CHANGE_KEY_IMAGE = "change_key_image"
    CHANGE_KEY_TEXT = "change_key_text"
    CHANGE_KEY = "change_key"
    CHANGE_LAYOUT = "change_layout"
    DBUS = "dbus"
    DEVICE_BRIGHTNESS_UP = "device_brightness_up"
    DEVICE_BRIGHTNESS_DOWN = "device_brightness_down"
    LAUNCH_APPLICATION = "launch_application"


def _launch_detached(command):
    """Launch a command completely detached from the current process.

    Uses nohup and shell backgrounding to ensure the process survives
    even if the parent Python process is killed.

    :param command: Command as string or list of arguments
    """
    # Build command string for shell execution with proper detachment
    if isinstance(command, str):
        cmd_str = command
    else:
        # Properly quote arguments for shell
        cmd_str = " ".join(shlex.quote(arg) for arg in command)

    # Use nohup and background execution for complete detachment
    # This ensures the process survives even if the parent is killed
    shell_cmd = f"nohup {cmd_str} >/dev/null 2>&1 &"

    subprocess.Popen(
        shell_cmd,
        shell=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )

def execute_command(command):
    """Execute a system command using subprocess.Popen.

    The command is launched in a completely separate process, detached from Python.
    This means:
    - The command's output won't appear in the Python console
    - The command will continue running even if the Python script exits
    - The command runs independently with its own process session
    """
    try:
        _launch_detached(command)
    except Exception as exc:
        logger.exception("Error executing command: %s", exc)

def emulate_key_combo(combo_string):
    """
    Emulate a keyboard combination using xdotool.

    :param combo_string: String like 'CTRL+C', 'ALT+F4', etc.
    """
    # Mapping of string names to xdotool key names
    key_mapping = {
        "CTRL": "ctrl",
        "CONTROL": "ctrl",
        "ALT": "alt",
        "SHIFT": "shift",
        "META": "super",
        "SUPER": "super",
        "WIN": "super",
        "COMMAND": "super",
        "CMD": "super",
        "ENTER": "Return",
        "RETURN": "Return",
        "TAB": "Tab",
        "SPACE": "space",
        "BACKSPACE": "BackSpace",
        "DELETE": "Delete",
        "DEL": "Delete",
        "ESC": "Escape",
        "ESCAPE": "Escape",
        "HOME": "Home",
        "END": "End",
        "PAGEUP": "Page_Up",
        "PAGEDOWN": "Page_Down",
        "UP": "Up",
        "DOWN": "Down",
        "LEFT": "Left",
        "RIGHT": "Right",
        "F1": "F1",
        "F2": "F2",
        "F3": "F3",
        "F4": "F4",
        "F5": "F5",
        "F6": "F6",
        "F7": "F7",
        "F8": "F8",
        "F9": "F9",
        "F10": "F10",
        "F11": "F11",
        "F12": "F12",
    }

    keys = [k.strip().upper() for k in combo_string.split("+")]
    if not keys:
        logger.warning("Invalid key combination: %s", combo_string)
        return


    # Try VirtualKeyboard first
    if vk and vk.available:
        if vk.send_combo(combo_string):
            return
        else:
            logger.warning("VirtualKeyboard failed to send combo, falling back to xdotool/kdotool")

    xdotool_keys = []
    for key in keys:
        if key in key_mapping:
            xdotool_keys.append(key_mapping[key])
        elif len(key) == 1:
            xdotool_keys.append(key.lower())
        else:
            logger.warning("Unknown key: %s", key)
            return

    # If the virtual keyboard failed, try kdotool (for KDE Wayland)
    try:
        # kdotool key "CTRL+C"
        subprocess.run(['kdotool', 'key', '+'.join(xdotool_keys)], check=True)
        return
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Fallback to xdotool
        pass
    except Exception as e:
        logger.warning(f"kdotool failed: {e}")

    # Fallback to xdotool (X11)
    try:
        subprocess.run(["xdotool", "key", "+".join(xdotool_keys)], check=True)
    except FileNotFoundError:
        logger.error("Error: neither kdotool nor xdotool found. key_press action will not work.")
    except subprocess.CalledProcessError as e:
        logger.error("Error pressing key combination: %s", e)


def type_text(text, delay=0.001):
    """
    Type text using xdotool, ensuring case sensitivity by using key events.

    :param text: Text to type (case-sensitive)
    :param delay: Delay between key presses in seconds (default: 0.001s for fast typing)
    """
    if not text:
        return

    # Try VirtualKeyboard first
    if vk and vk.available:
        if vk.type_string(text, delay=delay):
            return
    try:
        # Next attempt - kdotool (KDE Wayland)
        subprocess.run(['kdotool', 'type', text], check=True)
        return
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    try:
        # Next attempt - xdotool (X11)
        try:
            window_id = (
                subprocess.check_output(["xdotool", "getactivewindow"])
                .decode("utf-8")
                .strip()
            )
            window_args = ["windowactivate", "--sync", window_id]
        except Exception as e:
            # If we can't get window ID, continue without it (might be slightly less reliable)
            window_args = []

        # Prepare all key commands at once
        key_commands = []
        for char in text:
            # Handle special characters
            if char == " ":
                key = "space"
            elif char == "\n":
                key = "Return"
            elif char == "\t":
                key = "Tab"
            elif char in "!@#$%^&*()_+{}|:\"<>?~`-=[]\\;',./":
                key = char
            else:
                key = char

            # Build the command
            key_commands.append(
                ["xdotool"] + window_args + ["key", "--clearmodifiers", key]
            )

        # Execute all commands with minimal delay
        for cmd in key_commands:
            try:
                subprocess.run(
                    cmd, check=True, stderr=subprocess.PIPE, text=True, timeout=0.5
                )
                if delay > 0:
                    time.sleep(delay)
            except subprocess.TimeoutExpired:
                logger.warning("Timeout while typing character")
                continue
            except subprocess.CalledProcessError as e:
                logger.error("Failed to type character: %s", e)
    except FileNotFoundError:
        logger.error("Error: neither kdotool nor xdotool found. type_text action will not work.")
    except Exception as exc:
        logger.exception("Unexpected error while typing text: %s", exc)
        # Try fallback method if the main method fails
        try:
            subprocess.run(
                ["xdotool", "type", "--clearmodifiers", "--delay", "1", "--", text],
                check=True,
            )
        except Exception as fallback_error:
            logger.exception("Fallback typing also failed: %s", fallback_error)


def adjust_device_brightness(device, amount):
    """
    Adjust the device brightness by a relative amount.

    :param device: StreamDock device instance
    :param amount: Amount to adjust brightness (can be positive or negative)
    """
    if device is None:
        logger.error("Error: Device is required for brightness adjustment")
        return

    try:
        new_brightness = device.get_brightness() + amount

        # Clamp to valid range (0-100)
        new_brightness = max(0, min(100, new_brightness))

        # Set new brightness
        device.set_brightness(new_brightness)
    except Exception as e:
        logger.error("Error adjusting brightness: %s", e)


def send_dbus_command(dbus_command):
    """
    Send a D-Bus command for controlling media players, volume, and system services.

    :param dbus_command: Either a string command to execute or a dict with D-Bus parameters

    Examples:
        # String command (will be executed directly)
        "dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.PlayPause"

        # Dict with predefined shortcuts
        {"action": "play_pause"}
        {"action": "next"}
        {"action": "previous"}
        {"action": "volume_up"}
        {"action": "volume_down"}
        {"action": "mute"}
    """
    # Predefined D-Bus shortcuts for common actions
    shortcuts = {
        "play_pause": "dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.PlayPause",
        "play_pause_any": "dbus-send --type=method_call --dest=org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus.ListNames | grep -o 'org.mpris.MediaPlayer2.[^\"]*' | head -1 | xargs -I {} dbus-send --print-reply --dest={} /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.PlayPause",
        "next": "dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Next",
        "previous": "dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Previous",
        "stop": "dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Stop",
        "volume_up": "pactl set-sink-volume @DEFAULT_SINK@ +5%",
        "volume_down": "pactl set-sink-volume @DEFAULT_SINK@ -5%",
        "mute": "pactl set-sink-mute @DEFAULT_SINK@ toggle",
    }

    try:
        # Handle dict format with shortcuts
        if isinstance(dbus_command, dict):
            action = dbus_command.get("action")
            if action in shortcuts:
                command = shortcuts[action]
                subprocess.run(command, shell=True, check=True, capture_output=True)
            else:
                logger.warning("Unknown D-Bus shortcut: %s", action)
        # Handle string format (direct command)
        elif isinstance(dbus_command, str):
            subprocess.run(dbus_command, shell=True, check=True, capture_output=True)
        else:
            logger.error("Invalid D-Bus command format: %s", type(dbus_command))
    except FileNotFoundError:
        logger.error(
            "Error: dbus-send or pactl not found. Install with: sudo apt install dbus pactl"
        )
    except subprocess.CalledProcessError as e:
        logger.error("Error executing D-Bus command: %s", e)


def parse_desktop_file(desktop_file):
    """
    Parse a .desktop file and extract application launch information.

    :param desktop_file: Path to .desktop file or just the filename (e.g., 'firefox.desktop')
    :return: Dict with 'command', 'class_name', and 'name' or None if parsing fails

    Example:
        parse_desktop_file('firefox.desktop')
        # Returns: {'command': ['firefox'], 'class_name': 'firefox', 'name': 'Firefox'}
    """
    # Search paths for .desktop files
    search_paths = [
        "/usr/share/applications/",
        "/usr/local/share/applications/",
        os.path.expanduser("~/.local/share/applications/"),
        "/var/lib/flatpak/exports/share/applications/",
        os.path.expanduser("~/.local/share/flatpak/exports/share/applications/"),
    ]

    desktop_path = None

    # If it's an absolute path and exists, use it directly
    if os.path.isabs(desktop_file) and os.path.exists(desktop_file):
        desktop_path = desktop_file
    else:
        # Search for the file in standard locations
        filename = (
            desktop_file
            if desktop_file.endswith(".desktop")
            else f"{desktop_file}.desktop"
        )
        for search_path in search_paths:
            potential_path = os.path.join(search_path, filename)
            if os.path.exists(potential_path):
                desktop_path = potential_path
                break

    if not desktop_path:
        logger.warning("Desktop file not found: %s", desktop_file)
        return None

    try:
        # Parse the .desktop file
        config = configparser.ConfigParser(interpolation=None)
        config.read(desktop_path)

        if "Desktop Entry" not in config:
            logger.warning(
                f"Invalid desktop file (no [Desktop Entry] section): {desktop_path}"
            )
            return None

        entry = config["Desktop Entry"]

        # Get the Exec command
        exec_line = entry.get("Exec", "")
        if not exec_line:
            logger.warning("No Exec field in desktop file: %s", desktop_path)
            return None

        # Remove field codes (%f, %F, %u, %U, %i, %c, %k, etc.)
        # These are placeholders for files, URLs, etc. that we don't need
        import re

        exec_line = re.sub(r"%[fFuUdDnNickvm]", "", exec_line).strip()

        # Parse the command using shlex to handle quotes properly
        command = shlex.split(exec_line)

        # Get the window class name (StartupWMClass) or derive from command
        class_name = entry.get("StartupWMClass", "")
        if not class_name and command:
            # Use the basename of the first command as class name
            class_name = os.path.basename(command[0])

        # Get the application name
        app_name = entry.get("Name", "")

        return {"command": command, "class_name": class_name.lower(), "name": app_name}

    except Exception as e:
        logger.error("Error parsing desktop file %s: %s", desktop_path, e)
        return None


def launch_or_focus_application(app_config):
    """
    Launch an application if not running, or focus its window if already running.

    :param app_config: Dict with application configuration
        {
            "command": ["firefox"],              # Command to launch (option 1: direct command)
            "desktop_file": "firefox.desktop",   # Desktop file to load (option 2: KDE/GNOME app)
            "class_name": "firefox",             # Window class to search for (optional, defaults to command[0])
            "match_type": "contains",            # "exact" or "contains" (default: "contains")
            "force_new": false                   # Always launch new instance (default: false)
        }
        Or a simple string/list representing the command

    Examples:
        # Simple command
        "firefox"

        # Desktop file (searches standard locations)
        {"desktop_file": "firefox.desktop"}

        # Full path to desktop file
        {"desktop_file": "/usr/share/applications/org.kde.kate.desktop"}

        # Command with options
        {"command": ["firefox", "--private-window"], "force_new": true}
    """
    # Parse configuration
    command, class_name, match_type, force_new = _parse_app_config(app_config)

    if command is None:
        logger.error("Error: LAUNCH_APPLICATION requires either 'command' or 'desktop_file'")
        return

    # If force_new is True, skip window detection and always launch
    if force_new:
        try:
            # Launch in a completely separate process (detached from Python)
            _launch_detached(command)
        except Exception as e:
            logger.error("Error launching application: %s", e)
        finally:
            return

    try:
        # Quick check: is the process already running?
        process_name = command[0] if isinstance(command, list) else command
        # Extract just the executable name (remove path)
        process_name = os.path.basename(process_name)

        try:
            # Check if process exists and launch it if not
            result = subprocess.run(["pgrep", "-x", process_name], capture_output=True, text=True, timeout=1, check=False)
            if result.returncode != 0 or not result.stdout.strip():
                # Process not running, launch it (detached from Python)
                _launch_detached(command)
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # pgrep not available, continue with window detection

        # For Chrome/Chromium apps, also try searching by name (from desktop file)
        search_by_name = None
        if "chromium" in command[0].lower() or "chrome" in command[0].lower():
            # Extract app name from desktop file if we have it
            if isinstance(app_config, dict) and app_config.get("desktop_file"):
                # We already parsed it, get the name
                desktop_info = parse_desktop_file(app_config.get("desktop_file"))
                if desktop_info:
                    search_by_name = desktop_info["name"]

        # Search for the window using kdotool (KDE Wayland)
        if WindowUtils.is_kdotool_available():
            window_id = WindowUtils.kdotool_search_by_class(class_name)
            if not window_id and search_by_name:
                window_id = WindowUtils.kdotool_search_by_name(search_by_name)
            
            if window_id and WindowUtils.kdotool_activate_window(window_id):
                return True

        # Search for the window using xdotool (X11 sessions)
        elif WindowUtils.is_xdotool_available():
            window_id = WindowUtils.xdotool_search_by_class(class_name)
            if not window_id and search_by_name:
                window_id = WindowUtils.xdotool_search_by_name(search_by_name)
            
            if window_id and WindowUtils.xdotool_activate_window(window_id):
                return True

        # Last resort: try wmctrl (works on some Wayland compositors)
        try:
            result = subprocess.run(
                ["wmctrl", "-xa", class_name], capture_output=True, text=True, timeout=2, check=False
            )
            if result.returncode == 0:
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # If we got here, window detection failed but process is running
        # Launch new instance anyway (user may have minimized or hidden it)
        logger.info(f"Window not found for class '{class_name}', launching new instance")
        # Launch in a completely separate process (detached from Python)
        _launch_detached(command)

    except Exception as exc:
        logger.exception(f"Unhandled exception in LAUNCH_APPLICATION: {exc}")


def _parse_app_config(app_config):
    command = None
    class_name = None
    match_type = "contains"
    force_new = False

    if isinstance(app_config, str):
        # Simple string command
        command = [app_config]
        class_name = app_config.lower()
    elif isinstance(app_config, list):
        # List command
        command = app_config
        class_name = app_config[0].lower()
    elif isinstance(app_config, dict):
        # Full configuration - check for desktop_file first
        desktop_file = app_config.get("desktop_file")

        if desktop_file:
            # Parse desktop file
            desktop_info = parse_desktop_file(desktop_file)
            if desktop_info:
                command = desktop_info["command"]
                class_name = desktop_info["class_name"]
                logger.debug("Loaded from desktop file: %s", desktop_info['name'])
                logger.debug("  Command: %s", ' '.join(command))
                logger.debug("  Window class: %s", class_name)
                # Allow override of class_name from config
                if "class_name" in app_config:
                    class_name = app_config["class_name"].lower()
                    logger.debug("  Overridden class: %s", class_name)
            else:
                logger.warning("Failed to parse desktop file: %s", desktop_file)
                return None, None, "contains", False
        else:
            # Use command parameter
            command = app_config.get("command")
            if isinstance(command, str):
                command = [command]
            if command:
                class_name = app_config.get("class_name", command[0]).lower()

        match_type = app_config.get("match_type", "contains")
        force_new = app_config.get("force_new", False)
    else:
        logger.error("Invalid LAUNCH_APPLICATION parameter: %s", app_config)
        return None, None, "contains", False

    return command, class_name, match_type, force_new

def execute_action(action, device=None, key_number=None):
    """
    Execute a single action.

    :param action: Tuple of (ActionType, parameter)
    :param device: StreamDock device instance (required for CHANGE_KEY_IMAGE, CHANGE_KEY, CHANGE_LAYOUT)
    :param key_number: Key number (required for CHANGE_KEY_IMAGE)
    """
    if not isinstance(action, tuple) or len(action) != 2:
        logger.error(f"Invalid action format: {action}. Expected (ActionType, parameter)")
        return

    action_type, parameter = action

    if action_type == ActionType.EXECUTE_COMMAND:
        execute_command(parameter)

    elif action_type == ActionType.KEY_PRESS:
        emulate_key_combo(parameter)

    elif action_type == ActionType.TYPE_TEXT:
        type_text(parameter)

    elif action_type == ActionType.WAIT:
        time.sleep(parameter)

    elif action_type == ActionType.CHANGE_KEY_IMAGE:
        if device is None or key_number is None:
            logger.error("Error: CHANGE_KEY_IMAGE requires device and key_number")
            return
        device.set_key_image(key_number, parameter)

    elif action_type == ActionType.CHANGE_KEY_TEXT:
        if device is None or key_number is None:
            logger.error("Error: CHANGE_KEY_TEXT requires device and key_number")
            return

        # Parameter should be a dict with text and optional styling
        if isinstance(parameter, dict):
            text = parameter.get("text", "")
            text_color = parameter.get("text_color", "white")
            background_color = parameter.get("background_color", "black")
            font_size = parameter.get("font_size", 20)
            bold = parameter.get("bold", True)
        elif isinstance(parameter, str):
            # Simple string format
            text = parameter
            text_color = "white"
            background_color = "black"
            font_size = 20
            bold = True
        else:
            logger.error("Error: CHANGE_KEY_TEXT parameter must be dict or string")
            return

        # Generate text image
        import tempfile

        from .ImageHelpers.PILHelper import create_text_image
        try:
            text_image = create_text_image(
                text=text,
                size=(112, 112),
                text_color=text_color,
                background_color=background_color,
                font_size=font_size,
                bold=bold,
            )

            # Save to temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix=".png", prefix="key_text_")
            os.close(temp_fd)
            text_image.save(temp_path)

            # Set the key image
            device.set_key_image(key_number, temp_path)

            # Clean up temp file after a short delay (let device load it first)
            # TODO: Come up with better handling of the temp file
            def cleanup():
                time.sleep(0.5)
                try:
                    os.remove(temp_path)
                except:
                    pass

            Thread(target=cleanup, daemon=True).start()

        except Exception as e:
            logger.error("Error creating text image: %s", e)

    elif action_type == ActionType.CHANGE_KEY:
        if device is None:
            logger.error("Error: CHANGE_KEY requires device")
            return
        if key_number is None:
            logger.error("Error: CHANGE_KEY requires key_number")
            return
        # The parameter is a Key object that will configure itself
        # Update the key_number to match the button that triggered this action
        parameter.key_number = key_number
        # Recalculate logical key after updating key_number
        parameter.logical_key = parameter.KEY_MAPPING.get(key_number, key_number)
        
        logger.debug("Configuring key %d: %s", key_number, parameter)
        parameter._configure()

    elif action_type == ActionType.CHANGE_LAYOUT:
        if device is None:
            logger.error("Error: CHANGE_LAYOUT requires device")
            return

        # Parameter is a dict with layout and options
        layout = parameter["layout"]
        action_clear_all = parameter.get("clear_all", False)

        # Action's clear_all overrides layout's clear_all if explicitly set to True
        if action_clear_all and not layout.clear_all:
            device.clearAllIcon()

        # Apply the layout (which will also check layout's clear_all setting)
        layout.apply()

    elif action_type == ActionType.DBUS:
        send_dbus_command(parameter)

    elif action_type == ActionType.DEVICE_BRIGHTNESS_UP:
        if device is None:
            logger.error("Error: DEVICE_BRIGHTNESS_UP requires device")
            return
        adjust_device_brightness(device, 10)

    elif action_type == ActionType.DEVICE_BRIGHTNESS_DOWN:
        if device is None:
            logger.error("Error: DEVICE_BRIGHTNESS_DOWN requires device")
            return
        adjust_device_brightness(device, -10)

    elif action_type == ActionType.LAUNCH_APPLICATION:
        launch_or_focus_application(parameter)

    else:
        logger.warning("Unknown action type: %s", action_type)


def execute_actions(actions, device=None, key_number=None):
    """
    Execute a list of actions sequentially.

    :param actions: List of action tuples [(ActionType, parameter), ...]
    :param device: StreamDock device instance
    :param key_number: Key number for CHANGE_KEY_IMAGE actions
    """
    if not isinstance(actions, list):
        actions = [actions]

    for action in actions:
        execute_action(action, device=device, key_number=key_number)

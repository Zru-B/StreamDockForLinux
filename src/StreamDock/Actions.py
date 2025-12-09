from enum import Enum
import subprocess
import time
import os
import shlex
import configparser


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
        cmd_str = ' '.join(shlex.quote(arg) for arg in command)
    
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
        close_fds=True
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
    except Exception as e:
        print(f"Error executing command: {e}")


def emulate_key_combo(combo_string):
    """
    Emulate a keyboard combination using xdotool.
    
    :param combo_string: String like 'CTRL+C', 'ALT+F4', etc.
    """
    # Mapping of string names to xdotool key names
    key_mapping = {
        'CTRL': 'ctrl', 'CONTROL': 'ctrl',
        'ALT': 'alt',
        'SHIFT': 'shift',
        'META': 'super', 'SUPER': 'super', 'WIN': 'super', 'COMMAND': 'super', 'CMD': 'super',
        'ENTER': 'Return', 'RETURN': 'Return',
        'TAB': 'Tab',
        'SPACE': 'space',
        'BACKSPACE': 'BackSpace',
        'DELETE': 'Delete', 'DEL': 'Delete',
        'ESC': 'Escape', 'ESCAPE': 'Escape',
        'HOME': 'Home', 'END': 'End',
        'PAGEUP': 'Page_Up', 'PAGEDOWN': 'Page_Down',
        'UP': 'Up', 'DOWN': 'Down', 'LEFT': 'Left', 'RIGHT': 'Right',
        'F1': 'F1', 'F2': 'F2', 'F3': 'F3', 'F4': 'F4',
        'F5': 'F5', 'F6': 'F6', 'F7': 'F7', 'F8': 'F8',
        'F9': 'F9', 'F10': 'F10', 'F11': 'F11', 'F12': 'F12',
    }

    keys = [k.strip().upper() for k in combo_string.split('+')]
    if not keys:
        print(f"Invalid key combination: {combo_string}")
        return

    xdotool_keys = []
    for key in keys:
        if key in key_mapping:
            xdotool_keys.append(key_mapping[key])
        elif len(key) == 1:
            xdotool_keys.append(key.lower())
        else:
            print(f"Unknown key: {key}")
            return

    try:
        subprocess.run(['xdotool', 'key', '+'.join(xdotool_keys)], check=True)
    except FileNotFoundError:
        print("Error: xdotool not found. Install with: sudo apt install xdotool")
    except subprocess.CalledProcessError as e:
        print(f"Error pressing key combination: {e}")


def type_text(text, delay=0.001):
    """
    Type text using xdotool, ensuring case sensitivity by using key events.
    
    :param text: Text to type (case-sensitive)
    :param delay: Delay between key presses in seconds (default: 0.001s for fast typing)
    """
    if not text:
        return
        
    try:
        # Get the active window ID to ensure we type in the right window
        try:
            window_id = subprocess.check_output(['xdotool', 'getactivewindow']).decode('utf-8').strip()
            window_args = ['windowactivate', '--sync', window_id]
        except Exception as e:
            # If we can't get window ID, continue without it (might be slightly less reliable)
            window_args = []
        
        # Prepare all key commands at once
        key_commands = []
        for char in text:
            # Handle special characters
            if char == ' ':
                key = 'space'
            elif char == '\n':
                key = 'Return'
            elif char == '\t':
                key = 'Tab'
            elif char in "!@#$%^&*()_+{}|:\"<>?~`-=[]\\;',./":
                key = char
            else:
                key = char
            
            # Build the command
            key_commands.append(['xdotool'] + window_args + ['key', '--clearmodifiers', key])
        
        # Execute all commands with minimal delay
        for cmd in key_commands:
            try:
                subprocess.run(cmd, check=True, stderr=subprocess.PIPE, text=True, timeout=0.5)
                if delay > 0:
                    time.sleep(delay)
            except subprocess.TimeoutExpired:
                print(f"[WARNING] Timeout while typing character")
                continue
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] Failed to type character: {e}")
                if e.stderr:
                    print(f"[ERROR] stderr: {e.stderr}")
    
    except FileNotFoundError:
        print("[ERROR] xdotool not found. Install with: sudo apt install xdotool")
    except Exception as e:
        print(f"[ERROR] Unexpected error while typing text: {e}")
        # Try fallback method if the main method fails
        try:
            subprocess.run(['xdotool', 'type', '--clearmodifiers', '--delay', '1', '--', text], check=True)
        except Exception as fallback_error:
            print(f"[ERROR] Fallback typing also failed: {fallback_error}")


def adjust_device_brightness(device, amount):
    """
    Adjust the device brightness by a relative amount.
    
    :param device: StreamDock device instance
    :param amount: Amount to adjust brightness (can be positive or negative)
    """
    if device is None:
        print("Error: Device is required for brightness adjustment")
        return
    
    try:
        # Get current brightness (stored as an attribute on the device)
        current_brightness = getattr(device, '_current_brightness', 50)
        
        # Calculate new brightness
        new_brightness = current_brightness + amount
        
        # Clamp to valid range (0-100)
        new_brightness = max(0, min(100, new_brightness))
        
        # Set new brightness
        device.set_brightness(new_brightness)
        
        # Store the new brightness value
        device._current_brightness = new_brightness
    except Exception as e:
        print(f"Error adjusting brightness: {e}")


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
                print(f"Unknown D-Bus shortcut: {action}")
        # Handle string format (direct command)
        elif isinstance(dbus_command, str):
            subprocess.run(dbus_command, shell=True, check=True, capture_output=True)
        else:
            print(f"Invalid D-Bus command format: {type(dbus_command)}")
    except FileNotFoundError:
        print("Error: dbus-send or pactl not found. Install with: sudo apt install dbus pactl")
    except subprocess.CalledProcessError as e:
        print(f"Error executing D-Bus command: {e}")


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
        '/usr/share/applications/',
        '/usr/local/share/applications/',
        os.path.expanduser('~/.local/share/applications/'),
        '/var/lib/flatpak/exports/share/applications/',
        os.path.expanduser('~/.local/share/flatpak/exports/share/applications/'),
    ]
    
    desktop_path = None
    
    # If it's an absolute path and exists, use it directly
    if os.path.isabs(desktop_file) and os.path.exists(desktop_file):
        desktop_path = desktop_file
    else:
        # Search for the file in standard locations
        filename = desktop_file if desktop_file.endswith('.desktop') else f"{desktop_file}.desktop"
        for search_path in search_paths:
            potential_path = os.path.join(search_path, filename)
            if os.path.exists(potential_path):
                desktop_path = potential_path
                break
    
    if not desktop_path:
        print(f"Desktop file not found: {desktop_file}")
        return None
    
    try:
        # Parse the .desktop file
        config = configparser.ConfigParser(interpolation=None)
        config.read(desktop_path)
        
        if 'Desktop Entry' not in config:
            print(f"Invalid desktop file (no [Desktop Entry] section): {desktop_path}")
            return None
        
        entry = config['Desktop Entry']
        
        # Get the Exec command
        exec_line = entry.get('Exec', '')
        if not exec_line:
            print(f"No Exec field in desktop file: {desktop_path}")
            return None
        
        # Remove field codes (%f, %F, %u, %U, %i, %c, %k, etc.)
        # These are placeholders for files, URLs, etc. that we don't need
        import re
        exec_line = re.sub(r'%[fFuUdDnNickvm]', '', exec_line).strip()
        
        # Parse the command using shlex to handle quotes properly
        command = shlex.split(exec_line)
        
        # Get the window class name (StartupWMClass) or derive from command
        class_name = entry.get('StartupWMClass', '')
        if not class_name and command:
            # Use the basename of the first command as class name
            class_name = os.path.basename(command[0])
        
        # Get the application name
        app_name = entry.get('Name', '')
        
        return {
            'command': command,
            'class_name': class_name.lower(),
            'name': app_name
        }
    
    except Exception as e:
        print(f"Error parsing desktop file {desktop_path}: {e}")
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
    force_new = False  # Default: try to focus existing window
    command = None
    class_name = None
    match_type = "contains"
    
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
                command = desktop_info['command']
                class_name = desktop_info['class_name']
                print(f"Loaded from desktop file: {desktop_info['name']}")
                print(f"  Command: {' '.join(command)}")
                print(f"  Window class: {class_name}")
                # Allow override of class_name from config
                if "class_name" in app_config:
                    class_name = app_config["class_name"].lower()
                    print(f"  Overridden class: {class_name}")
            else:
                print(f"Failed to parse desktop file: {desktop_file}")
                return
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
        print(f"Invalid LAUNCH_APPLICATION parameter: {app_config}")
        return
    
    if not command:
        print("Error: LAUNCH_APPLICATION requires either 'command' or 'desktop_file'")
        return
    
    # If force_new is True, skip window detection and always launch
    if force_new:
        try:
            # Launch in a completely separate process (detached from Python)
            _launch_detached(command)
            return
        except Exception as e:
            print(f"Error launching application: {e}")
            return
    
    try:
        # Quick check: is the process already running?
        process_name = command[0] if isinstance(command, list) else command
        # Extract just the executable name (remove path)
        process_name = os.path.basename(process_name)
        
        try:
            # Check if process exists
            result = subprocess.run(
                ['pgrep', '-x', process_name],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            if result.returncode != 0 or not result.stdout.strip():
                # Process not running, launch it (detached from Python)
                _launch_detached(command)
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # pgrep not available, continue with window detection
        
        # Process is running, try to find and focus window
        window_found = False
        
        # For Chrome/Chromium apps, also try searching by name (from desktop file)
        search_by_name = None
        if 'chromium' in command[0].lower() or 'chrome' in command[0].lower():
            # Extract app name from desktop file if we have it
            if isinstance(app_config, dict) and app_config.get('desktop_file'):
                # We already parsed it, get the name
                desktop_info = parse_desktop_file(app_config.get('desktop_file'))
                if desktop_info:
                    search_by_name = desktop_info['name']
        
        # Try kdotool first (KDE Wayland)
        try:
            # Search for window by class name
            result = subprocess.run(
                ['kdotool', 'search', '--class', class_name],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0 and result.stdout.strip():
                # Window found, get the window ID
                window_id = result.stdout.strip().split('\n')[0]
                print(f"Found window (kdotool): {window_id} for class '{class_name}'")
                # Activate the window
                subprocess.run(
                    ['kdotool', 'windowactivate', window_id],
                    check=True,
                    timeout=2
                )
                window_found = True
            elif search_by_name and not window_found:
                # Fallback: Try searching by window name for Chrome apps
                result = subprocess.run(
                    ['kdotool', 'search', '--name', search_by_name],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    window_id = result.stdout.strip().split('\n')[0]
                    print(f"Found window (kdotool by name): {window_id} for '{search_by_name}'")
                    subprocess.run(
                        ['kdotool', 'windowactivate', window_id],
                        check=True,
                        timeout=2
                    )
                    window_found = True
        
        except FileNotFoundError:
            # kdotool not available, try other methods
            pass
        except subprocess.TimeoutExpired:
            pass
        
        # Try xdotool as fallback (for X11 sessions)
        if not window_found:
            try:
                # Search for windows by class name (search all desktops)
                result = subprocess.run(
                    ['xdotool', 'search', '--all', '--onlyvisible', '--class', class_name],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    # Window found, focus it
                    window_ids = result.stdout.strip().split('\n')
                    if window_ids:
                        print(f"Found window (xdotool): {window_ids[0]} for class '{class_name}'")
                        # Focus the first matching window
                        subprocess.run(
                            ['xdotool', 'windowactivate', window_ids[0]],
                            check=True,
                            timeout=2
                        )
                        window_found = True
                elif search_by_name and not window_found:
                    # Fallback: Try searching by window name for Chrome apps
                    result = subprocess.run(
                        ['xdotool', 'search', '--all', '--name', search_by_name],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        window_ids = result.stdout.strip().split('\n')
                        if window_ids:
                            print(f"Found window (xdotool by name): {window_ids[0]} for '{search_by_name}'")
                            subprocess.run(
                                ['xdotool', 'windowactivate', window_ids[0]],
                                check=True,
                                timeout=2
                            )
                            window_found = True
            
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        
        # If we found a window, we're done
        if window_found:
            return
        
        # Last resort: try wmctrl (works on some Wayland compositors)
        try:
            result = subprocess.run(
                ['wmctrl', '-xa', class_name],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # If we got here, window detection failed but process is running
        # Launch new instance anyway (user may have minimized or hidden it)
        print(f"Window not found for class '{class_name}', launching new instance")
        # Launch in a completely separate process (detached from Python)
        _launch_detached(command)
    
    except Exception as e:
        print(f"Error in LAUNCH_APPLICATION: {e}")


def execute_action(action, device=None, key_number=None):
    """
    Execute a single action.
    
    :param action: Tuple of (ActionType, parameter)
    :param device: StreamDock device instance (required for CHANGE_KEY_IMAGE, CHANGE_KEY, CHANGE_LAYOUT)
    :param key_number: Key number (required for CHANGE_KEY_IMAGE)
    """
    if not isinstance(action, tuple) or len(action) != 2:
        print(f"Invalid action format: {action}. Expected (ActionType, parameter)")
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
            print("Error: CHANGE_KEY_IMAGE requires device and key_number")
            return
        device.set_key_image(key_number, parameter)
    
    elif action_type == ActionType.CHANGE_KEY_TEXT:
        if device is None or key_number is None:
            print("Error: CHANGE_KEY_TEXT requires device and key_number")
            return
        
        # Parameter should be a dict with text and optional styling
        if isinstance(parameter, dict):
            text = parameter.get('text', '')
            text_color = parameter.get('text_color', 'white')
            background_color = parameter.get('background_color', 'black')
            font_size = parameter.get('font_size', 20)
            bold = parameter.get('bold', True)
        elif isinstance(parameter, str):
            # Simple string format
            text = parameter
            text_color = 'white'
            background_color = 'black'
            font_size = 20
            bold = True
        else:
            print(f"Error: CHANGE_KEY_TEXT parameter must be dict or string")
            return
        
        # Generate text image
        from .ImageHelpers.PILHelper import create_text_image
        import tempfile
        import os
        
        try:
            text_image = create_text_image(
                text=text,
                size=(112, 112),
                text_color=text_color,
                background_color=background_color,
                font_size=font_size,
                bold=bold
            )
            
            # Save to temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix='.png', prefix='key_text_')
            os.close(temp_fd)
            text_image.save(temp_path)
            
            # Set the key image
            device.set_key_image(key_number, temp_path)
            
            # Clean up temp file after a short delay (let device load it first)
            # Note: In production, you might want to manage this better
            import threading
            def cleanup():
                time.sleep(0.5)
                try:
                    os.remove(temp_path)
                except:
                    pass
            threading.Thread(target=cleanup, daemon=True).start()
            
        except Exception as e:
            print(f"Error creating text image: {e}")
    
    elif action_type == ActionType.CHANGE_KEY:
        if device is None:
            print("Error: CHANGE_KEY requires device")
            return
        # The parameter is a Key object that will configure itself
        parameter._configure()
    
    elif action_type == ActionType.CHANGE_LAYOUT:
        if device is None:
            print("Error: CHANGE_LAYOUT requires device")
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
            print("Error: DEVICE_BRIGHTNESS_UP requires device")
            return
        adjust_device_brightness(device, 10)
    
    elif action_type == ActionType.DEVICE_BRIGHTNESS_DOWN:
        if device is None:
            print("Error: DEVICE_BRIGHTNESS_DOWN requires device")
            return
        adjust_device_brightness(device, -10)
    
    elif action_type == ActionType.LAUNCH_APPLICATION:
        launch_or_focus_application(parameter)
    
    else:
        print(f"Unknown action type: {action_type}")


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

# Actions Reference

This document provides a detailed reference for all actions available in the `config.yml` file. Actions are executed sequentially within `on_press_actions`, `on_release_actions`, and `on_double_press_actions`.

---

### `EXECUTE_COMMAND`

Executes a system command in a detached process. This is useful for launching applications or running scripts.

**Format:**
```yaml
- "EXECUTE_COMMAND": ["command", "arg1", "arg2"]
```

**Example:**
```yaml
- "EXECUTE_COMMAND": ["firefox"]
- "EXECUTE_COMMAND": ["dolphin", "/home/user"]
```

**Note:** Commands are executed via `nohup` and run in a completely separate process. Their output will not appear in the StreamDock console, and they will continue to run even if the main script is stopped.

---

### `LAUNCH_APPLICATION`

A "run or raise" action that launches an application if it's not running, or focuses its main window if it is. This is the recommended way to launch GUI applications.

**Formats:**

```yaml
# 1. Simple command (string or list)
- "LAUNCH_APPLICATION": "firefox"
- "LAUNCH_APPLICATION": ["dolphin", "/home"]

# 2. Using .desktop files (recommended for most GUI apps)
- "LAUNCH_APPLICATION":
    desktop_file: "firefox.desktop" # Searches standard system locations

# 3. Advanced format with specific matching
- "LAUNCH_APPLICATION":
    command: ["code"]
    class_name: "code"             # Explicitly define the window class to search for
    match_type: "exact"            # "exact" or "contains" (default)
    force_new: true                # Always launch a new instance
```

**How It Works:**
1.  If `force_new: true`, it always launches a new instance.
2.  Otherwise, it searches for an existing window matching the application's `class_name`.
3.  If a window is found, it is focused.
4.  If no window is found, the application is launched using the specified `command` or the command from the `desktop_file`.

**Process Behavior:**
- Like `EXECUTE_COMMAND`, launched applications run in a completely detached process.

**Parameters:**
- `command` (option 1): The command to execute (string or list).
- `desktop_file` (option 2): The application's `.desktop` file name (e.g., `org.kde.konsole.desktop`) or full path. The system is searched automatically.
- `class_name` (optional): Overrides the window class name used for searching. If omitted, it's inferred from the command or desktop file.
- `match_type` (optional): `contains` (default) or `exact`.
- `force_new` (optional): `true` to always launch a new instance.

---

### `KEY_PRESS`

Simulates a keyboard shortcut.

**Format:**
```yaml
- "KEY_PRESS": "MODIFIER+KEY"
```

**Supported Modifiers:** `CTRL`, `ALT`, `SHIFT`, `SUPER` (the Windows/Meta key).

**Example:**
```yaml
- "KEY_PRESS": "CTRL+C"
- "KEY_PRESS": "CTRL+ALT+T"
- "KEY_PRESS": "SUPER+L" # Locks the screen on many desktops
```

---

### `TYPE_TEXT`

Types a given string of text.

**Format:**
```yaml
- "TYPE_TEXT": "your-email@example.com"
```

---

### `WAIT`

Pauses the execution of subsequent actions for a specified duration.

**Format:**
```yaml
- "WAIT": 0.5 # Pauses for 0.5 seconds
```

---

### `CHANGE_KEY_IMAGE`

Dynamically changes the image of the key being interacted with.

**Format:**
```yaml
- "CHANGE_KEY_IMAGE": "../img/new_icon.png"
```

**Note:** The path is relative to the `config.yml` file.

---

### `CHANGE_LAYOUT`

Switches the device to a different, named layout.

**Formats:**
```yaml
# 1. Simple format
- "CHANGE_LAYOUT": "Media_Layout"

# 2. Advanced format with options
- "CHANGE_LAYOUT":
    layout: "Media_Layout"
    clear_all: true # Optional: clears all keys before switching
```

**Parameters:**
- `layout` (required): The name of the layout to switch to.
- `clear_all` (optional): If `true`, all keys on the device are cleared before the new layout is applied. This is useful for creating clean transitions between screens. Defaults to `false`.

---

### `DBUS`

Sends a D-Bus command, commonly used for controlling media players and system volume.

**Format:**
```yaml
- "DBUS": {"action": "shortcut_name"}
```

**Predefined Shortcuts:**
- `play_pause`: Toggles play/pause for MPRIS-compatible players (e.g., Spotify).
- `next`: Skips to the next track.
- `previous`: Skips to the previous track.
- `volume_up`: Increases system volume via PulseAudio/PipeWire.
- `volume_down`: Decreases system volume.
- `mute`: Toggles system mute.

**Example:**
```yaml
- "DBUS": {"action": "play_pause"}
- "DBUS": {"action": "volume_up"}
```

---

### `DEVICE_BRIGHTNESS_UP` / `DEVICE_BRIGHTNESS_DOWN`

Adjusts the device's LED brightness by a 10% increment.

**Format:**
```yaml
- "DEVICE_BRIGHTNESS_UP": ""
- "DEVICE_BRIGHTNESS_DOWN": ""
```

---

### Chaining Multiple Actions

Actions in a list are executed sequentially, allowing you to create powerful macros.

**Example:** A "Copy and Paste" key.
```yaml
on_press_actions:
  - "KEY_PRESS": "CTRL+C"
  - "WAIT": 0.1
  - "KEY_PRESS": "CTRL+V"
```

**Example:** Log into a server.
```yaml
on_press_actions:
  - "TYPE_TEXT": "ssh user@server.com"
  - "KEY_PRESS": "Return"
  - "WAIT": 1.5 # Wait for password prompt
  - "TYPE_TEXT": "YourSecretPassword"
  - "KEY_PRESS": "Return"
```

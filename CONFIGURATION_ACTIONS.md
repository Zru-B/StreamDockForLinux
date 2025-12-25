# Actions Reference

This document provides a comprehensive reference for all actions available in StreamDockForLinux. Actions are executed sequentially within `on_press_actions`, `on_release_actions`, and `on_double_press_actions`.

## Table of Contents

- [EXECUTE_COMMAND](#execute_command) - Execute system commands
- [LAUNCH_APPLICATION](#launch_application) - Launch or focus applications
- [KEY_PRESS](#key_press) - Simulate keyboard shortcuts
- [TYPE_TEXT](#type_text) - Type text strings
- [WAIT](#wait) - Pause execution
- [CHANGE_KEY_IMAGE](#change_key_image) - Change key icon dynamically
- [CHANGE_KEY_TEXT](#change_key_text) - Change key text dynamically
- [CHANGE_KEY](#change_key) - Replace entire key configuration
- [CHANGE_LAYOUT](#change_layout) - Switch between layouts
- [DBUS](#dbus) - Control media players and system services
- [DEVICE_BRIGHTNESS_UP / DEVICE_BRIGHTNESS_DOWN](#device_brightness) - Adjust device brightness
- [Chaining Actions](#chaining-multiple-actions) - Combine actions into macros

---

## `EXECUTE_COMMAND`

Executes a system command in a completely detached process. The command continues running even if StreamDock is stopped.

**Format:**
```yaml
- "EXECUTE_COMMAND": ["command", "arg1", "arg2"]
# or
- "EXECUTE_COMMAND": "simple-command"
```

**Examples:**
```yaml
# Launch Firefox
- "EXECUTE_COMMAND": ["firefox"]

# Open file manager in specific directory
- "EXECUTE_COMMAND": ["dolphin", "/home/user/Documents"]

# Run a script
- "EXECUTE_COMMAND": ["/home/user/scripts/backup.sh"]
```

**Behavior:**
- Commands are launched via `nohup` in a separate process session
- Output does not appear in StreamDock console
- Process continues running independently of StreamDock
- Suitable for launching background tasks and scripts

**Note:** For GUI applications, consider using `LAUNCH_APPLICATION` instead for better window management.

---

## `LAUNCH_APPLICATION`

A "run or raise" action that intelligently launches an application if not running, or focuses its window if already running. **This is the recommended way to launch GUI applications.**

**Formats:**

```yaml
# 1. Simple command (string or list)
- "LAUNCH_APPLICATION": "firefox"
- "LAUNCH_APPLICATION": ["dolphin", "/home"]

# 2. Using .desktop files (recommended for most GUI apps)
- "LAUNCH_APPLICATION":
    desktop_file: "firefox.desktop"  # Searches standard system locations

# 3. Full path to .desktop file
- "LAUNCH_APPLICATION":
    desktop_file: "/usr/share/applications/org.kde.kate.desktop"

# 4. Advanced format with specific options
- "LAUNCH_APPLICATION":
    command: ["code", "--new-window"]
    class_name: "code"              # Override window class for matching
    match_type: "exact"             # "exact" or "contains" (default: "contains")
    force_new: true                 # Always launch new instance (default: false)
```

**How It Works:**
1. If `force_new: true`, always launches a new instance
2. Otherwise, checks if process is running using `pgrep`
3. If running, searches for window by `class_name` using `kdotool` (Wayland) or `xdotool` (X11)
4. If window found, focuses it
5. If no window found or process not running, launches the application

**Parameters:**
- `command` (option 1): Command to execute (string or list)
- `desktop_file` (option 2): `.desktop` file name or full path
  - Automatically searches: `/usr/share/applications/`, `/usr/local/share/applications/`, `~/.local/share/applications/`, flatpak directories
  - Extracts command, window class, and app name from desktop file
- `class_name` (optional): Override window class for matching (defaults to command basename or `StartupWMClass` from desktop file)
- `match_type` (optional): `"contains"` (default) or `"exact"`
- `force_new` (optional): `true` to always launch new instance

**Desktop File Search Locations:**
- `/usr/share/applications/`
- `/usr/local/share/applications/`
- `~/.local/share/applications/`
- `/var/lib/flatpak/exports/share/applications/`
- `~/.local/share/flatpak/exports/share/applications/`

**Examples:**
```yaml
# Simple - launch or focus Firefox
- "LAUNCH_APPLICATION": "firefox"

# Using desktop file (recommended)
- "LAUNCH_APPLICATION":
    desktop_file: "org.kde.konsole.desktop"

# Always open new window
- "LAUNCH_APPLICATION":
    command: ["firefox", "--private-window"]
    force_new: true

# Custom window class matching
- "LAUNCH_APPLICATION":
    command: "code"
    class_name: "Code"
    match_type: "exact"
```

**Process Behavior:**
- Like `EXECUTE_COMMAND`, applications run in detached processes
- Survives StreamDock shutdown

**Platform Support:**
- **Wayland (KDE)**: Uses `kdotool` for window detection and focusing
- **X11**: Uses `xdotool` for window detection and focusing
- **Fallback**: Uses `wmctrl` if available

---

## `KEY_PRESS`

Simulates keyboard shortcuts and key combinations.

**Format:**
```yaml
- "KEY_PRESS": "MODIFIER+KEY"
# or multiple modifiers
- "KEY_PRESS": "CTRL+SHIFT+KEY"
```

**Supported Modifiers:**
- `CTRL` or `CONTROL` - Control key
- `ALT` - Alt key
- `SHIFT` - Shift key
- `SUPER`, `META`, `WIN`, `COMMAND`, `CMD` - Super/Windows/Meta key

**Supported Special Keys:**
- `ENTER`, `RETURN` - Enter key
- `TAB` - Tab key
- `SPACE` - Space bar
- `BACKSPACE` - Backspace
- `DELETE`, `DEL` - Delete key
- `ESC`, `ESCAPE` - Escape key
- `HOME`, `END` - Home/End keys
- `PAGEUP`, `PAGEDOWN` - Page Up/Down
- `UP`, `DOWN`, `LEFT`, `RIGHT` - Arrow keys
- `F1` through `F12` - Function keys

**Examples:**
```yaml
# Copy
- "KEY_PRESS": "CTRL+C"

# Paste
- "KEY_PRESS": "CTRL+V"

# Open terminal (common Linux shortcut)
- "KEY_PRESS": "CTRL+ALT+T"

# Lock screen (KDE/GNOME)
- "KEY_PRESS": "SUPER+L"

# Screenshot (common shortcut)
- "KEY_PRESS": "SHIFT+PRINT"

# Media controls
- "KEY_PRESS": "SPACE"  # Play/Pause in media players

# Function keys
- "KEY_PRESS": "F11"  # Fullscreen in browsers
```

**Implementation:**
1. **VirtualKeyboard** (preferred): Uses `/dev/uinput` for direct input injection
2. **kdotool** (Wayland fallback): For KDE Plasma on Wayland
3. **xdotool** (X11 fallback): For X11 sessions

**Case Sensitivity:** Key names are case-insensitive. Single character keys are automatically lowercased.

---

## `TYPE_TEXT`

Types a string of text character-by-character, preserving case and special characters.

**Format:**
```yaml
- "TYPE_TEXT": "text to type"
```

**Examples:**
```yaml
# Type email address
- "TYPE_TEXT": "user@example.com"

# Type password (not recommended - use password managers!)
- "TYPE_TEXT": "MyP@ssw0rd!"

# Type multi-line text (use \n for newlines)
- "TYPE_TEXT": "Line 1\nLine 2\nLine 3"

# Type code snippet
- "TYPE_TEXT": "console.log('Hello, World!');"
```

**Special Character Support:**
- Spaces, newlines (`\n`), tabs (`\t`)
- Punctuation: `!@#$%^&*()_+{}|:"<>?~` `-=[]\;',./`
- Case-sensitive (preserves uppercase and lowercase)

**Implementation:**
1. **VirtualKeyboard** (preferred): Direct input injection via `/dev/uinput`
2. **kdotool** (Wayland fallback): `kdotool type`
3. **xdotool** (X11 fallback): Individual key events with `--clearmodifiers`

**Performance:**
- Default delay: 0.001s (1ms) between characters
- Fast typing suitable for most applications
- Automatically activates target window (X11 only)

**Use Cases:**
- Auto-fill forms
- Insert boilerplate text
- Type commands or code snippets
- Enter credentials (though password managers are preferred)

---

## `WAIT`

Pauses execution for a specified duration before continuing to the next action.

**Format:**
```yaml
- "WAIT": seconds  # Floating point number
```

**Examples:**
```yaml
# Wait half a second
- "WAIT": 0.5

# Wait 2 seconds
- "WAIT": 2

# Wait 100ms
- "WAIT": 0.1
```

**Use Cases:**
- Allow time for applications to launch
- Wait for UI elements to appear
- Pace automated sequences
- Ensure commands complete before next action

**Example with Context:**
```yaml
on_press_actions:
  - "LAUNCH_APPLICATION": "konsole"
  - "WAIT": 1.5  # Wait for terminal to open
  - "TYPE_TEXT": "ssh user@server.com"
  - "KEY_PRESS": "RETURN"
```

---

## `CHANGE_KEY_IMAGE`

Dynamically changes the icon/image of the currently pressed key.

**Format:**
```yaml
- "CHANGE_KEY_IMAGE": "path/to/image.png"
```

**Examples:**
```yaml
# Change to a different icon
- "CHANGE_KEY_IMAGE": "./img/pause.png"

# Absolute path
- "CHANGE_KEY_IMAGE": "/home/user/icons/recording.png"

# Relative to config file
- "CHANGE_KEY_IMAGE": "../icons/active.png"
```

**Supported Formats:**
- PNG, JPG, JPEG, GIF, SVG, BMP

**Path Resolution:**
- Relative paths are resolved relative to the `config.yml` file location
- Absolute paths are used as-is
- Environment variables and `~` are expanded

**Use Cases:**
- Toggle button states (play/pause, on/off)
- Visual feedback for state changes
- Indicate active/inactive modes
- Show recording status

**Note:** This only changes the image, not the actions. For complete key replacement, see `CHANGE_KEY`.

---

## `CHANGE_KEY_TEXT`

Dynamically changes the text displayed on the currently pressed key.

**Formats:**
```yaml
# Simple format (white text on black background)
- "CHANGE_KEY_TEXT": "New Text"

# Advanced format with styling
- "CHANGE_KEY_TEXT":
    text: "Custom"
    text_color: "#00FF00"        # Hex color or name
    background_color: "black"    # Hex color or name
    font_size: 24                # Font size in points
    bold: true                   # Bold text (default: true)
```

**Examples:**
```yaml
# Simple text change
- "CHANGE_KEY_TEXT": "Active"

# Colored text
- "CHANGE_KEY_TEXT":
    text: "REC"
    text_color: "red"
    background_color: "black"
    font_size: 28
    bold: true

# Counter display
- "CHANGE_KEY_TEXT":
    text: "Count: 5"
    text_color: "white"
    background_color: "#2c3e50"
    font_size: 18
```

**Parameters:**
- `text` (required): Text to display
- `text_color` (optional): Color name or hex code (default: `"white"`)
- `background_color` (optional): Color name or hex code (default: `"black"`)
- `font_size` (optional): Font size in points (default: `20`)
- `bold` (optional): Bold text (default: `true`)

**Color Formats:**
- Named colors: `"white"`, `"black"`, `"red"`, `"green"`, `"blue"`, etc.
- Hex colors: `"#FF0000"`, `"#00FF00"`, `"#0000FF"`, etc.

**Implementation:**
- Generates a 112x112 pixel PNG image with the text
- Temporarily saves image and loads it to the key
- Automatically cleans up temporary file after 0.5s

**Use Cases:**
- Display counters or timers
- Show status information
- Create text-based toggles
- Display dynamic values

**Note:** Multi-line text is supported using `\n`:
```yaml
- "CHANGE_KEY_TEXT":
    text: "Line 1\nLine 2"
    font_size: 16
```

---

## `CHANGE_KEY`

Replaces the entire key configuration (image and actions) with a different key definition from the `keys` section. This allows dynamic key transformations, such as switching a button between different states or modes.

**Formats:**
```yaml
# Simple format (most common)
- "CHANGE_KEY": "KeyName"

# Advanced format with options (for future extensions)
- "CHANGE_KEY":
    key_name: "KeyName"
```

**Parameters:**
- `key_name` (required): Name of the key definition to switch to (must be defined in `keys` section)

**Examples:**

**Example 1: Screenshot with Cancel**
```yaml
keys:
  PrintScreenKey:
    icon: "img/screen_capture.png"
    on_press_actions:
      - KEY_PRESS: "META+SHIFT+P"        # Trigger screenshot tool
      - WAIT: 1.5                         # Wait for tool to be ready
      - CHANGE_KEY: CancelPrintScreenKey  # Change to cancel button
  
  CancelPrintScreenKey:
    icon: "img/screen_capture_abort.png"
    on_press_actions:
      - KEY_PRESS: "Esc"                 # Cancel screenshot
      - CHANGE_KEY: PrintScreenKey       # Change back to screenshot button

layouts:
  Main:
    Default: true
    keys:
      - 11: PrintScreenKey  # Only PrintScreenKey is initially visible
```

**Example 2: Record/Stop Toggle**
```yaml
keys:
  RecordKey:
    icon: "img/record.png"
    on_press_actions:
      - EXECUTE_COMMAND: "obs-studio --start-recording"
      - CHANGE_KEY: StopRecordKey
  
  StopRecordKey:
    icon: "img/stop.png"
    on_press_actions:
      - EXECUTE_COMMAND: "obs-studio --stop-recording"
      - CHANGE_KEY: RecordKey

layouts:
  Main:
    Default: true
    keys:
      - 5: RecordKey
```

**Example 3: Multi-State Button**
```yaml
keys:
  State1Key:
    text: "State 1"
    on_press_actions:
      - TYPE_TEXT: "First state activated"
      - CHANGE_KEY: State2Key
  
  State2Key:
    text: "State 2"
    on_press_actions:
      - TYPE_TEXT: "Second state activated"
      - CHANGE_KEY: State3Key
  
  State3Key:
    text: "State 3"
    on_press_actions:
      - TYPE_TEXT: "Third state activated"
      - CHANGE_KEY: State1Key  # Cycle back to first state

layouts:
  Main:
    Default: true
    keys:
      - 1: State1Key  # Only State1Key is initially visible
```

**Behavior:**
- Updates the pressed key's image to the target key's image
- Replaces the pressed key's callbacks (on_press, on_release, on_double_press) with the target key's callbacks
- The target key does **not** need to be in any layout initially - it can be a "hidden" key definition
- Works on the physical button that was pressed, regardless of the target key's original position
- Changes take effect immediately
- Device display is refreshed automatically

**Important Notes:**
- The target key name must exist in the `keys` section, or a validation error will occur
- The target key does NOT need to be assigned to a physical button in any layout
- This enables creating "state machine" buttons that cycle through different configurations
- For simple image-only changes, consider `CHANGE_KEY_IMAGE` instead
- For text-only changes, consider `CHANGE_KEY_TEXT` instead

**Use Cases:**
- **State toggles**: Record/Stop, Play/Pause, On/Off
- **Modal buttons**: Different actions in different modes (e.g., screenshot → cancel screenshot)
- **Progressive actions**: Multi-step workflows where the button changes after each step
- **Dynamic UI**: Buttons that adapt based on context or application state

**Comparison with Similar Actions:**
- `CHANGE_KEY_IMAGE`: Only changes the icon, keeps the same actions
- `CHANGE_KEY_TEXT`: Only changes the text display, keeps the same actions  
- `CHANGE_KEY`: Replaces both image AND all actions (complete key replacement)
- `CHANGE_LAYOUT`: Switches the entire device to different layout (all 15 keys)



---

## `CHANGE_LAYOUT`

Switches the entire device to a different predefined layout.

**Formats:**
```yaml
# Simple format
- "CHANGE_LAYOUT": "LayoutName"

# Advanced format with options
- "CHANGE_LAYOUT":
    layout: "LayoutName"
    clear_all: true  # Optional: clear all keys before switching
```

**Parameters:**
- `layout` (required): Name of the layout to switch to (must be defined in `layouts` section)
- `clear_all` (optional): If `true`, clears all keys before applying new layout (default: `false`)

**Examples:**
```yaml
# Switch to media control layout
- "CHANGE_LAYOUT": "Media"

# Switch to gaming layout with clean transition
- "CHANGE_LAYOUT":
    layout: "Gaming"
    clear_all: true

# Return to main layout
- "CHANGE_LAYOUT": "Main"
```

**Behavior:**
- Immediately applies all keys from the target layout
- Updates all key images and callbacks
- Refreshes device display
- If `clear_all: true`, clears all 15 keys before applying new layout
- Layout's own `clear_all` setting is also respected

**Use Cases:**
- Switch between different control schemes (Main, Media, Gaming, Work)
- Context-specific key configurations
- Multi-page layouts
- Application-specific controls

**Example Configuration:**
```yaml
layouts:
  Main:
    Default: true
    keys:
      - 1: HomeKey
      - 2: MediaLayoutKey  # Key that switches to Media layout
  
  Media:
    keys:
      - 1: PlayPauseKey
      - 2: NextTrackKey
      - 15: BackToMainKey  # Key that returns to Main layout

keys:
  MediaLayoutKey:
    text: "Media"
    on_press_actions:
      - "CHANGE_LAYOUT": "Media"
  
  BackToMainKey:
    text: "Back"
    on_press_actions:
      - "CHANGE_LAYOUT": "Main"
```

---

## `DBUS`

Sends D-Bus commands for controlling media players, system volume, and other D-Bus services.

**Formats:**
```yaml
# Using predefined shortcuts
- "DBUS": {"action": "shortcut_name"}

# Custom D-Bus command string
- "DBUS": "dbus-send --dest=... --path=... method"
```

**Predefined Shortcuts:**

| Shortcut | Description | Implementation |
|----------|-------------|----------------|
| `play_pause` | Toggle play/pause (Spotify) | MPRIS MediaPlayer2 interface |
| `play_pause_any` | Toggle play/pause (any MPRIS player) | Detects first available MPRIS player |
| `next` | Next track (Spotify) | MPRIS MediaPlayer2 interface |
| `previous` | Previous track (Spotify) | MPRIS MediaPlayer2 interface |
| `stop` | Stop playback (Spotify) | MPRIS MediaPlayer2 interface |
| `volume_up` | Increase volume by 5% | PulseAudio/PipeWire via `pactl` |
| `volume_down` | Decrease volume by 5% | PulseAudio/PipeWire via `pactl` |
| `mute` | Toggle mute | PulseAudio/PipeWire via `pactl` |

**Examples:**
```yaml
# Media controls
- "DBUS": {"action": "play_pause"}
- "DBUS": {"action": "next"}
- "DBUS": {"action": "previous"}

# Volume controls
- "DBUS": {"action": "volume_up"}
- "DBUS": {"action": "volume_down"}
- "DBUS": {"action": "mute"}

# Custom D-Bus command
- "DBUS": "dbus-send --print-reply --dest=org.freedesktop.Notifications /org/freedesktop/Notifications org.freedesktop.Notifications.GetCapabilities"
```

**Requirements:**
- `dbus-send` - For D-Bus commands
- `pactl` - For volume controls (PulseAudio/PipeWire)

**MPRIS Support:**
- Works with any MPRIS2-compatible media player
- Predefined shortcuts target Spotify by default
- Use `play_pause_any` to target any running media player

**Supported Media Players:**
- Spotify
- VLC
- Chrome/Chromium (when playing media)
- Firefox (when playing media)
- Rhythmbox
- Clementine
- Any MPRIS2-compatible player

---

## `DEVICE_BRIGHTNESS`

Adjusts the StreamDock device's LED brightness.

**Formats:**
```yaml
# Increase brightness by 10%
- "DEVICE_BRIGHTNESS_UP": ""

# Decrease brightness by 10%
- "DEVICE_BRIGHTNESS_DOWN": ""
```

**Behavior:**
- Each press adjusts brightness by 10%
- Brightness range: 0-100%
- Current brightness is stored on the device object
- Changes are immediately visible

**Examples:**
```yaml
# Brightness up key
BrightnessUp:
  text: "🔆"
  on_press_actions:
    - "DEVICE_BRIGHTNESS_UP": ""

# Brightness down key
BrightnessDown:
  text: "🔅"
  on_press_actions:
    - "DEVICE_BRIGHTNESS_DOWN": ""
```

**Note:** The parameter value is ignored (can be empty string or null).

---

## Chaining Multiple Actions

Actions in a list are executed sequentially, allowing you to create powerful macros and automated workflows.

**Example: Copy and Paste**
```yaml
on_press_actions:
  - "KEY_PRESS": "CTRL+C"
  - "WAIT": 0.1
  - "KEY_PRESS": "CTRL+V"
```

**Example: SSH Login**
```yaml
on_press_actions:
  - "LAUNCH_APPLICATION": "konsole"
  - "WAIT": 1.5  # Wait for terminal to open
  - "TYPE_TEXT": "ssh user@server.com"
  - "KEY_PRESS": "RETURN"
  - "WAIT": 2.0  # Wait for password prompt
  - "TYPE_TEXT": "password123"  # Not recommended - use SSH keys!
  - "KEY_PRESS": "RETURN"
```

**Example: Toggle with Visual Feedback**
```yaml
PlayKey:
  icon: "./img/play.png"
  on_press_actions:
    - "KEY_PRESS": "SPACE"  # Toggle playback
    - "CHANGE_KEY_IMAGE": "./img/pause.png"  # Update icon

PauseKey:
  icon: "./img/pause.png"
  on_press_actions:
    - "KEY_PRESS": "SPACE"  # Toggle playback
    - "CHANGE_KEY_IMAGE": "./img/play.png"  # Update icon
```

**Example: Multi-Step Workflow**
```yaml
on_press_actions:
  - "LAUNCH_APPLICATION": "code"
  - "WAIT": 2.0
  - "KEY_PRESS": "CTRL+K CTRL+O"  # Open folder in VS Code
  - "WAIT": 0.5
  - "TYPE_TEXT": "/home/user/projects/myproject"
  - "KEY_PRESS": "RETURN"
```

**Best Practices:**
- Use `WAIT` between actions that depend on previous actions completing
- Keep macros focused on a single task
- Test timing values - they may vary based on system performance
- Use `LAUNCH_APPLICATION` instead of `EXECUTE_COMMAND` for GUI apps
- Combine `CHANGE_KEY_IMAGE` or `CHANGE_KEY_TEXT` with actions for visual feedback

---

## Platform Compatibility

### Wayland Support
- **KDE Plasma**: Full support via `kdotool`
- **GNOME**: Limited support (VirtualKeyboard via `/dev/uinput`)
- **Other compositors**: VirtualKeyboard support where available

### X11 Support
- Full support via `xdotool`
- All actions work as expected

### Required Tools
- **VirtualKeyboard**: `/dev/uinput` access (preferred method)
- **kdotool**: For Wayland/KDE (install via package manager)
- **xdotool**: For X11 (install via package manager)
- **wmctrl**: Optional fallback for window management
- **dbus-send**: For D-Bus actions
- **pactl**: For volume controls

---

## Action Execution Order

Actions are executed in the order they appear in the list:

```yaml
on_press_actions:
  - "ACTION_1": "param1"  # Executes first
  - "ACTION_2": "param2"  # Executes second
  - "ACTION_3": "param3"  # Executes third
```

Each action completes before the next one starts, except for:
- `EXECUTE_COMMAND` - Launches in background, doesn't block
- `LAUNCH_APPLICATION` - Launches in background, doesn't block

Use `WAIT` to add delays when needed.

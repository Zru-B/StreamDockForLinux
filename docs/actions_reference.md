# Actions Reference

This document details all available actions you can assign to keys in your `config.yml`.

## EXECUTE_COMMAND
Run a shell command in a detached process.

```yaml
- "EXECUTE_COMMAND": ["firefox"]
- "EXECUTE_COMMAND": ["dolphin", "/home"]
```
*   **Behavior:** Runs in background using `nohup`. Output is discarded. Independent of the StreamDock process.

---

## LAUNCH_APPLICATION
Smart launcher: launches if closed, focuses if open.

**Simple String:**
```yaml
- "LAUNCH_APPLICATION": "firefox"
```

**Desktop File (Recommended):**
```yaml
- "LAUNCH_APPLICATION":
    desktop_file: "org.kde.kate.desktop"  # Searches /usr/share/applications/
```

**Advanced:**
```yaml
- "LAUNCH_APPLICATION":
    command: ["firefox", "--new-window"]
    class_name: "firefox"          # Class to search for
    match_type: "contains"         # "contains" or "exact"
    force_new: true                # Ignore existing windows, always launch new
```

---

## KEY_PRESS
Simulate keyboard shortcuts.

```yaml
- "KEY_PRESS": "CTRL+C"
- "KEY_PRESS": "CTRL+ALT+T"
- "KEY_PRESS": "SUPER+L"
```
*   **Modifiers:** CTRL, ALT, SHIFT, SUPER

---

## TYPE_TEXT
Type a string of text.

```yaml
- "TYPE_TEXT": "user@example.com"
- "TYPE_TEXT": "MySecurePassword123"
```

---

## CHANGE_LAYOUT
Switch the active layout.

**Simple:**
```yaml
- "CHANGE_LAYOUT": "Media_Layout"
```

**With Options:**
```yaml
- "CHANGE_LAYOUT":
    layout: "Settings_Layout"
    clear_all: true  # Wipes screen before switching
```

---

## DBUS (Media Control)
Send MPRIS media commands to **any active media player** (Spotify, VLC, Rhythmbox, etc.).
The player is discovered dynamically at press time via the D-Bus session bus. If no media player is running, the action is a silent no-op.

```yaml
- "DBUS": {"action": "play_pause"}  # Toggle play/pause
- "DBUS": {"action": "next"}        # Skip to next track
- "DBUS": {"action": "previous"}    # Go to previous track
- "DBUS": {"action": "stop"}        # Stop playback
- "DBUS": {"action": "volume_up"}   # System volume +5%
- "DBUS": {"action": "volume_down"} # System volume -5%
- "DBUS": {"action": "mute"}        # Toggle system mute
```

---

## DEVICE_BRIGHTNESS
Adjust the StreamDock's screen brightness.

```yaml
- "DEVICE_BRIGHTNESS_UP": ""    # +10%
- "DEVICE_BRIGHTNESS_DOWN": ""  # -10%
```

---

## CHANGE_KEY_IMAGE
Dynamically update the icon of the current key.

```yaml
- "CHANGE_KEY_IMAGE": "../img/mute_on.png"
```

---

## CHANGE_KEY_TEXT
Dynamically update the text label of the current key. Supports overlays if an icon is specified.

**Simple String:**
```yaml
- "CHANGE_KEY_TEXT": "Muted"
```

**Advanced (Overlay):**
```yaml
- "CHANGE_KEY_TEXT":
    text: "Muted"
    text_color: "red"
    icon: "../img/mute_on.png"      # Optional overlay
    text_position: "bottom"         # Optional
```

---

## WAIT
Pause execution sequence (useful for multi-step macros).

```yaml
- "WAIT": 0.5  # Wait 0.5 seconds
```

## Chaining Actions
You can list multiple actions to create a macro:

```yaml
on_press_actions:
  - "TYPE_TEXT": "git status"
  - "KEY_PRESS": "RETURN"
  - "WAIT": 1.0
  - "TYPE_TEXT": "git pull"
```

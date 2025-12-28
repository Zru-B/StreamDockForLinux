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
Send standard Linux MPRIS media commands.

```yaml
- "DBUS": {"action": "play_pause"}
- "DBUS": {"action": "next"}
- "DBUS": {"action": "previous"}
- "DBUS": {"action": "volume_up"}
- "DBUS": {"action": "volume_down"}
- "DBUS": {"action": "mute"}
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

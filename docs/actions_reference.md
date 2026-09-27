# Actions Reference

This document details all available actions you can assign to keys in your `config.yml`.

Each entry in an action list is a mapping of one action name to its parameter,
like `- KEY_PRESS: "CTRL+C"`. A bare name (`- KEY_PRESS`) is rejected, as is an
empty action list. Action names are matched case-insensitively (`key_press`
works too), and each parameter is checked when the configuration loads, so a
wrong one is reported instead of silently doing nothing when the key is pressed.

## EXECUTE_COMMAND
Run a shell command in a detached process.

```yaml
- "EXECUTE_COMMAND": "firefox"
- "EXECUTE_COMMAND": "dolphin /home"
```
*   **Parameter:** a non-empty shell command line (a string, not a list).
*   **Behavior:** Runs in the background through the shell. Output is discarded. Independent of the StreamDock process.

---

## LAUNCH_APPLICATION
Smart launcher: launches if closed, focuses if open.

**Simple String:**
```yaml
- "LAUNCH_APPLICATION": "firefox"
- "LAUNCH_APPLICATION": "code --new-window"
```
A string is split like a shell command line into the program and its arguments;
the process and window class looked for are the program's file name
(`code` above).

**Desktop File (Recommended):**
```yaml
- "LAUNCH_APPLICATION":
    desktop_file: "org.kde.kate.desktop"  # Searches /usr/share/applications/
```

**Advanced:**
```yaml
- "LAUNCH_APPLICATION":
    command: ["firefox", "--new-window"]   # or a string: "firefox --new-window"
    class_name: "firefox"          # Class to search for
    match_type: "contains"         # "contains" or "exact"
    force_new: true                # Ignore existing windows, always launch new
```
*   **match_type:** `contains` (default) accepts any window whose class contains
    `class_name`; `exact` only one whose class equals it, ignoring case. With `exact`,
    a window whose class merely contains the name is not used, and the application
    is launched instead.

---

## KEY_PRESS
Simulate keyboard shortcuts.

```yaml
- "KEY_PRESS": "CTRL+C"
- "KEY_PRESS": "CTRL+ALT+T"
- "KEY_PRESS": "SUPER+L"
```
*   **Modifiers:** CTRL, ALT, SHIFT, SUPER
*   **The plus key:** write it as a trailing `+` after the separator, e.g. `"CTRL++"` (zoom in).
*   **Other keys:** any X keysym name (e.g. `XF86AudioPlay`, `KP_Add`) is passed to `xdotool`
    as written; keysyms are case-sensitive.

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

The layout must exist in `layouts`.

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

A string instead of a mapping is run as a shell command (for a raw `dbus-send`);
its output is discarded and it is stopped after 5 seconds.

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
*   Relative paths are resolved against the directory holding the config file, like key icons, and the file must exist.

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
    icon: "../img/mute_on.png"      # Optional overlay, resolved like CHANGE_KEY_IMAGE
    text_position: "bottom"         # Optional
```

---

## CHANGE_KEY
Replace the current key with another key from `keys`: its image or text and all of its actions.

```yaml
- "CHANGE_KEY": "Mic_Muted"   # the name of a key defined under keys
```
*   For older configurations, a value that is not a key name is taken as an image path and only changes the picture.

---

## WAIT
Pause execution sequence (useful for multi-step macros).

```yaml
- "WAIT": 0.5  # Wait 0.5 seconds
```
*   **Parameter:** a number of seconds, 0 or more.
*   If a WAIT fails, the remaining actions in the list are skipped: they usually depend on the pause.
*   Key actions run on 4 shared workers, and a waiting macro occupies one of them for the
    whole pause. Several long WAITs running at once delay other keys until one finishes.

## Chaining Actions
You can list multiple actions to create a macro:

```yaml
on_press_actions:
  - "TYPE_TEXT": "git status"
  - "KEY_PRESS": "RETURN"
  - "WAIT": 1.0
  - "TYPE_TEXT": "git pull"
```

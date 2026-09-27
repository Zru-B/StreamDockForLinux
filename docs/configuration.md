# Configuration Guide

StreamDock uses a YAML configuration file (`config.yml`) to define global settings, keys, layouts, and window rules.

## Basic Structure

```yaml
streamdock:
  settings:
    # Global device settings
    brightness: 15
  
  keys:
    # Key definitions
    MyKey:
      icon: "../img/icon.png"
      on_press_actions: [...]
  
  layouts:
    # Layout definitions
    Main:
      Default: true
      keys:
        - 1: "MyKey"
  
  windows_rules:
    # Automatic layout switching
    Firefox_Rule:
      window_name: "Firefox"
      layout: "Main"
```

---

## Settings

Optional global settings for the application.

```yaml
settings:
  brightness: 15                   # Device brightness (0-100), default: 50
  lock_monitor: true               # Auto turn off when computer locked, default: true
  lock_verification_delay: 2.0     # Seconds to wait before confirming lock, default: 2.0
  double_press_interval: 0.3       # Time window in seconds for double-press detection
  long_press_duration: 0.5         # Seconds a key must be held to count as a long press
```

- **brightness:** Controls the LED brightness of the device.
- **lock_monitor:** Requires `dbus-python`. Turns off screen when system is locked.
- **lock_verification_delay:** Time to wait before confirming a lock event (0.1-30s). Prevents false lock detection when user aborts lock screen. Higher values are more reliable but slower to respond.
- **double_press_interval:** Valid range 0.1-2.0s. Lower is faster but harder to trigger.
- **long_press_duration:** Valid range 0.1-5.0s. Only affects keys that have `on_long_press_actions`.

Both timings can also be changed in the editor under **Advanced Settings**.

---

## Keys

Keys are the building blocks. They are defined once and can be reused in multiple layouts.

### Image-Based Keys

```yaml
keys:
  Firefox:
    icon: "../img/firefox.png"      # Supports: PNG, JPG, GIF, SVG
    on_press_actions:
      - "EXECUTE_COMMAND": ["firefox"]
```

### Text-Based & Hybrid Keys

Keys can display an icon, text, or both. If both are provided, the text is layered on top of the icon.

```yaml
keys:
  Settings:
    icon: "../img/settings.png"      # Optional
    text: "Settings"                # Optional
    text_color: "white"             # Optional (color name or hex)
    background_color: "black"       # Optional (text-only background, or behind a transparent icon)
    font_size: 20                   # Optional (pixels)
    bold: true                      # Optional
    text_position: "bottom"         # Optional: "top", "center", "bottom" (default: bottom)
    on_press_actions:
      - "EXECUTE_COMMAND": ["systemsettings"]
```

With both `icon` and `text`, the icon fills the key and the text is drawn over it:
`text`, `text_position`, `text_color`, `font_size` and `bold` all apply, and
`background_color` shows through transparent parts of the icon. With `text` alone
the text is always centred on `background_color`, and `text_position` has no effect.

> **Note:** If an icon is present, `text_position: "bottom"` is usually recommended to avoid obscuring the main image.

### Widget Keys

A widget key draws itself at runtime: a clock, the date, CPU load, the microphone's mute state. Use `widget` instead of `icon` or `text`:

```yaml
keys:
  Clock:
    widget: digital_clock
    widget_options:
      format: 12h
```

A widget key needs no actions, but can have any of them. It can also show your own images per state (`state_icons`), or a base `icon` with the widget's badge (an unread count, say) in a corner:

```yaml
keys:
  Slack:
    widget: slack_notifications
    icon: img/slack.png
    badge: { position: top_right }
```

See [Widgets](widgets.md) for the built-in widgets, their states and badges, and installing or writing your own.

### Action Triggers

Keys support four trigger types:

```yaml
MyKey:
  icon: "icon.png"
  on_press_actions:         # Triggered immediately on press
    - "TYPE_TEXT": "Pressed"
  on_release_actions:       # Triggered when released
    - "TYPE_TEXT": "Released"
  on_double_press_actions:  # Triggered on double-click
    - "KEY_PRESS": "CTRL+C"
  on_long_press_actions:    # Triggered once the key is held for long_press_duration
    - "KEY_PRESS": "CTRL+V"
```

Adding a double-press or long-press trigger changes when the other triggers run, because
the key has to wait to find out which gesture it is:

- **Double press:** the press and release actions are delayed by `double_press_interval`.
  If a second press arrives within that window after the release, only the double-press
  actions run.
- **Long press:** the press actions run when the key is released, not when it goes down,
  and only if it was released before `long_press_duration`. If the key is held that long,
  the long-press actions run while it is still down, and releasing it runs nothing.
- **Both:** a tap waits out the double-press window and then runs press followed by release.
  A hold runs the long press, and a double tap runs the double press.

Keys with only press and release actions are unaffected and still fire immediately.

Every action list you include must hold at least one action, and each action is a
mapping of one action name to its parameter (`- KEY_PRESS: "CTRL+C"`, not a bare
`- KEY_PRESS`). Action names are case-insensitive. Parameters are checked when the
configuration loads: for example `WAIT` needs a number of seconds, `CHANGE_LAYOUT` an
existing layout, and `CHANGE_KEY` the name of another key.

For a list of all available actions, see the [Actions Reference](actions_reference.md).

---

## Layouts

Layouts map your **Keys** to physical buttons on the device (1-15).

**Rules:**
1. You must define at least one layout.
2. Exactly one layout must have `Default: true`.

```yaml
layouts:
  Main:
    Default: true           # This is the starting layout
    keys:
      - 1: "Firefox"
      - 2: "Chrome"
      - 3: "Spotify"
      - 4: null             # Explicitly empty key
      - 15: "NextPage"
  
  Media:
    clear_all: true         # Clear old icons when switching to this layout
    keys:
      - 1: "PlayPause"
      - 2: "NextTrack"
```

- **Key numbers:** 1-15 (Top-left to Bottom-right).
- **Empty keys:** Use `null` or `~` to clear a key: when the layout is applied, that button is blanked and its actions from the previous layout are removed.
- **clear_all:** If `true`, wipes the screen before drawing this layout. Useful for clean transitions.

---

## Window Rules

Automatically switch layouts based on the active window.

```yaml
windows_rules:
  Firefox_Rule:
    window_name: "Firefox"      # Single string pattern
    layout: "Browser_Layout"    # Layout to activate
    match_field: "class"        # Field to match against

  Browsers_List_Rule:
    window_name:                # List of strings
      - "Firefox"
      - "Chromium"
      - "Vivaldi"
    layout: "Browser_Layout"

  Browser_Regex_Rule:
    window_name: "^Chrom.*"     # Single regex pattern
    is_regex: true              # Treat patterns as regex (default: false)
    layout: "Chrome_Layout"

  Browser_List_Regex_Rule:
    window_name:                # List of strings and regex patterns
      - "^Chrom.*"
      - "^Vivaldi.*"
      - "Firefox"
    is_regex: true              # Treat list items as regex (default: false)
    layout: "Browser_Layout"
```

> **Note:** When `is_regex` is `true`, all items in the list are compiled as case-insensitive regex pattern. Simple strings (e.g., `"Firefox"`) will still work as expected (matching anywhere in the target field), essentially behaving like a substring match.

**Match fields:**
- `class` (default): Application class name (e.g., `firefox`, `Code`).
- `title`: Window title bar text.
- `raw`: Raw window info string.

**Order:** the first matching rule wins. Rules are tried by `priority`
(optional whole number, higher first, default `0`; anything else is rejected), then in the order they appear
in the file. The editor's Window Rules panel lists them in that order; dragging
a rule to a new place rewrites the file order and clears `priority`.

**Requirements:**
- **X11:** `xdotool`
- **Wayland/KDE:** `kdotool` or KWin scripting.

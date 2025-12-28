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
  brightness: 15                # Device brightness (0-100), default: 50
  lock_monitor: true            # Auto turn off when computer locked, default: true
  double_press_interval: 0.3    # Time window in seconds for double-press detection
```

- **brightness:** Controls the LED brightness of the device.
- **lock_monitor:** Requires `dbus-python`. Turns off screen when system is locked.
- **double_press_interval:** Valid range 0.1-2.0s. Lower is faster but harder to trigger.

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

### Text-Based Keys

Useful if you don't have an icon.

```yaml
keys:
  Settings:
    text: "Settings"                # Required
    text_color: "white"             # Optional (color name or hex)
    background_color: "black"       # Optional
    font_size: 20                   # Optional (pixels)
    bold: true                      # Optional
    on_press_actions:
      - "EXECUTE_COMMAND": ["systemsettings"]
```

> **Note:** A key must have either `icon` OR `text`, not both.

### Action Triggers

Keys support three trigger types:

```yaml
MyKey:
  icon: "icon.png"
  on_press_actions:         # Triggered immediately on press
    - "TYPE_TEXT": "Pressed"
  on_release_actions:       # Triggered when released
    - "TYPE_TEXT": "Released"
  on_double_press_actions:  # Triggered on double-click
    - "KEY_PRESS": "CTRL+C"
```

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
- **Empty keys:** Use `null` or `~` to clear a key.
- **clear_all:** If `true`, wipes the screen before drawing this layout. Useful for clean transitions.

---

## Window Rules

Automatically switch layouts based on the active window.

```yaml
windows_rules:
  Firefox_Rule:
    window_name: "Firefox"      # Pattern to match
    layout: "Browser_Layout"    # Layout to activate
    match_field: "class"        # Field to match against
```

**Match fields:**
- `class` (default): Application class name (e.g., `firefox`, `Code`).
- `title`: Window title bar text.
- `raw`: Raw window info string.

**Requirements:**
- **X11:** `xdotool`
- **Wayland/KDE:** `kdotool` or KWin scripting.

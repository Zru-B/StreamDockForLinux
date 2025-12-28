# Recipe: The Productivity Powerhouse

This advanced recipe demonstrates **Context-Aware Layouts**. The StreamDock will automatically change its keys based on which application you are currently using.

## Config

```yaml
streamdock:
  keys:
    # --- Navigation Keys ---
    ToMedia:
      text: "Media ->"
      on_press_actions:
        - "CHANGE_LAYOUT": "Media_Layout"
    
    ToMain:
      text: "<- Back"
      on_press_actions:
        - "CHANGE_LAYOUT": "Main"

    # --- Browser Keys ---
    NewTab:
      text: "New Tab"
      on_press_actions:
        - "KEY_PRESS": "CTRL+T"
    
    ReopenTab:
      text: "Reopen"
      on_press_actions:
        - "KEY_PRESS": "CTRL+SHIFT+T"

    # --- Spotify Keys ---
    LikeSong:
      icon: "../img/heart.png"
      on_press_actions:
        - "KEY_PRESS": "ALT+SHIFT+B" # Spotify shortcut for Like

  layouts:
    # 1. The Default Layout
    Main:
      Default: true
      keys:
        - 1: "Firefox" # Assumed defined elsewhere
        - 15: "ToMedia" # Manual switch button

    # 2. Browser Specific Layout
    Browser_Layout:
      keys:
        - 1: "NewTab"
        - 2: "ReopenTab"
        - 15: "ToMain"

    # 3. Media Specific Layout
    Media_Layout:
      keys:
        - 1: "PlayPause" # Assumed defined
        - 2: "LikeSong"
        - 15: "ToMain"

  # --- The Magic: Auto-Switching Rules ---
  windows_rules:
    # If Firefox is focused, show Browser layout
    Firefox_Rule:
      window_name: "Firefox"
      layout: "Browser_Layout"
      match_field: "class"
    
    # If Spotify is focused, show Media layout
    Spotify_Rule:
      window_name: "Spotify"
      layout: "Media_Layout"
      match_field: "class"
```

## How it works
1.  **Window Rules:** The `windows_rules` section monitors the active window.
2.  **Auto-Switching:**
    *   Focus **Firefox** -> Device switches to `Browser_Layout` (showing tab controls).
    *   Focus **Spotify** -> Device switches to `Media_Layout` (showing playback/like controls).
    *   Focus anything else -> Device stays on the last active layout (or you can set a default fallback).
3.  **Manual Overrides:** The `ToMain` and `ToMedia` keys allow you to force a layout change manually, which is useful if you want to control music while coding (without focusing Spotify).

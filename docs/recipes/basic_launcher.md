# Recipe: The Basic App Launcher

This is the simplest configuration to get started. It creates a main menu with a few common applications.

## Config

```yaml
streamdock:
  settings:
    brightness: 30
  
  keys:
    # --- Browsers ---
    Firefox:
      icon: "../img/firefox.png"
      on_press_actions:
        - "LAUNCH_APPLICATION": "firefox"
    
    Chrome:
      icon: "../img/chrome.png"
      on_press_actions:
        - "LAUNCH_APPLICATION": "google-chrome-stable"

    # --- Terminals ---
    Terminal:
      icon: "../img/terminal.png"
      on_press_actions:
        - "LAUNCH_APPLICATION": "konsole"
    
    # --- System ---
    Files:
      icon: "../img/folder.png"
      on_press_actions:
        - "LAUNCH_APPLICATION": "dolphin"

  layouts:
    Main:
      Default: true
      keys:
        - 1: "Firefox"
        - 2: "Chrome"
        - 3: null
        - 4: "Terminal"
        - 5: "Files"
```

## How it works
- Uses `LAUNCH_APPLICATION` which is smarter than `EXECUTE_COMMAND`. It will focus the window if it's already open, preventing clutter.
- `brightness: 30` sets a comfortable default level.
- Keys 1, 2, 4, 5 are mapped. Key 3 is explicitly left empty (`null`).

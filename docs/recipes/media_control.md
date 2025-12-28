# Recipe: Media Control Deck

A dedicated layout for controlling music and volume.

## Config

```yaml
streamdock:
  keys:
    # --- Controls ---
    PlayPause:
      icon: "../img/play.png"
      on_press_actions:
        - "DBUS": {"action": "play_pause"}
    
    NextTrack:
      icon: "../img/next.png"
      on_press_actions:
        - "DBUS": {"action": "next"}
        
    PrevTrack:
      icon: "../img/prev.png"
      on_press_actions:
        - "DBUS": {"action": "previous"}

    # --- Volume (Text Keys) ---
    VolUp:
      text: "Vol +"
      text_color: "#00FF00" # Green
      font_size: 25
      on_press_actions:
        - "DBUS": {"action": "volume_up"}
    
    VolDown:
      text: "Vol -"
      text_color: "#FF0000" # Red
      font_size: 25
      on_press_actions:
        - "DBUS": {"action": "volume_down"}
    
    Mute:
      text: "MUTE"
      background_color: "#333333"
      on_press_actions:
        - "DBUS": {"action": "mute"}

  layouts:
    MediaLayout:
      Default: true
      keys:
        - 1: "VolDown"
        - 2: "Mute"
        - 3: "VolUp"
        - 6: "PrevTrack"
        - 7: "PlayPause"
        - 8: "NextTrack"
```

## How it works
- Uses the `DBUS` action type to send standard Linux MPRIS commands. This works with Spotify, VLC, YouTube Music (desktop), and system volume.
- Demonstrates **Text Keys** (`VolUp`, `VolDown`) for when you don't have an icon handy.
- Uses `text_color` and `background_color` for styling.

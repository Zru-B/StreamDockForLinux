# Examples

Complete configurations to copy from. Icon paths are relative to the
configuration file; swap in your own images, or use `text:` keys instead.
[Configuration](configuration.md) covers every field, and the
[Actions Reference](actions_reference.md) every action.

## App launcher

A single layout that starts your usual applications.

```yaml
streamdock:
  settings:
    brightness: 30

  keys:
    Firefox:
      icon: "../img/firefox.png"
      on_press_actions:
        - "LAUNCH_APPLICATION": "firefox"

    Terminal:
      icon: "../img/terminal.png"
      on_press_actions:
        - "LAUNCH_APPLICATION": "konsole"

    Files:
      icon: "../img/folder.png"
      on_press_actions:
        - "LAUNCH_APPLICATION": "dolphin"

    Notes:                      # text-only, no icon needed
      text: "Notes"
      text_color: "white"
      background_color: "#4A90E2"
      font_size: 24
      bold: true
      on_press_actions:
        - "LAUNCH_APPLICATION": "obsidian"

  layouts:
    Main:
      Default: true
      keys:
        - 1: "Firefox"
        - 2: "Terminal"
        - 3: null               # explicitly empty
        - 4: "Files"
        - 5: "Notes"
```

`LAUNCH_APPLICATION` focuses the application's window when it is already
open instead of starting a second copy. A key can also carry an icon *and*
text: add `text:` to an icon key and the label is drawn over the icon, at
`text_position:` (`bottom`, `center` or `top`) with the same `text_color`,
`font_size` and `bold` a text key takes; `background_color` shows through a
transparent icon. The editor offers this as the *Label* field of an icon key.

```yaml
    Browser:
      icon: "../img/firefox.png"
      text: "Web"
      text_position: "bottom"
      on_press_actions:
        - "LAUNCH_APPLICATION": "firefox"
```

## Media controls

Playback and volume through D-Bus.

```yaml
streamdock:
  keys:
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

    VolUp:
      text: "Vol +"
      text_color: "#00FF00"
      font_size: 25
      on_press_actions:
        - "DBUS": {"action": "volume_up"}

    VolDown:
      text: "Vol -"
      text_color: "#FF0000"
      font_size: 25
      on_press_actions:
        - "DBUS": {"action": "volume_down"}

    Mute:
      text: "MUTE"
      background_color: "#333333"
      on_press_actions:
        - "DBUS": {"action": "mute"}

  layouts:
    Media:
      Default: true
      keys:
        - 1: "VolDown"
        - 2: "Mute"
        - 3: "VolUp"
        - 6: "PrevTrack"
        - 7: "PlayPause"
        - 8: "NextTrack"
```

The playback actions go to whichever MPRIS player is playing (then one that
is paused), such as Spotify, VLC or a browser tab; with no player running
the key does nothing. For live keys showing the track or the mute state, see
[Widgets](widgets.md).

## Layouts that follow the focused window

The deck shows browser keys while Firefox is focused, music keys while
Spotify is, and the main layout otherwise.

```yaml
streamdock:
  keys:
    Firefox:
      icon: "../img/firefox.png"
      on_press_actions:
        - "LAUNCH_APPLICATION": "firefox"

    ToMedia:
      text: "Media ->"
      on_press_actions:
        - "CHANGE_LAYOUT": "Media_Layout"

    ToMain:
      text: "<- Back"
      on_press_actions:
        - "CHANGE_LAYOUT": "Main"

    NewTab:
      text: "New Tab"
      on_press_actions:
        - "KEY_PRESS": "CTRL+T"

    ReopenTab:
      text: "Reopen"
      on_press_actions:
        - "KEY_PRESS": "CTRL+SHIFT+T"

    PlayPause:
      icon: "../img/play.png"
      on_press_actions:
        - "DBUS": {"action": "play_pause"}

    LikeSong:
      icon: "../img/heart.png"
      on_press_actions:
        - "KEY_PRESS": "ALT+SHIFT+B"   # Spotify's "Like" shortcut

  layouts:
    Main:
      Default: true
      keys:
        - 1: "Firefox"
        - 15: "ToMedia"

    Browser_Layout:
      keys:
        - 1: "NewTab"
        - 2: "ReopenTab"
        - 15: "ToMain"

    Media_Layout:
      keys:
        - 1: "PlayPause"
        - 2: "LikeSong"
        - 15: "ToMain"

  windows_rules:
    Firefox_Rule:
      window_name: "firefox"
      layout: "Browser_Layout"
      match_field: "class"

    Spotify_Rule:
      window_name: "spotify"
      layout: "Media_Layout"
      match_field: "class"
```

When the focused window matches no rule, the deck returns to the default
layout (`Main`). `ToMedia` and `ToMain` switch by hand - handy for music
controls while another application has focus, until the focus changes again.

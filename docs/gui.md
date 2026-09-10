# The StreamDock Application

Running `python src/main.py` opens one window that both edits your
configuration and drives the device. There is no separate editor and no
restart-to-apply step.

## Connecting

The bar above the key grid lists every Stream Dock currently attached. The
first one is selected automatically, and the application connects to it on
startup when a configuration is loaded.

| Control | What it does |
|---|---|
| Device list | Choose which device to drive. Locked while connected — disconnect to switch. |
| ⟳ | Look for attached devices again after plugging one in. |
| ● | Connection state: grey disconnected, amber connecting, green connected, red error. |
| Connect / Disconnect | Open or release the device. |
| Apply to Device | Send the configuration currently open in the window. |

If the list is empty, check that you are in the `plugdev` group and that the
udev rule is installed — see [Installation](installation.md).

## Plugging and unplugging

The device list keeps itself up to date. Unplug the device you are driving and
the application releases it and says so; plug it back in and it reconnects and
re-applies your configuration on its own. Plug in a device while nothing is
connected and it connects to that one.

Two rules keep this from being surprising:

- Pressing **Disconnect** sticks. Replugging will not undo an explicit
  disconnect — press Connect when you want it back.
- If you picked a specific device from the list, only *that* device is
  reconnected. The application will not silently move to a different dock.

This works through udev, falling back to polling every couple of seconds if
pyudev is unavailable. It applies to `--headless` too, which likewise waits
for a device rather than exiting when none is attached.

## Applying a configuration

**Apply to Device** sends what is in the window, including unsaved edits, so
you can try a change before committing it. Save and Apply are separate: saving
writes the file, applying changes the hardware.

The configuration is validated first, and an invalid one never reaches the
device — the previous configuration keeps running. Saving an invalid
configuration is allowed (via *Save anyway*), because a work-in-progress
config whose icon does not exist yet is still worth keeping.

Applying does not disconnect the device. Keys are re-rendered in place, so
there is a brief flicker rather than the screen going dark.

**Apply is only enabled when it would do something.** After connecting, or
right after an apply, the device already matches what is on screen, so the
button is greyed out. It becomes available again as soon as you edit
something, open a different configuration file, or the device is unplugged and
reconnected. Note that saving does not enable it and applying does not clear
the modified marker in the title bar — writing the file and pushing to the
device stay independent.

## The default configuration

The application opens the same configuration each time. When you open a
different file it asks whether that should become the new default; answering
*No* keeps the current one. Without a stored default it looks for `config.yml`
in the working directory, then next to `main.py`, and otherwise starts empty.

## Appearance

The window follows the desktop it is running on. On Plasma, LXQt and other Qt
sessions it wears **Breeze**: a menu bar along the top, a status bar along the
bottom, tight corners, and — this is the part worth knowing — the colour scheme
you actually chose in *System Settings > Colours*. The accent, the window and
view backgrounds, and the positive, negative and neutral colours are read from
`kdeglobals`, so a custom scheme or a custom accent comes through without the
application knowing anything about it.

On GNOME, Cinnamon, XFCE and other GTK sessions it wears **Adwaita** instead,
and that is a different arrangement rather than a repaint:

| | Plasma (Breeze) | GNOME (Adwaita) |
|---|---|---|
| Commands | Menu bar: File, Keys, Settings | Header bar with Open and Save, everything else under ☰ |
| Messages | Status bar along the bottom | A toast that floats over the content and fades |
| Dialogs | Cancel and the action at the bottom right | Cancel at the header's left, the action at its right |
| Document name | In the window title | Under the title in the header bar |
| Shape | 3px corners, outlined controls | 8–12px corners, filled controls |

Light and dark follow the session too, through the cross-desktop portal that
both Plasma and GNOME publish. Turn on your desktop's night mode and the window
follows it while it is open. Swapping to a different colour scheme entirely, or
changing your accent, is picked up the next time the application starts.

### Choosing for yourself

*Settings > Appearance* overrides both, and the choice is remembered:

- **Design** — *Follow the desktop*, *Plasma (Breeze)*, or *GNOME (Adwaita)*.
- **Colours** — *Follow the desktop*, *Light*, or *Dark*.

Switching either takes effect immediately; there is no restart. Forcing a
design that is not the session's own uses that design's stock colours rather
than the desktop's, since Breeze blue on a GNOME layout belongs to neither.

`--design gnome` forces the design for one run without changing what is
remembered. `STREAMDOCK_QT_STYLE=Breeze` swaps the Qt widget style underneath
the theme, for anything the stylesheet does not paint.

## The system tray

Closing the window hides it in the tray, and the device keeps switching
layouts as you change windows. Click the tray icon to bring the window back.

Use **Quit** — in the tray menu or *File > Exit* — to actually stop: it blanks
the device screen, releases it, and exits. This is the only path that prompts
about unsaved changes.

On desktops with no system tray (GNOME without an AppIndicator extension),
closing the window quits instead, so the application can never become
unreachable.

## Running without a GUI

```bash
python src/main.py --headless
```

Runs the controller alone, importing no Qt at all — useful over SSH or on a
machine with no display. Press Ctrl+C to stop.

## One instance at a time

Only one process can drive the device. A second launch raises the existing
window rather than starting again, and if something else already holds the
device the application says so and lets you keep editing configurations with
connecting disabled.

## Command line

```
streamdock [CONFIG] [--headless] [--minimized] [--device ID] [--design NAME]
           [--check-deps] [--debug]
```

| Option | Effect |
|---|---|
| `CONFIG` | Configuration file to open, overriding the stored default |
| `--headless` | Run the controller with no GUI |
| `--minimized` | Start hidden in the system tray |
| `--device ID` | Connect to a specific device, as shown in the device list |
| `--design NAME` | Force `kde`, `gnome` or `auto` for this run only |
| `--check-deps` | Print a dependency report and exit |
| `--debug` | Verbose logging |

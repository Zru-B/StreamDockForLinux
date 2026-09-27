# Troubleshooting Guide

Common issues and solutions for StreamDock.

## Automated Diagnostics

Before manual troubleshooting, run the automated dependency checker to verify your system and Python environment:

```bash
python3 main.py --check-deps
```

This tool identifies missing system binaries (like `xdotool` or `kdotool`) and Python packages, providing hints on how to resolve them.

## Device Not Found / Permission Denied

**Symptoms:**
- Error: `PermissionError: [Errno 13] Permission denied`
- Application says "No Stream Dock devices found".

**Solutions:**
1.  **Check connection:** `lsusb | grep -i hotspot` (or `mirabox`).
2.  **Verify udev rules:** Ensure you ran `scripts/install.sh` and that
    `/etc/udev/rules.d/70-streamdock.rules` exists (see [Installation](installation.md#device-permissions--launcher-linux)).
    A leftover `99-streamdock.rules` from an older install runs too late for
    its `uaccess` tag to apply on hotplug; rerun the script to replace it.
3.  **Check the ACL:** find the deck with `lsusb -d 6603:1006` (Bus `BBB`
    Device `DDD`) and run `getfacl /dev/bus/usb/BBB/DDD` (and `getfacl /dev/hidrawN`
    for its hidraw nodes). The owner stays `root`; there should be a
    `user:<you>:rw-` entry. It is only granted to a user with an active
    session on the local seat, so it is absent over SSH.
4.  **Reload Rules:** `sudo udevadm control --reload-rules && sudo udevadm trigger`, then replug.

## Mouse Keys / Cursor Issues

**Symptoms:**
- The mouse cursor changes to a **+** sign.
- The numeric keypad moves the mouse pointer.
- Occurs after locking/unlocking the screen.

**Cause:**
The device has multiple HID interfaces. Linux sometimes misinterprets one as a generic keyboard and activates the "Mouse Keys" accessibility feature during device initialization.

**Fix:**
1.  **Stop the system treating the deck as an input device.** Add these lines
    to `/etc/udev/rules.d/70-streamdock.rules` (after the ones
    `scripts/install.sh` put there; rerunning the script overwrites the file,
    so add them again afterwards), then run
    `sudo udevadm control --reload-rules && sudo udevadm trigger` and replug:

    ```udev
    # Keep every interface of the deck away from the input subsystem
    SUBSYSTEMS=="usb", ATTRS{idVendor}=="6603", ATTRS{idProduct}=="1006", ENV{ID_INPUT}="0", ENV{ID_INPUT_KEYBOARD}="0", ENV{ID_INPUT_MOUSE}="0", ENV{ID_INPUT_TABLET}="0", ENV{ID_INPUT_TOUCHPAD}="0", ENV{ID_INPUT_JOYSTICK}="0"
    SUBSYSTEM=="input", ATTRS{idVendor}=="6603", ATTRS{idProduct}=="1006", ENV{ID_INPUT}="0", ENV{LIBINPUT_IGNORE_DEVICE}="1", TAG-="uaccess"
    KERNEL=="event*", ATTRS{idVendor}=="6603", ATTRS{idProduct}=="1006", MODE="0000", GROUP="root"
    # Unbind the generic HID driver so it never becomes a keyboard/mouse
    SUBSYSTEM=="hid", ATTRS{idVendor}=="6603", ATTRS{idProduct}=="1006", RUN+="/bin/sh -c 'echo -n %k > /sys/bus/hid/drivers/hid-generic/unbind || true'"
    ```
2.  **Disable Mouse Keys:**
    *   **KDE:** System Settings → Accessibility → Mouse Navigation → Uncheck "Activate with Shift key".
    *   **GNOME:** Settings → Accessibility → Pointing & Clicking → Turn off "Mouse Keys".

## Lock Monitor Not Working

**Symptoms:**
- Device stays on when screen is locked.
- Device doesn't wake up after unlocking.

**How it works:**
- **On lock:** The device screen is turned off by setting brightness to 0, but the HID connection stays open for fast wake-up.
- **On unlock:** The application first tries to wake the device using the existing connection. If that fails (e.g., USB was reset during sleep), it automatically falls back to fully reopening the device.

**Fix for "device stays on":**
- Ensure D-Bus libraries are installed:
  ```bash
  # Arch
  sudo pacman -S python-dbus python-gobject
  # Ubuntu
  sudo apt install python3-dbus python3-gi
  ```
- Test D-Bus manually:
  ```bash
  dbus-send --session --print-reply --dest=org.freedesktop.ScreenSaver /ScreenSaver org.freedesktop.ScreenSaver.GetActive
  ```

**Fix for "device doesn't wake":**
- Check the application logs for errors during unlock.
- If fallback is consistently failing, ensure udev rules allow device access (see [Installation](installation.md#device-permissions--launcher-linux)).

## Configuration Errors

**"Duplicate key name"**
- Every key under `keys:` must have a unique name.

**"Layout references undefined key"**
- If a layout uses `1: "MyKey"`, ensure `MyKey` is defined in the `keys` section.

**"Icon file not found"**
- Paths are relative to the `config.yml` file location (or the working directory if running from source). Use absolute paths if unsure.


## The application window

### No tray icon appears

GNOME removed built-in tray support; install the **AppIndicator and KStatusNotifierItem Support**
extension. Without a tray, StreamDock deliberately quits when you close the
window instead of hiding somewhere you cannot reach it.

### "Another StreamDock process already controls the device"

Only one process can hold the device: either another window is open or a
`--headless` run is still going. Close the other one and try again.

You can still edit and save configurations while this message is showing;
only connecting is disabled.

### The device is listed but connecting fails

Most often another process already has it open — a `--headless` run or a
second window. The application now says so explicitly rather than reporting a
connection that is not really there.

### Unplugging does not get noticed

Hotplug uses udev via `pyudev`. If it is not installed the application falls
back to polling every couple of seconds, which is slower but still works;
`python src/main.py --check-deps` reports whether `pyudev` is present.

### "Could not load the Qt platform plugin xcb"

The Qt runtime libraries are missing. On Debian/Ubuntu:

```bash
sudo apt install libxcb-cursor0 libxcb-xinerama0
```

On Arch these come with the `qt6-base` package.

### Apply says the configuration is invalid

The same validation the controller applies at startup runs before anything
reaches the device, so the message is the exact reason the device would have
rejected it — most often an icon path that does not exist. Icon paths are
resolved relative to the configuration file's own directory.

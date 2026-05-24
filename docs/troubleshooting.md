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
2.  **Verify udev rules:** Ensure you followed the [Device Setup Guide](device_setup.md).
3.  **Check Group:** Run `groups` and ensure your user is in `plugdev`.
4.  **Reload Rules:** `sudo udevadm control --reload-rules && sudo udevadm trigger`.

## Mouse Keys / Cursor Issues

**Symptoms:**
- The mouse cursor changes to a **+** sign.
- The numeric keypad moves the mouse pointer.
- Occurs after locking/unlocking the screen.

**Cause:**
The device has multiple HID interfaces. Linux sometimes misinterprets one as a generic keyboard and activates the "Mouse Keys" accessibility feature during device initialization.

**Fix:**
1.  **Update udev rules:** The rules provided in the [Device Setup Guide](device_setup.md) include specific directives (`LIBINPUT_IGNORE_DEVICE`, `HID_GENERIC unbind`) to prevent this.
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
- If fallback is consistently failing, ensure udev rules allow device access (see [Device Setup Guide](device_setup.md)).

## Configuration Errors

**"Duplicate key name"**
- Every key under `keys:` must have a unique name.

**"Layout references undefined key"**
- If a layout uses `1: "MyKey"`, ensure `MyKey` is defined in the `keys` section.

**"Icon file not found"**
- Paths are relative to the `config.yml` file location (or the working directory if running from source). Use absolute paths if unsure.

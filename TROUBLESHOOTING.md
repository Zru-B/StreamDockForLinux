# Troubleshooting

### Device Not Found

**Check device connection:**
```bash
lsusb | grep -i hotspot
```

**Check udev rules:**
```bash
ls -l /dev/hidraw* | grep -i hotspot
```

**Fix:**
1. Verify udev rules are correct
2. Reload udev: `sudo udevadm control --reload-rules && sudo udevadm trigger`
3. Reconnect device
4. Add user to plugdev group: `sudo usermod -a -G plugdev $USER`
5. Log out and log back in

### Permission Denied

**Error:** `PermissionError: [Errno 13] Permission denied`

**Fix:**
1. Check udev rules are set up correctly
2. Ensure you're in the plugdev group: `groups`
3. Device mode should be `0666` in udev rules
4. Restart the system if needed

### Keyboard Controls Mouse Pointer (+ Cursor / Mouse Keys Activated)

**Problem:** After locking/unlocking the computer, your keyboard controls the mouse pointer. The cursor changes to a **+ sign**, and you have to press ESC to return to normal. This is the **Mouse Keys accessibility feature** being accidentally activated.

**Cause:** The StreamDock device has multiple HID interfaces. During device re-initialization (especially after lock/unlock), some interfaces send signals that the system interprets as the Mouse Keys activation shortcut (typically Shift pressed 5 times).

**Complete Fix:**

1. **Install the updated udev rules** (this is critical):
   ```bash
   cd /path/to/StreamDock
   sudo cp 99-streamdock.rules /etc/udev/rules.d/
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

2. **Disconnect and reconnect the device** completely:
   ```bash
   # Unplug the USB device and plug it back in
   ```

3. **Verify the device is NOT creating input event devices:**
   ```bash
   ls -l /dev/input/by-id/ | grep -i "6603.*1006"
   ```
   
   **Should return NOTHING.** If you see any event devices, the udev rules didn't apply correctly.

4. **Check if libinput is ignoring the device:**
   ```bash
   libinput list-devices | grep -A 10 "6603"
   ```
   
   The device should **not appear** in this list at all.

5. **Disable Mouse Keys permanently** (recommended):
   
   **KDE Plasma:**
   - System Settings → Accessibility → Mouse Navigation
   - Uncheck "Activate with Shift key"
   - Click "Apply"
   
   **GNOME:**
   - Settings → Accessibility → Pointing & Clicking
   - Turn off "Mouse Keys"
   - Disable "Activation shortcut"
   
   **X11 (command line):**
   ```bash
   xkbset -m  # Disable mouse keys
   ```

6. **Find your actual device VID/PID** if the rules still don't work:
   ```bash
   lsusb | grep -i hotspot
   # or
   lsusb | grep -i mirabox
   ```
   
   Update `6603` and `1006` in the udev rules to match your device.

**Why This Happens:**
- Device has 3+ HID interfaces
- Linux tries to bind keyboard/mouse drivers to ALL interfaces
- During re-initialization (unlock), spurious events trigger Mouse Keys
- The updated udev rules prevent driver binding entirely

**Prevention:** 
- Always use the provided udev rules
- The rules now include `HID_GENERIC unbind` to prevent driver attachment
- Added delays in device re-initialization to stabilize the device

### Lock Monitor Not Working

**Check dependencies:**
```bash
python3 -c "import dbus; import gi; print('OK')"
```

**Fix:**
```bash
# Arch Linux
sudo pacman -S python-dbus python-gobject

# Ubuntu/Debian
sudo apt install python3-dbus python3-gi
```

**Test D-Bus connection:**
```bash
dbus-send --session --print-reply \
  --dest=org.freedesktop.ScreenSaver \
  /ScreenSaver \
  org.freedesktop.ScreenSaver.GetActive
```

### Keyboard Automation Not Working

**For X11:**
```bash
sudo pacman -S xdotool    # Arch
sudo apt install xdotool  # Ubuntu
```

**For Wayland/KDE:**
```bash
yay -S kdotool-git
```

### Window Rules Not Working

**X11:** Install `xdotool`

**Wayland/KDE:** Ensure KWin scripting is available (usually included in KDE)

**Test window detection:**
```bash
# X11
xdotool getactivewindow getwindowclassname

# KDE/Wayland
qdbus org.kde.KWin /KWin org.kde.KWin.queryWindowInfo
```

### Configuration Validation Errors

Common errors:

**"Duplicate key name"** - Each key must have a unique name

**"At least one layout must have 'Default: true'"** - Mark one layout as default

**"Layout references undefined key"** - Check key names match exactly

**"Icon file not found"** - Verify icon path is correct (relative to config file)

**"A key must have either 'icon' OR 'text'"** - Don't use both

### Virtual Environment Issues

If you get import errors with virtual environment:

```bash
# Reinstall with system site packages
python -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements.txt
```

Some packages (like dbus-python, PyGObject) may need system libraries and work better with `--system-site-packages`.

### SVG Icons Not Working

**Install SVG support:**
```bash
# Arch
sudo pacman -S librsvg

# Ubuntu
sudo apt install librsvg2-bin

# Also install Python package
pip install cairosvg
```

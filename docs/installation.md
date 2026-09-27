# Installation Guide

This guide covers the system and Python dependencies required to run StreamDock.

## System Dependencies

StreamDock relies on several system-level libraries for USB communication, image processing, and automation.

### Arch Linux

```bash
# Required packages
sudo pacman -S python python-pip hidapi libusb

# For keyboard automation (X11)
sudo pacman -S xdotool

# For keyboard automation (Wayland/KDE)
yay -S kdotool-git

# For audio control
sudo pacman -S pulseaudio-utils

# For lock monitor (optional)
sudo pacman -S python-dbus python-gobject

# For SVG support
sudo pacman -S librsvg
```

### Ubuntu / Debian

```bash
# Required packages
sudo apt install python3-pip libhidapi-libusb0 libusb-1.0-0-dev

# For keyboard automation (X11)
sudo apt install xdotool

# For audio control
sudo apt install pulseaudio-utils

# For lock monitor (optional)
sudo apt install python3-dbus python3-gi

# For SVG support
sudo apt install librsvg2-bin
```

---

## Python Dependencies

Install required Python packages using pip.

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install pillow pyyaml "cairosvg>=2.7.0" pyudev PyQt6 dbus-python PyGObject
```

### Package Details

**Required packages:**
- `pillow` - Image processing (PNG, JPG, GIF)
- `pyyaml` - YAML configuration parsing
- `cairosvg` - SVG to PNG conversion
- `pyudev` - Device hotplug monitoring
- `PyQt6` - Configuration editor GUI

**System wrappers (require system libraries):**
- `dbus-python` - D-Bus communication (for Media control & Lock monitor)
- `PyGObject` - GLib main loop (for Lock monitor)

---

## Virtual Environment Setup

Using a virtual environment is strongly recommended to avoid conflicts with system packages.

```bash
# 1. Create virtual environment
# We use --system-site-packages because some libraries (like dbus-python/PyGObject) 
# bind better to system libraries this way on some distros.
python -m venv --system-site-packages venv

# 2. Activate virtual environment
source venv/bin/activate

# 3. Install dependencies
# For development (includes testing and linting tools):
pip install -r requirements-dev.txt

# For production only:
pip install -r requirements.txt

# 4. Run the application (opens the configuration GUI)
cd src
python main.py

# Or run the controller with no GUI:
python main.py --headless
```

To exit the virtual environment when done:
```bash
deactivate
```

---

## Device Permissions & Launcher (Linux)

By default, the USB device is only accessible as root. The `scripts/install.sh` script handles everything in one step:

```bash
./scripts/install.sh
```

This installs:

| File | Destination | Purpose |
|---|---|---|
| `contrib/70-streamdock.rules` | `/etc/udev/rules.d/` | Tags the USB and hidraw nodes `uaccess`, so the user at the local seat can open them |
| `contrib/streamdock.desktop.template` | `~/.local/share/applications/streamdock.desktop` | Application launcher (paths filled in by the script) |
| `contrib/streamdock.svg` | `~/.local/share/icons/hicolor/scalable/apps/` | Launcher and tray icon |

No group membership is needed: systemd-logind gives whoever is logged in at
the local seat an ACL on the device. The file must sort before
`73-seat-late.rules`, which applies those ACLs, hence the `70-` prefix. The
script also removes the `99-streamdock.rules` that earlier versions installed.

To check it worked, unplug and replug the deck, then:

```bash
lsusb -d 6603:1006               # the deck (HOTSPOTEKUSB): note Bus BBB Device DDD
getfacl /dev/bus/usb/BBB/DDD     # owner root, plus a user:<you>:rw- entry
getfacl /dev/hidrawN             # same for its hidraw node(s), if any
```

The app talks to the USB node (libhidapi's libusb backend); `ls -l` on it
shows `root root` with a `+` marking the ACL.

If your deck reports a different vendor/product ID in `lsusb`, change the
two IDs in `contrib/70-streamdock.rules` before running the script. If the
deck moves the mouse pointer or triggers Mouse Keys, see
[Troubleshooting](troubleshooting.md#mouse-keys--cursor-issues).

### Starting at login

StreamDock is a normal desktop application, so use your desktop's own
autostart settings to launch it at login. Add `--minimized` to start it
straight into the system tray:

```bash
python src/main.py --minimized
```

### Uninstall

```bash
./scripts/uninstall.sh
```

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
pip install pillow pyyaml cairosvg pyudev PyQt6 dbus-python PyGObject
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

# 4. Run the application
cd src
python main.py
```

To exit the virtual environment when done:
```bash
deactivate
```

---

## Device Permissions & Auto-start (Linux)

By default, the USB device is only accessible as root. The `scripts/install.sh` script handles everything in one step:

```bash
./scripts/install.sh
```

This installs:

| File | Destination | Purpose |
|---|---|---|
| `contrib/99-streamdock.rules` | `/etc/udev/rules.d/` | Grants `plugdev` group write access; triggers start/stop on plug/unplug |
| `contrib/streamdock-udev-helper` | `/usr/local/bin/` | Helper called by udev — finds the active user and controls their service |
| `contrib/streamdock.service.template` | `~/.config/systemd/user/streamdock.service` | Systemd user service (paths filled in by the script) |

### Why a systemd user service?

udev rules run as root with no access to the user's graphical session. The application needs the user's D-Bus session for window detection and lock/unlock monitoring. The helper script uses `systemctl --user --machine=USER@` to bridge from root (udev) into the correct user session — without hardcoding any username.

### Optional: start at login

To also launch StreamDock when you log in (not just when the device is plugged in):

```bash
systemctl --user enable streamdock.service
```

### Useful commands

```bash
# Check if the service is running
systemctl --user status streamdock.service

# Follow live logs
journalctl --user -u streamdock.service -f

# Start / stop manually
systemctl --user start streamdock.service
systemctl --user stop streamdock.service
```

### Uninstall

```bash
./scripts/uninstall.sh
```

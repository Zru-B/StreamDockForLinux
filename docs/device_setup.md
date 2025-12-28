# Device Setup & udev Rules

To access the StreamDock device without root privileges and prevent conflicts with the OS input system, you must configure `udev` rules.

## 1. Find Your Device IDs

Connect your StreamDock and run:

```bash
lsusb | grep -i hotspot
```

Or if that returns nothing, try:
```bash
lsusb | grep -i mirabox
```

You should see output like:
```
Bus 001 Device 005: ID 65e3:1006 HOTSPOTEKUSB HOTSPOTEKUSB HID DEMO
```

Note the ID format: `VID:PID` (e.g., `65e3:1006`).
- **Vendor ID (VID):** `6603` (or `65e3`)
- **Product ID (PID):** `1006`

## 2. Create udev Rule

Create a new udev rule file:

```bash
sudo nano /etc/udev/rules.d/99-streamdock.rules
```

Add the following content (replace VID `6603` and PID `1006` with your device IDs if different).

**⚠️ CRITICAL:** These rules are essential to prevent the "Mouse Keys" problem where the device accidentally controls your mouse cursor.

```udev
# StreamDock Device Access Rules
# Prevents the device from being used as a keyboard/mouse by the system
# Only allows the StreamDock application to access it via hidraw

# Match the StreamDock device - Allow USB access
SUBSYSTEM=="usb", ATTRS{idVendor}=="6603", ATTRS{idProduct}=="1006", MODE="0666", GROUP="plugdev"

# Allow hidraw access for interface 0 only (for StreamDock application)
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="6603", ATTRS{idProduct}=="1006", MODE="0666", GROUP="plugdev"

# CRITICAL: Prevent ALL interfaces from being recognized as input devices
# This must come BEFORE the device is processed by input subsystem
SUBSYSTEMS=="usb", ATTRS{idVendor}=="6603", ATTRS{idProduct}=="1006", ENV{ID_INPUT}="0", ENV{ID_INPUT_KEYBOARD}="0", ENV{ID_INPUT_MOUSE}="0", ENV{ID_INPUT_TABLET}="0", ENV{ID_INPUT_TOUCHPAD}="0", ENV{ID_INPUT_JOYSTICK}="0"

# Tell libinput to completely ignore this device
SUBSYSTEM=="input", ATTRS{idVendor}=="6603", ATTRS{idProduct}=="1006", ENV{ID_INPUT}="0", ENV{LIBINPUT_IGNORE_DEVICE}="1", TAG-="uaccess"

# Prevent udev from creating ANY input event devices for this device
KERNEL=="event*", ATTRS{idVendor}=="6603", ATTRS{idProduct}=="1006", MODE="0000", GROUP="root"

# Block all HID interfaces except hidraw (prevents keyboard/mouse driver binding)
SUBSYSTEM=="hid", ATTRS{idVendor}=="6603", ATTRS{idProduct}=="1006", ENV{HID_NAME}="StreamDock", RUN+="/bin/sh -c 'echo -n %k > /sys/bus/hid/drivers/hid-generic/unbind || true'"
```

## 3. Apply Changes

1. **Add your user to the plugdev group:**
   ```bash
   sudo usermod -a -G plugdev $USER
   ```

2. **Reload rules:**
   ```bash
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

3. **Log out and log back in** (for group changes to take effect).

## 4. Verify Setup

Disconnect and reconnect your device, then check:

```bash
ls -l /dev/hidraw* | grep hotspot
```

You should see permissions like `crw-rw-rw-` indicating the device is accessible.

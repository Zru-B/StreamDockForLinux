# StreamDock - Linux Stream Dock Controller

A powerful, customizable Stream Dock 293v3 controller for Linux with YAML configuration, context-aware layout switching, keyboard automation, D-Bus integration, lock monitoring, and window monitoring.

## Features

- 🎯 **YAML Configuration** - Define your entire setup in a simple config file
- 🪟 **Context-Aware Layouts** - Automatically switch layouts based on focused window
- 🔒 **Lock Monitor** - Automatically turn off device when computer is locked
- ⌨️ **Keyboard Automation** - Execute commands, type text, simulate shortcuts (Virtual Keyboard & xdotool)
- 🎵 **Media Controls** - Control Spotify, VLC, and other MPRIS-compatible players
- 🔊 **Volume Control** - Adjust system volume with PulseAudio integration
- 🎨 **Dynamic Key Images** - Change key images on press/release
- 🖼️ **SVG Support** - Use vector graphics for crisp, scalable icons
- 📝 **Text-Based Keys** - Create keys from text without image files
- 💡 **Brightness Control** - Adjust device brightness on-the-fly
- 🔄 **Layout Management** - Multiple layouts with easy switching
- 🐧 **Linux Native** - Built for Linux (X11 & Wayland support)

---

## Table of Contents

1. [Installation](#installation)
   - [System Dependencies](#system-dependencies)
   - [Python Dependencies](#python-dependencies)
   - [Virtual Environment Setup](#virtual-environment-setup)
2. [Device Setup](#device-setup)
   - [udev Rules](#udev-rules)
3. [Configuration](#configuration)
   - [Basic Structure](#basic-structure)
   - [Settings](#settings)
   - [Keys](#keys)
   - [Layouts](#layouts)
   - [Window Rules](#window-rules)
4. [Actions Reference](#actions-reference)
5. [Running the Application](#running-the-application)
6. [Examples](#examples)
7. [Troubleshooting](#troubleshooting)

---

## Installation

### System Dependencies

#### Arch Linux

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

# For Virtual Keyboard (optional but recommended)
# No system packages needed (uses python-evdev)
# But requires udev rule setup (see Device Setup)
```

#### Debian / Ubuntu

```bash
# Core dependencies
sudo apt install python3-pip libhidapi-hidraw0 libusb-1.0-0 pkg-config gobject-introspection libgirepository-2.0-dev libcairo2-dev

# For keyboard automation (X11)
sudo apt install xdotool

# For keyboard automation (Wayland/KDE)
## Download it from https://github.com/jinliu/kdotool/releases and extract the binary to a location in your path.

# For audio control
sudo apt install pulseaudio-utils

# For lock monitor (optional)
sudo apt install python3-dbus python3-gi
```


### Python Dependencies

Install required Python packages:

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install pillow pyyaml cairosvg pyudev PyQt6 dbus-python PyGObject
```

**Required packages:**
- `pillow` - Image processing
- `pyyaml` - YAML configuration parsing
- `cairosvg` - SVG to PNG conversion
- `pyudev` - Device hotplug monitoring
- `PyQt6` - Configuration editor GUI
- `evdev` - Virtual Keyboard support

**System dependencies (must be installed via package manager):**
- `hidapi` / `libhidapi-libusb` - HID device communication (system library, not Python package)
- `libusb` - USB communication
- `xdotool` - Keyboard automation for X11
- `kdotool` - Keyboard automation for KDE Wayland (optional, recommended for Wayland)

**Optional packages (for lock monitor):**
- `dbus-python` - D-Bus communication
- `PyGObject` - GLib main loop

### Virtual Environment Setup

Using a virtual environment is recommended to avoid conflicts with system packages:

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
cd src
python main.py

# When done, deactivate
deactivate
```

**Note:** You may need to install some system packages even when using a virtual environment (like `hidapi`, `libusb`, system D-Bus libraries).

---

## Device Setup

### udev Rules

To access the StreamDock device without root privileges, you need to set up udev rules.

#### 1. Find Your Device IDs

Connect your StreamDock and run:

```bash
lsusb | grep -i hotspot
```

You should see output like:
```
Bus 001 Device 005: ID 65e3:1006 HOTSPOTEKUSB HOTSPOTEKUSB HID DEMO
```

Note the ID format: `65e3:1006` (Vendor:Product)

#### 2. Create udev Rule

Create a new udev rule file:

```bash
sudo nano /etc/udev/rules.d/99-streamdock.rules
```

Add the following content (replace VID `6603` and PID `1006` with your device IDs if different):

```
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

**⚠️ CRITICAL:** These udev rules are **essential** to prevent the Mouse Keys problem. The StreamDock device has multiple HID interfaces, and without these rules:
- Some interfaces will be recognized as keyboard/mouse devices
- Your keyboard will randomly control the mouse pointer (+ cursor)
- The Mouse Keys accessibility feature will be triggered during device re-initialization

The rules above:
1. Allow hidraw access for the StreamDock application
2. **Prevent ALL input device creation** (no event devices)
3. **Force libinput to ignore** the device completely  
4. **Unbind HID drivers** from all device interfaces

**Common Device IDs:**
- VID: `6603` (26115 decimal) - HOTSPOTEKUSB / Mirabox
- PID: `1006` (4102 decimal) - Common StreamDock model (293v3)

**To find your device IDs:**
```bash
lsusb | grep -i hotspot
```

#### 3. Add User to plugdev Group

```bash
sudo usermod -a -G plugdev $USER
```

#### 4. Reload udev Rules

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

#### 5. Verify Setup

Disconnect and reconnect your device, then check:

```bash
ls -l /dev/hidraw* | grep hotspot
```

You should see permissions like `crw-rw-rw-` indicating the device is accessible.

**Note:** You may need to log out and log back in for group changes to take effect.

### Virtual Keyboard Setup (Recommended)

To enable the improved Virtual Keyboard (faster, reliable, works on Wayland/X11 without focus stealing), you need additional udev rules for `/dev/uinput`.

See [SETUP_UDEV.md](SETUP_UDEV.md) for detailed instructions.

Briefly:
1.  Create `/etc/udev/rules.d/99-streamdock-uinput.rules` with:
    ```
    KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"
    ```
2.  Add your user to the `input` group:
    ```
    sudo usermod -aG input $USER
    ```
3.  Load the kernel module:
    ```
    sudo modprobe uinput
    ```
4.  Reload rules:
    ```
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    ```

---

## Configuration

StreamDock uses a YAML configuration file to define keys, layouts, and behaviors.

### Basic Structure

Create or edit `src/config.yml`:

```yaml
streamdock:
  settings:
    brightness: 15              # 0-100
    lock_monitor: true          # Turn off when locked
  
  keys:
    KeyName:
      icon: "../img/icon.png"
      on_press_actions:
        - "ACTION_TYPE": "parameter"
  
  layouts:
    Main:
      Default: true
      keys:
        - 1: "KeyName"
  
  windows_rules:
    RuleName:
      window_name: "Firefox"
      layout: "Main"
```

### Settings

Optional device settings:

```yaml
settings:
  brightness: 15                # Device brightness (0-100), default: 50
  lock_monitor: true            # Auto turn off when computer locked, default: true
  double_press_interval: 0.3    # Double-press detection time window in seconds (0-2.0), default: 0.3
```

**brightness:** Controls the LED brightness of the device.

**lock_monitor:** When enabled, automatically turns off the device when you lock your computer (Super+L in KDE) and turns it back on when unlocked. Requires `dbus-python` and `PyGObject`.

**double_press_interval:** Time window in seconds for detecting double-presses on keys. Lower values (e.g., 0.2) require faster double-presses. Higher values (e.g., 0.5) are more forgiving but may delay single-press actions. Valid range: 0.1-2.0 seconds. Default: 0.3 seconds (300ms).

### Keys

Keys are defined with unique names and can use either images or text.

#### Image-Based Keys

```yaml
keys:
  Firefox:
    icon: "../img/firefox.png"      # Supports: PNG, JPG, GIF, SVG
    on_press_actions:
      - "EXECUTE_COMMAND": ["firefox"]
```

**Supported image formats:** PNG, JPG, GIF, SVG

#### Text-Based Keys

```yaml
keys:
  Settings:
    text: "Settings"                # Text to display
    text_color: "white"             # Optional, default: white
    background_color: "black"       # Optional, default: black  
    font_size: 20                   # Optional, default: 20
    bold: true                      # Optional, default: true
    on_press_actions:
      - "EXECUTE_COMMAND": ["systemsettings"]
```

**Text key options:**
- `text` (required) - Text to display
- `text_color` (optional) - Color name or hex code (e.g., "red", "#FF0000")
- `background_color` (optional) - Background color
- `font_size` (optional) - Font size in pixels (1-100)
- `bold` (optional) - Use bold font (true/false)

**Note:** A key must have either `icon` OR `text`, not both.

#### Action Types

Keys can have three types of actions:
- `on_press_actions` - Execute when key is pressed
- `on_release_actions` - Execute when key is released
- `on_double_press_actions` - Execute on double-press

```yaml
MyKey:
  icon: "../img/icon.png"
  on_press_actions:
    - "EXECUTE_COMMAND": ["firefox"]
  on_release_actions:
    - "TYPE_TEXT": "Released"
  on_double_press_actions:
    - "KEY_PRESS": "CTRL+C"
```

### Layouts

Layouts assign key numbers to keys. Each layout must have at least one key.

**One layout MUST have `Default: true`**

```yaml
layouts:
  Main:
    Default: true           # Default layout
    keys:
      - 1: "Firefox"
      - 2: "Chrome"
      - 3: "Spotify"
      - 4: null             # Empty key (cleared)
  
  Media:
    keys:
      - 1: "PlayPause"
      - 2: "NextTrack"
  
  Settings:
    clear_all: true         # Clear all icons when this layout is applied
    keys:
      - 1: "BackButton"
      - 2: "BrightnessUp"
```

**Layout Options:**
- `Default: true` - Mark this as the default layout (required for exactly one layout)
- `clear_all: true` - Clear all icons before applying this layout (optional, default: false)
- `keys` - List of key assignments (required)

**Key numbers:** 1-15 (correspond to physical positions on device)

**Empty keys:** Use `null` or `~` to explicitly clear a key position:

```yaml
- 3: null      # Cleared
- 4: ~         # Also cleared (alternative syntax)
```

**clear_all behavior:**
- When `clear_all: true` is set in the layout definition, all icons will be cleared **every time** this layout is applied
- This works for:
  - Manual layout switches via `CHANGE_LAYOUT` action
  - Automatic switches via window rules
  - Any other layout switching mechanism

### Window Rules

Automatically switch layouts based on the focused window:

```yaml
windows_rules:
  Firefox_Rule:
    window_name: "Firefox"      # Pattern to match
    layout: "Browser_Layout"    # Layout to apply
    match_field: "class"        # Optional: class, title, raw
  
  Kate_Rule:
    window_name: "Kate"
    layout: "Editor_Layout"
```

**Match fields:**
- `class` (default) - Match against application class name
- `title` - Match against window title
- `raw` - Match against raw window info

**Requirements:**
- X11: Requires `xdotool`
- Wayland/KDE: Requires `kdotool` or KWin scripting

---

## Actions Reference

### EXECUTE_COMMAND

Execute a system command:

```yaml
- "EXECUTE_COMMAND": ["firefox"]
- "EXECUTE_COMMAND": ["dolphin", "/home"]
```

**Note:** All executed commands run in **completely separate processes**, detached from the StreamDock script using `nohup` and shell backgrounding. Their output won't appear in the StreamDock console, and they continue running independently even if you stop, kill, or crash the script.

### LAUNCH_APPLICATION

Smart application launcher - launches an application if not running, or focuses its window if already running (run or raise behavior):

```yaml
# Simple format (command as string or list)
- "LAUNCH_APPLICATION": "firefox"
- "LAUNCH_APPLICATION": ["dolphin", "/home"]

# Using desktop files (KDE/GNOME applications)
- "LAUNCH_APPLICATION":
    desktop_file: "firefox.desktop"          # Searches standard locations

- "LAUNCH_APPLICATION":
    desktop_file: "org.kde.kate"             # Auto-adds .desktop extension

- "LAUNCH_APPLICATION":
    desktop_file: "/usr/share/applications/org.kde.konsole.desktop"  # Full path

# Advanced format with custom window matching
- "LAUNCH_APPLICATION":
    command: ["firefox"]           # Command to launch
    class_name: "firefox"          # Window class to search (optional, defaults to command[0])
    match_type: "contains"         # "contains" or "exact" (optional, default: "contains")
    force_new: false               # Always launch new instance (optional, default: false)

# Force new instance (always launch, never focus existing)
- "LAUNCH_APPLICATION":
    command: ["firefox", "--new-window"]
    force_new: true                # Skip window detection, always launch
```

**How it works:**
1. If `force_new: true`, always launches new instance (skips window detection)
2. Otherwise, searches for existing windows by class name
3. If found, focuses the window
4. If not found, launches the application

**Process Behavior:**
- All launched applications run in **completely separate processes**, detached from the StreamDock script using `nohup`
- Application output (stdout/stderr) does **not** appear in the StreamDock console (redirected to /dev/null)
- Applications continue running **independently** even if you stop, kill, or crash the StreamDock script
- Each application has its own process session and will not receive signals from the parent process
- Uses shell backgrounding (`&`) and `nohup` for maximum reliability

**Parameters:**
- `command` (option 1) - Command to execute (string or list)
- `desktop_file` (option 2) - Path to .desktop file or application name
- `class_name` (optional) - Window class name to search, defaults to command[0] or from desktop file
- `match_type` (optional) - `"contains"` (default) or `"exact"` matching
- `force_new` (optional) - `true` to always launch new instance, `false` (default) to focus existing

**Desktop file support:**
- Searches standard locations: `/usr/share/applications/`, `~/.local/share/applications/`, flatpak dirs
- Automatically extracts command, window class, and application name
- Handles field codes (`%f`, `%u`, etc.) properly
- Works with both simple names (`firefox.desktop`) and full paths

**Use cases:**
- Quickly switch to or launch your browser
- Toggle applications without launching duplicates
- One-button access to frequently used apps
- Force new windows for specific scenarios (e.g., private browsing)
- Use system-installed applications via desktop files

**Examples:**

```yaml
keys:
  # Smart launcher - focus if running
  Firefox:
    icon: "../img/firefox.png"
    on_press_actions:
      - "LAUNCH_APPLICATION": "firefox"
  
  # Using desktop file (recommended for KDE/GNOME apps)
  Kate:
    icon: "../img/kate.png"
    on_press_actions:
      - "LAUNCH_APPLICATION":
          desktop_file: "org.kde.kate.desktop"
  
  # Force new instance - always opens new window
  Firefox_Private:
    icon: "../img/firefox_private.png"
    on_press_actions:
      - "LAUNCH_APPLICATION":
          command: ["firefox", "--private-window"]
          force_new: true
  
  Terminal:
    icon: "../img/terminal.png"
    on_press_actions:
      - "LAUNCH_APPLICATION": "konsole"
  
  VSCode:
    icon: "../img/vscode.png"
    on_press_actions:
      - "LAUNCH_APPLICATION":
          command: ["code"]
          class_name: "code"
          match_type: "exact"
```

### KEY_PRESS

Simulate keyboard shortcuts:

```yaml
- "KEY_PRESS": "CTRL+C"
- "KEY_PRESS": "CTRL+ALT+T"
- "KEY_PRESS": "SUPER+L"
```

**Supported modifiers:** CTRL, ALT, SHIFT, SUPER (Windows/Meta key)

### TYPE_TEXT

Type text automatically:

```yaml
- "TYPE_TEXT": "user@example.com"
```

### WAIT

Pause execution (in seconds):

```yaml
- "WAIT": 0.5
- "WAIT": 2
```

### CHANGE_KEY_IMAGE

Change the key's image dynamically:

```yaml
- "CHANGE_KEY_IMAGE": "../img/new_icon.png"
```

### CHANGE_LAYOUT

Switch to a different layout:

```yaml
# Simple format (just switch layouts)
- "CHANGE_LAYOUT": "Media_Layout"

# Advanced format with options
- "CHANGE_LAYOUT":
    layout: "Media_Layout"
    clear_all: true              # Clear all icons before applying layout (optional, default: false)
```

**Parameters:**
- `layout` (required) - Name of the layout to switch to
- `clear_all` (optional) - If `true`, clears all icons before applying the new layout. Useful for clean transitions between layouts with different key configurations. Default: `false`

**Use cases:**
- **Without clear_all:** Keys from previous layout remain visible if not overwritten
- **With clear_all:** All keys are cleared first, then only new layout keys are shown

**Examples:**

```yaml
keys:
  # Standard layout switch (keys overlay)
  ToMedia:
    text: "Media"
    on_press_actions:
      - "CHANGE_LAYOUT": "Media_Layout"
  
  # Clean layout switch (clear all first)
  ToSettings:
    text: "Settings"
    on_press_actions:
      - "CHANGE_LAYOUT":
          layout: "Settings_Layout"
          clear_all: true
  
  # Back button that clears and returns to main
  BackToMain:
    text: "← Back"
    on_press_actions:
      - "CHANGE_LAYOUT":
          layout: "Main"
          clear_all: true
```

### DBUS

Send D-Bus commands for media/volume control:

```yaml
# Predefined shortcuts
- "DBUS": {"action": "play_pause"}
- "DBUS": {"action": "next"}
- "DBUS": {"action": "previous"}
- "DBUS": {"action": "volume_up"}
- "DBUS": {"action": "volume_down"}
- "DBUS": {"action": "mute"}
```

### DEVICE_BRIGHTNESS_UP / DOWN

Adjust device brightness:

```yaml
- "DEVICE_BRIGHTNESS_UP": ""      # Increase by 10%
- "DEVICE_BRIGHTNESS_DOWN": ""    # Decrease by 10%
```

### Multiple Actions

Actions execute sequentially:

```yaml
on_press_actions:
  - "TYPE_TEXT": "user@example.com"
  - "WAIT": 0.2
  - "KEY_PRESS": "CTRL+A"
  - "KEY_PRESS": "CTRL+C"
```

---

## Running the Application

### Quick Start

```bash
cd src
python3 main.py
```

### With Custom Config

```bash
python3 main.py /path/to/custom_config.yml
```

### Using Virtual Environment

```bash
source venv/bin/activate
cd src
python3 main.py
```

### Expected Output

```
🔒 Lock monitor started
🔒 Connected to org.freedesktop.ScreenSaver

StreamDock is ready. Press Ctrl+C to exit.
```

### Exit

Press `Ctrl+C` to stop the application gracefully.

---

## Examples

### Example 1: Basic Application Launcher

```yaml
streamdock:
  settings:
    brightness: 15
  
  keys:
    Firefox:
      icon: "../img/firefox.png"
      on_press_actions:
        - "EXECUTE_COMMAND": ["firefox"]
    
    Terminal:
      icon: "../img/terminal.png"
      on_press_actions:
        - "EXECUTE_COMMAND": ["konsole"]
  
  layouts:
    Main:
      Default: true
      keys:
        - 1: "Firefox"
        - 2: "Terminal"
```

### Example 2: Media Control

```yaml
keys:
  PlayPause:
    icon: "../img/play.png"
    on_press_actions:
      - "DBUS": {"action": "play_pause"}
  
  VolumeUp:
    text: "Vol+"
    text_color: "green"
    on_press_actions:
      - "DBUS": {"action": "volume_up"}
```

### Example 3: Text Shortcuts

```yaml
keys:
  EmailSignature:
    text: "Email"
    on_press_actions:
      - "TYPE_TEXT": "Best regards,\nJohn Doe"
```

### Example 4: Layout Switcher

```yaml
keys:
  ToMedia:
    text: "Media"
    on_press_actions:
      - "CHANGE_LAYOUT": "Media_Layout"
  
  ToMain:
    text: "Main"
    on_press_actions:
      - "CHANGE_LAYOUT": "Main"

layouts:
  Main:
    Default: true
    keys:
      - 1: "Firefox"
      - 15: "ToMedia"
  
  Media_Layout:
    keys:
      - 1: "PlayPause"
      - 15: "ToMain"
```

### Example 5: Window Rules

```yaml
windows_rules:
  Firefox_Rule:
    window_name: "Firefox"
    layout: "Browser_Layout"
    match_field: "class"
  
  Spotify_Rule:
    window_name: "Spotify"
    layout: "Media_Layout"
    match_field: "class"
```

When you focus Firefox, the Browser_Layout automatically activates. When you focus Spotify, Media_Layout activates.

---

## Troubleshooting

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

---

## Advanced Features

### Empty Keys in Layouts

Clear specific key positions when switching layouts:

```yaml
layouts:
  Minimal:
    keys:
      - 1: "Firefox"
      - 2: null      # Cleared
      - 3: null      # Cleared
      - 4: "Terminal"
```

Use cases:
- Clean transitions between layouts
- Create visual gaps
- Temporarily disable keys

### Brightness Control Keys

Create keys to adjust device brightness:

```yaml
keys:
  BrightnessUp:
    text: "☀"
    font_size: 30
    on_press_actions:
      - "DEVICE_BRIGHTNESS_UP": ""
  
  BrightnessDown:
    text: "☾"
    font_size: 30
    on_press_actions:
      - "DEVICE_BRIGHTNESS_DOWN": ""
```

### Complex Action Sequences

Chain multiple actions together:

```yaml
keys:
  Screenshot:
    icon: "../img/camera.png"
    on_press_actions:
      - "KEY_PRESS": "SHIFT+PRINT"  # Take screenshot
      - "WAIT": 0.5                  # Wait for dialog
      - "KEY_PRESS": "RETURN"        # Confirm save
```

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Contributing

Contributions are welcome! Feel free to:
- Report bugs
- Suggest features
- Submit pull requests
- Improve documentation

---

## Acknowledgments

- Based on [StreamDock-Device-SDK](https://github.com/MiraboxSpace/StreamDock-Device-SDK) by MiraboxSpace (MIT License)
- Uses `libhidapi-libusb` (system library) for USB/HID communication via ctypes
- SVG support via `cairosvg`
- Window monitoring via `xdotool`/`kdotool`
- Media control via D-Bus/MPRIS

---

## Support

For issues, questions, or feature requests, please open an issue on the project repository.

**System Requirements:**
- Linux (Wayland)
- Python 3.10+
- StreamDock-compatible device
- USB HID access

**Tested On:**
- Arch Linux + KDE Plasma 6.5

**Enjoy your StreamDock! 🎉**

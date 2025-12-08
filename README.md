# StreamDock - A Linux Controller for Stream Dock Devices

![StreamDock](https://img.shields.io/badge/Platform-Linux-blue)
![Python](https://img.shields.io/badge/Python-3.10+-yellow)
![License](https://img.shields.io/badge/License-MIT-green)

A powerful and customizable controller for the Stream Dock 293v3 on Linux, featuring a YAML-based configuration, context-aware layout switching, keyboard automation, D-Bus integration, and more.

## Features

- 🎯 **Declarative YAML Config:** Define your entire setup in a simple, human-readable configuration file.
- 🪟 **Context-Aware Layouts:** Automatically switch button layouts based on the currently focused application.
- 🔒 **Lock Monitor:** Automatically turns off the device screen when you lock your computer and wakes it on unlock.
- ⌨️ **Keyboard Automation:** Execute commands, type text, and simulate shortcuts (Virtual Keyboard & xdotool) to create complex macros.
- 🎵 **Media Controls:** Native control for Spotify, VLC, and other MPRIS-compatible media players.
- 🔊 **Volume Control:** Adjust system volume using built-in PulseAudio/PipeWire integration.
- 🎨 **Dynamic Keys:** Change key images and text on the fly in response to press/release actions.
- 🖼️ **SVG Support:** Use vector graphics for crisp, scalable icons
- 📝 **Text-Based Keys:** Create keys from text without image files
- 💡 **Brightness Control:** Adjust device brightness on-the-fly
- 🔄 **Layout Management:** Multiple layouts with easy switching
- 🐧 **Linux Native:** Built for Linux (X11 & Wayland support)

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Installation](#installation)
4. [Device Setup (udev)](#device-setup-udev-rules)
5. [Configuration](#configuration)
6. [Running the Application](#running-the-application)
7. [Troubleshooting](#troubleshooting)
8. [Advanced Features](#advanced-features)
9. [Contributing](#contributing)
10. [License](#license)

---

## Prerequisites

Before you begin, ensure you have the following:

- **Hardware:** A StreamDock 293v3 device.
- **Operating System:** Linux (tested on Arch Linux with KDE Plasma 6).
- **Python:** Python 3.10+
- **System Libraries:** `hidapi`, `libusb`, and `pkg-config`.

For specific features, you may need:
- **Keyboard Automation:** `xdotool` (for X11) or `kdotool` (for KDE Wayland).
- **Audio Control:** `pulseaudio-utils`.
- **Lock Monitor:** `python-dbus` and `python-gobject`.
- **SVG Icons:** `librsvg`.

---

## Quick Start

For those who are impatient to get started:

1.  **Install Dependencies & Set Permissions:**
    ```bash
    # Install system packages (see detailed Installation section for your distro)
    # Set up udev rules (see Device Setup section below - this is critical!)
    # Install Python packages
    pip install -r requirements.txt
    ```

2.  **Edit Configuration:**
    - Open `src/config.yml` and customize it to your needs. At a minimum, review the default key assignments.

3.  **Run the Application:**
    ```bash
    cd src
    python3 main.py
    ```

---

## Installation

### 1. System Dependencies

Install the required system packages for your distribution.

<details>
<summary><strong>🔵 Arch Linux</strong></summary>

```bash
# Required packages
sudo pacman -S python python-pip hidapi libusb

# For keyboard automation
sudo pacman -S xdotool      # (X11)
yay -S kdotool-git         # (Wayland/KDE)

# For audio/media control
sudo pacman -S pulseaudio-utils

# For SVG icon support
sudo pacman -S librsvg

# For lock monitor (optional)
sudo pacman -S python-dbus python-gobject

# For Virtual Keyboard (optional but recommended)
# No system packages needed (uses python-evdev)
# But requires udev rule setup (see Device Setup)
```
</details>

<details>
<summary><strong>🟠 Debian / Ubuntu</strong></summary>

```bash
# Core dependencies
sudo apt install python3-pip libhidapi-hidraw0 libusb-1.0-0 pkg-config gobject-introspection libgirepository-2.0-dev libcairo2-dev

# For keyboard automation
sudo apt install xdotool # (X11)
# For Wayland/KDE, download kdotool from https://github.com/jinliu/kdotool/releases

# For audio/media control
sudo apt install pulseaudio-utils

# For SVG icon support
sudo apt install librsvg2-bin

# For lock monitor (optional)
sudo apt install python3-dbus python3-gi
```
</details>

### 2. Python Dependencies

Using a virtual environment is highly recommended.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate
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

# To deactivate when you are done
# deactivate
```

**Note:** If you encounter issues with packages like `dbus-python` or `PyGObject`, you may need to create the virtual environment with `--system-site-packages` to ensure it can access system-level libraries.

---

## Device Setup (udev rules)

To access the StreamDock device without root privileges, you must set up udev rules. This is a **critical** step.

#### 1. Find Your Device ID

Connect your StreamDock and run `lsusb | grep -i hotspot`. You should see an ID like `6603:1006`. Note your device's Vendor and Product ID.

#### 2. Create the udev Rule File

Copy the `99-streamdock.rules` file from this repository to `/etc/udev/rules.d/`. If your device ID from the previous step is different, you must edit the file and replace the `VID` and `PID` values.

**⚠️ CRITICAL:** These udev rules are **essential** to prevent the "Mouse Keys" problem, where your keyboard might start controlling your mouse pointer. The purpose of these rules is to:
1.  Allow user access to the device (`hidraw`).
2.  **Prevent** the system from treating the device as a standard keyboard or mouse.
3.  Force `libinput` to completely ignore the device.
4.  Unbind the generic HID drivers that cause conflicts.

#### 3. Add Your User to the `plugdev` Group

```bash
sudo usermod -a -G plugdev $USER
```

#### 4. Reload udev Rules

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```
Finally, unplug and reconnect your device. You may need to log out and back in for group changes to take full effect.

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

StreamDock is configured via a single YAML file located at `src/config.yml`. This file defines the device settings, keys, layouts, and automation rules.

### Basic Structure

```yaml
streamdock:
  # Global device settings, all optional
  settings:
    # The physical keys' LED brightness, range from 0 to 100. Default: `50`.
    brightness: 15
    # Automatically turn the screen off when the computer is locked. Default: `true`.
    lock_monitor: true
    # THe maximal double-press time duration (in seconds), range from 0.1 to 2.0 seconds. Default: `0.3`.
    double_press_interval: 0.6
  
  # All available keys are defined here
  keys:
    KeyName:
      icon: "../img/icon.png"
      on_press_actions:
        - "ACTION_TYPE": "parameter"
  
  # Layouts are collections of keys mapped to physical buttons
  layouts:
    Main:
      Default: true
      keys:
        - 1: "KeyName"
  
  # Rules for automatic layout switching
  windows_rules:
    RuleName:
      window_name: "Firefox"
      layout: "Main"
```

### `keys`

Defines all the buttons available for use in layouts. Each key must have a unique name. A key can be either image-based or text-based.

**Image-Based Key:**
```yaml
keys:
  Firefox:
    icon: "../img/firefox.svg" # Supports PNG, JPG, GIF, SVG
    on_press_actions:
      - "LAUNCH_APPLICATION": "firefox"
```

**Text-Based Key:**
```yaml
keys:
  Settings:
    text: "Settings"
    text_color: "white"             # Optional
    background_color: "black"       # Optional
    font_size: 20                   # Optional
    bold: true                      # Optional
    on_press_actions:
      - "LAUNCH_APPLICATION": "systemsettings"
```

Keys can trigger actions on `on_press_actions`, `on_release_actions`, or `on_double_press_actions`.

### `layouts`

Layouts assign the defined keys into physical button numbers (1-15). **One layout MUST be marked as `Default: true`**.

- `keys`: A list of key number to key name mappings.
- `clear_all`: (`true`/`false`) Optional argument. If true, clears the entire board before drawing this layout's keys. Defaults to `false`
- `Default`: (`true`/`false`) Marks the layout that is active on startup.

```yaml
layouts:
  MainLayout:
    Default: true
    keys:
      - 1: "Firefox"
      - 2: "Terminal"
      - 3: null # This key will be blank
```

### `windows_rules`

Automatically switch layouts based on the currently focused window.

- `window_name`: A string or regex pattern to match.
- `layout`: The name of the layout to apply when a match is found.
- `match_field`: The window property to match against. Can be `class` (default), `title`, or `raw`.

```yaml
windows_rules:
  Firefox_Rule:
    window_name: "Firefox"
    layout: "Browser_Layout"
    match_field: "class"
```

---

## Actions Reference

A wide variety of actions can be triggered by key presses. For a complete list and detailed explanation of each action, please see the **[Keys Actions Reference](CONFIGURATION_ACTIONS.md)**.

---

## Running the Application

To run the application, navigate to the `src` directory and execute `main.py`.

```bash
# If using a virtual environment, make sure it's activated
source .venv/bin/activate
cd src
python3 main.py
```

To use a custom configuration file:
```bash
python3 main.py /path/to/your/custom_config.yml
```

Press `Ctrl+C` in the terminal to stop the application gracefully.

---

## Examples

Here are a few examples to showcase what's possible.

<details>
<summary><strong>Example 1: A simple application launcher</strong></summary>

```yaml
streamdock:
  keys:
    FirefoxKey:
      icon: "../img/firefox.png"
      on_press_actions:
        - "LAUNCH_APPLICATION": "firefox"
    TerminalKey:
      icon: "../img/konsole.svg"
      on_press_actions:
        - "LAUNCH_APPLICATION": "konsole"
  layouts:
    Main:
      Default: true
      keys:
        - 1: "FirefoxKey"
        - 2: "TerminalKey"
```
</details>

<details>
<summary><strong>Example 2: A layout for media control</strong></summary>

```yaml
keys:
  PlayPause:
    icon: "../img/play.svg"
    on_press_actions:
      - "DBUS": {"action": "play_pause"}
  NextTrack:
    icon: "../img/next_song.svg"
    on_press_actions:
      - "DBUS": {"action": "next"}
layouts:
  Media:
    keys:
      - 7: "PrevTrack" # Assuming PrevTrack is defined elsewhere
      - 8: "PlayPause"
      - 9: "NextTrack"
```
</details>

<details>
<summary><strong>Example 3: Context-aware switching</strong></summary>

```yaml
# This rule will automatically switch to the "Media" layout
# when a window with the class "Spotify" is focused.
windows_rules:
  SpotifyRule:
    window_name: "Spotify"
    layout: "Media"
    match_field: "class"
```
</details>

---

## Troubleshooting

For common issues, errors, and solutions, please see the **[Troubleshooting Guide](TROUBLESHOOTING.md)**.

---

## Advanced Features

### Empty Keys in Layouts

You can explicitly clear a key position in a layout by setting its value to `null`. This is useful for creating clean visual transitions between layouts.

```yaml
layouts:
  Minimal:
    keys:
      - 1: "Firefox"
      - 2: null # This key will be cleared
      - 3: null # This one too
      - 4: "Terminal"
```

### Complex Action Sequences

Chain multiple actions to create powerful macros. The actions are executed in order, with `WAIT` actions used to insert delays.

```yaml
keys:
  Screenshot:
    icon: "../img/camera.png"
    on_press_actions:
      - "KEY_PRESS": "SHIFT+PRINT"  # Take screenshot
      - "WAIT": 0.5                  # Wait for the dialog to appear
      - "KEY_PRESS": "RETURN"        # Confirm the save action
```

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Contributing

Contributions are welcome! Feel free to open an issue or submit a pull request for:
- Bug fixes
- Feature suggestions
- Documentation improvements

---

## Acknowledgments

- Uses `libhidapi-libusb` for HID communication.
- Based on the original [StreamDock-Device-SDK](https://github.com/MiraboxSpace/StreamDock-Device-SDK) by MiraboxSpace.
- SVG support via `cairosvg`.

---

**Enjoy your StreamDock! 🎉**

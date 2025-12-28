# StreamDock - Linux Stream Dock Controller

A powerful, customizable Stream Dock 293v3 controller for Linux.

StreamDock lets you define your entire deck configuration in a simple YAML file. It supports automatic layout switching based on the focused window, complex macros, system monitoring, and complete visual customization using images or text.

## Features

- 🎯 **YAML Configuration** - Simple, readable config files.
- 🪟 **Context-Aware** - Automatically switch layouts when you open Firefox, VSCode, or Spotify.
- 🔒 **Secure** - Auto-lock monitor turns off the display when your session locks.
- 🐧 **Linux Native** - Built for X11 and Wayland (KDE/GNOME).
- 🎨 **Visuals** - Support for PNG, JPG, GIF, SVG, and dynamic text generation.
- 🛠️ **Hackable** - Pure Python with a plugin-friendly architecture.

---

## 🚀 Quick Start

1.  **Install system dependencies** (see [Installation Guide](docs/installation.md) for Ubuntu/Debian):
    ```bash
    # Arch Linux example
    sudo pacman -S python python-pip hidapi libusb xdotool
    ```

2.  **Set up the environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Setup Device Permissions:**
    Follow the [Device Setup Guide](docs/device_setup.md) to configure `udev` rules. This is **critical** to prevent the "Mouse Keys" bug.

4.  **Run:**
    ```bash
    cd src
    python main.py
    ```

---

## 📚 Documentation

The documentation is organized into the following sections:

### Getting Started
*   [**Installation Guide**](docs/installation.md) - Detailed dependency lists and setup steps.
*   [**Device Setup**](docs/device_setup.md) - **Important:** `udev` rules and hardware configuration.
*   [**Troubleshooting**](docs/troubleshooting.md) - Fixes for common issues (Device not found, Permissions).

### Configuration
*   [**Configuration Guide**](docs/configuration.md) - How to write `config.yml`, define Keys, and create Layouts.
*   [**Actions Reference**](docs/actions_reference.md) - Dictionary of all available commands (`LAUNCH_APP`, `KEY_PRESS`, `DBUS`, etc.).

### 🍳 Cookbook & Recipes
Learn by example with these ready-to-use configurations:
*   [**Basic App Launcher**](docs/recipes/basic_launcher.md) - A simple menu to start your favorite apps.
*   [**Media Controller**](docs/recipes/media_control.md) - Volume, Mute, and Spotify controls.
*   [**The Productivity Setup**](docs/recipes/productivity.md) - Advanced context-switching rules (e.g., auto-show browser keys when Firefox is focused).

---

## License

This project is licensed under the [MIT License](LICENSE).

## Acknowledgments

- Based on [StreamDock-Device-SDK](https://github.com/MiraboxSpace/StreamDock-Device-SDK) by MiraboxSpace.
- Powered by `libhidapi`, `cairosvg`, and `pyudev`.
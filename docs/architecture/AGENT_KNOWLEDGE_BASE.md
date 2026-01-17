# StreamDockForLinux - Agent Knowledge Base

This document provides a high-density technical summary of the StreamDockForLinux project, designed for LLM-based agents.

## Project Overview
A Python-based controller for **MiraBox 293v3 Stream Dock** hardware on Linux. It bridges physical hardware buttons to system actions (macros, app launching, brightness) and provides automation based on window focus and screen lock states.

### Core Stack
- **Language**: Python 3.10+
- **Hardware Interface**: `libhidapi-libusb` via `ctypes` (No `hidraw` used).
- **GUI/Logic**: `PyQt6` (mostly for event loops), `Pillow` (image processing).
- **Automation**: `dbus-python`, `PyGObject` (introspection), `xdotool`/`kdotool` (input emulation).

---

## Architecture Detail

### 1. Hardware Communication (`src/StreamDock/transport/`)
- **`HIDTransport`**: Core protocol implementation. 513-byte packets with `"CRT"` signature.
- **`MockTransport`**: Headless mode (`--mock`) simulation using internal queues.
- **Protocol Commands**: 
  - `LIG`: Brightness
  - `CLE`: Key/Screen clear
  - `LOG`: Set background/key image
  - `DIS`: Wake screen
  - `STP`: Refresh/Stop

### 2. State Management
- **`DeviceManager`**: Singleton-style manager for hardware discovery and event listening thread.
- **`ConfigLoader`**: YAML-to-Object mapper. Supports nested `Layout` and `Key` definitions.
- **`WindowMonitor`**: Background thread polling active window info to trigger layout matches.

### 3. Action Ecosystem (`src/StreamDock/actions.py`)
Actions are defined as `(ActionType, Parameter)` tuples.
- **Window Activation**: Complex logic trying `kdotool` (Wayland), `xdotool` (X11), or `wmctrl`.
- **Media Control**: DBus-based shortcuts for Spotify and generic MPRIS players.
- **Dynamic Keys**: `CHANGE_KEY` and `CHANGE_KEY_TEXT` allow buttons to update their own visuals/actions at runtime.

---

## Known Limitations & Constraints

### 1. Window Detection Latency
Historical detection (Journal-based KWin) is slow (~280ms). New "Direct DBus" and "Init-Once" methods target ~10ms but are still being integrated/optimized.

### 2. Wayland/X11 Bifurcation
The project maintains parallel code paths for Wayland and X11. Detection and activation reliability varies significantly between the two.

### 3. Tool Dependency
Heavy reliance on CLI tools (`pgrep`, `pactl`, `dbus-send`). If these are missing, actions fail silently or with logged errors.

---

## Implementation Hints for Agents
- **Path Handling**: Always use absolute paths for images.
- **Action Execution**: Use `execute_actions(list, device, key_number)` for complex macros.
- **Debugging**: Run with `LOG_LEVEL=DEBUG` or with argument `--debug` to see debug logs as well as `@_timed` output.
- **Mocking**: Use `simulate_key_press(index)` in `MockTransport` to test logic without hardware.

---

## Git Guidelines
- **Diff Inspection**: When inspecting changes, always use `git --no-pager diff` (or equivalent `git diff --no-pager`) to ensure the entire output is captured in the log without being truncated by a pager.

# Domain Glossary

This document defines the core terminology used across the StreamDockForLinux project to ensure consistency in naming conventions, mental models, and AI-assisted development.

> [!NOTE]
> This glossary was generated through comprehensive codebase analysis and is maintained as the canonical reference for all project terminology. When implementing new features or refactoring code, prioritize using these standardized terms.

## Core Hardware & Device Concepts

| Term | Definition | Related Classes/Modules |
| :--- | :--- | :--- |
| **Action** | A system-level task triggered by a key press, release, or double-press event (e.g., launching an app, simulating a key combo, changing layouts). | `ActionType`, `actions.py` |
| **Brightness** | The LCD backlight intensity level for the device screen, ranging from 0 (off) to 100 (maximum). | `StreamDock.set_brightness()` |
| **Canvas** | The internal representation of the 288x288 pixel area for rendering a single key icon or background image. | Image helpers |
| **CRT Protocol** | The custom transport protocol signature used by StreamDock devices, characterized by 513-byte packets with a 3-byte ASCII command header (e.g., `LIG` for lighting/image, `CLE` for clear). All packets are prefixed with report ID `0x02`. See ADR-002 for full protocol specification. | `HIDTransport`, ADR-002 |
| **Device** | The physical Stream Dock 293v3 hardware unit connected via USB. | `StreamDock`, `DeviceManager` |
| **HID Transport** | Low-level communication layer using USB Human Interface Device (HID) protocol via `libhidapi-libusb` to send/receive raw data packets. | `HIDTransport`, `transport/` |
| **Key** | A specific hardware button (1-15 on the 293v3 model) with associated visual (icon, label) and behavioral (action callbacks) data. Each key can have separate callbacks for press, release, and double-press events. | `Key` class |
| **Key Mapping** | The translation between physical key numbers (1-15, hardware layout) and logical key numbers (used internally for callback registration). Required because the hardware reports keys in a different order than their physical arrangement. | `Key.KEY_MAPPING` (dict) |
| **Layout** | A complete configuration set containing 1-15 key definitions and optional background image that can be applied to the device simultaneously. | `Layout` class |
| **Packet** | A 513-byte unit of communication sent to/from the hardware, consisting of: 1 byte report ID (always `0x02`), 3-byte ASCII command, 509 bytes data/padding. | `HIDTransport._create_packet()` |
| **Stream Dock 293v3** | The specific hardware model supported by this project (identified by VID/PID). | `product_ids.py` |

## Action System

| Term | Definition | Related Classes/Modules |
| :--- | :--- | :--- |
| **ActionType** | Enumeration of all supported action types: `execute_command`, `key_press`, `type_text`, `wait`, `change_key_image`, `change_key_text`, `change_key`, `change_layout`, `dbus`, `device_brightness_up`, `device_brightness_down`, `launch_application`. | `ActionType` enum |
| **Change Key** | Action that updates a key's visual appearance and/or callbacks dynamically. | `ActionType.CHANGE_KEY` |
| **Change Layout** | Action that switches the entire device configuration to a different layout. | `ActionType.CHANGE_LAYOUT` |
| **D-Bus Action** | System integration action using D-Bus for media control (play/pause, next/previous), volume control (up/down, mute), and other system services. | `ActionType.DBUS`, `send_dbus_command()` |
| **Desktop File** | Standard Linux `.desktop` file format used to parse application metadata for launch actions. | `parse_desktop_file()` |
| **Double-Press** | Key event triggered when a key is pressed twice within a configured time interval (default: 0.3s). Detected by tracking time between consecutive press events on the same key. | `DEFAULT_DOUBLE_PRESS_INTERVAL` (0.3s) |
| **Execute Command** | Action that launches a system command using subprocess with full detachment via `nohup` and shell backgrounding. The launched process survives even if StreamDock exits, and output is redirected to `/dev/null`. | `execute_command()` |
| **Key Press** | Action that emulates keyboard input using `xdotool` or `kdotool`. | `emulate_key_combo()` |
| **Launch or Focus** | Smart application action that checks if an application is running (via `pgrep`), focuses its window if found (via `WindowUtils`), or launches it if not. Supports `.desktop` files, commands, and custom window matching. | `launch_or_focus_application()` |
| **Type Text** | Action that simulates typing text character-by-character with case sensitivity. | `type_text()` |

## Window Management & Detection

| Term | Definition | Related Classes/Modules |
| :--- | :--- | :--- |
| **Active Window** | The window currently receiving keyboard input and user focus. | `WindowMonitor.get_active_window_info()` |
| **AppPattern** | Pattern definition for detecting and normalizing application names from raw class names and titles. | `AppPattern` dataclass |
| **Class Name** | The window class identifier (e.g., `org.kde.kate`, `firefox`, `chromium-browser`) used for matching. | `WindowInfo.class_` |
| **Detection Method** | Strategy pattern implementation for detecting active windows using different tools (kdotool, KWin scripting, xdotool, etc.). | `DetectionMethod` abstract class |
| **KdotoolDetection** | Detection strategy using `kdotool` command-line tool (best for KDE Wayland). | `KdotoolDetection` |
| **KWin Dynamic Scripting** | Advanced detection using dynamically generated KWin scripts with unique UUID markers for reliable parsing. Each query generates a new script to avoid stale data. Requires `journalctl` for script output retrieval. More reliable than basic KWin detection but slower. | `KWinDynamicScriptingDetection` |
| **KWin Scripting** | Detection method that loads temporary JavaScript into KWin window manager to query active window. | `KWinDynamicScriptingDetection`, `KWinBasicDetection` |
| **MatchField** | Enum specifying which window property to match against (`title`, `class`, `raw`). | `MatchField` enum |
| **Normalized Name** | Standardized application name extracted from raw window class/title (e.g., "Firefox", "Chrome", "VSCode"). | `WindowUtils.normalize_app_name()` |
| **Simulation Mode** | Testing mode that reads active window info from a file instead of querying the system. | `SimulationDetection` |
| **Window Focus** | The state where a specific application window is the active input target. | Window monitoring system |
| **WindowInfo** | Dataclass containing comprehensive window metadata: `title` (window title), `class_` (window class/app name), `window_id` (unique identifier), `pid` (process ID, for debugging only), `method` (detection method used), `timestamp` (detection time). Includes backward compatibility via `class_name` property and `to_dict()` method. | `WindowInfo` dataclass |
| **Window Monitor** | Background service that continuously polls for active window changes (default: 0.5s interval) and triggers callbacks based on window rules. Runs detection in a separate thread and caches the last window to avoid redundant callbacks. Supports simulation mode for testing. | `WindowMonitor` class |
| **Window Rule** | Pattern-based rule that matches window properties and executes a callback (typically to switch layouts). | `WindowRule` dataclass |
| **WindowUtils** | Utility class providing unified interface for window operations across Wayland/KDE and X11 environments. | `WindowUtils` class |
| **XWindowDetection** | Fallback detection using X11 tools (`xdotool` + `xprop`) for non-Wayland environments. | `XWindowDetection` |

## Configuration & State Management

| Term | Definition | Related Classes/Modules |
| :--- | :--- | :--- |
| **Clear All** | Operation that removes all key icons and callbacks from the device at once. | `Layout.clear_all` |
| **Clear Keys** | List of specific key numbers to clear (set to empty/blank) when applying a layout. | `Layout.clear_keys` |
| **Config Loader** | Component responsible for parsing YAML configuration files and constructing runtime objects (Keys, Layouts, Window Rules). Performs validation, action parsing, and layout reference resolution. The config loader acts as the bridge between declarative YAML and the imperative runtime system. | `ConfigLoader` class |
| **ConfigValidationError** | Exception raised when YAML configuration structure or content is invalid. | `ConfigValidationError` |
| **Default Layout** | The initial layout applied when the device starts or when no window rules match. | `ConfigLoader.apply()` |
| **Layout Switch** | The atomic operation of replacing the entire device state (all 15 keys plus background) based on a trigger event (window change, manual action, etc.). Involves clearing old callbacks, setting new images, registering new callbacks, and refreshing display. Callback reference from the previous layout is preserved if the new layout doesn't override it. | `ConfigLoader.switch_to_layout()` |
| **On Press Actions** | List of actions executed when a key is pressed down. | Key configuration |
| **On Release Actions** | List of actions executed when a key is released. | Key configuration |
| **On Double Press Actions** | List of actions executed when a key is double-pressed within the threshold interval. | Key configuration |
| **Settings** | Global device configuration section containing brightness and other device-level preferences. | YAML `settings:` section |
| **YAML Configuration** | The primary configuration file format defining keys, layouts, window rules, and device settings. | `config_loader.py` |

## System Integration

| Term | Definition | Related Classes/Modules |
| :--- | :--- | :--- |
| **D-Bus** | Inter-process communication system used for desktop integration. StreamDock uses D-Bus for: (1) Screen lock/unlock detection via `org.freedesktop.ScreenSaver`, (2) Media player control via MPRIS2 (`org.mpris.MediaPlayer2`), (3) Volume control via PulseAudio. Requires either `dbus-send` or `qdbus`/`qdbus6` to be installed. | `lock_monitor.py`, `send_dbus_command()` |
| **D-Bus Signal** | An asynchronous notification broadcast via D-Bus to inform applications of system state changes. | Lock monitor |
| **Dependency** | Required or optional system tool or Python package needed for functionality. | `Dependency` dataclass |
| **DependencyChecker** | Utility that verifies all required and optional dependencies are installed. | `DependencyChecker` class |
| **GLib Main Loop** | Event loop from GLib used for asynchronous D-Bus signal handling. | `lock_monitor.py` |
| **hidapi** | Low-level C library (`libhidapi-libusb0`) for USB HID device communication. StreamDock uses the libusb backend (not hidraw) to avoid kernel driver conflicts. All hidapi functions are called via ctypes bindings defined in `lib_usb_hid_api.py`. See ADR-001 for rationale. | `lib_usb_hid_api.py`, ADR-001 |
| **Lock Monitor** | Component that detects system lock/unlock events via D-Bus signals and manages device screen state accordingly. On lock: turns screen off while keeping HID handle open. On unlock: attempts to wake existing handle, falls back to device reopen if handle is stale. Includes lock verification delay (default 2s) to handle user-aborted locks. | `LockMonitor` class |
| **Lock Verification** | Delayed check (default 2 seconds after lock signal) to confirm screen lock actually completed. Handles race condition where lock event fires but user moves mouse/keyboard to abort. Verification polls `org.freedesktop.ScreenSaver.GetActive()` D-Bus method to confirm actual lock state before turning off device. | `LockMonitor._verify_and_handle_lock()` |
| **pactl** | PulseAudio/PipeWire command-line tool for volume control actions. | `actions.py` |
| **Polling** | Periodic checking method (fallback when event-driven approach unavailable). | `WindowMonitor.poll_interval` |
| **pyudev** | Python bindings for udev, used to monitor USB device connection/disconnection events in real-time. The `DeviceManager` uses `pyudev.Monitor.from_netlink()` to watch for `add`/`remove` events on the `usb` subsystem, automatically opening new devices and cleaning up removed devices. | `DeviceManager.listen()` |
| **Screen Lock** | System state where user authentication is required, triggering device screen-off. | `LockMonitor` |
| **Screen Off** | Device state where display is blanked but HID connection remains active. | `StreamDock.screen_off()` |
| **Screen On** | Device state where display is active and showing content. | `StreamDock.screen_on()` |
| **Tool Availability Cache** | Module-level cached boolean flags for system tool availability checks (kdotool, xdotool, wmctrl, dbus-send, pactl). Caching prevents expensive `shutil.which()` calls on every action execution. Cache can be refreshed via `WindowUtils.refresh_tool_cache()` if tools are installed/uninstalled at runtime. | `WindowUtils` module variables |
| **udev** | Linux device manager that sends events when hardware is connected/disconnected. | `DeviceManager.listen()` |
| **Wake Screen** | Operation to reactivate device display after screen-off state. | `StreamDock.wake_screen()` |
| **wmctrl** | Legacy window management tool used as fallback for window activation. | `WindowUtils.wmctrl_activate_window()` |
| **xdotool** | X11 automation tool for simulating keyboard/mouse input and window manipulation. | `WindowUtils`, `actions.py` |

## Architecture & Internal Mechanisms

| Term | Definition | Related Classes/Modules |
| :--- | :--- | :--- |
| **Callback** | Function executed in response to key events or window changes. Key callback signature: `callback(device, key)` where `device` is `StreamDock` instance and `key` is the logical key number. Window rule callback signature: `callback(window_info)` where `window_info` is a `WindowInfo` dict. All callbacks run in worker threads, not the main thread. | Key system, `WindowRule` |
| **Circuit Breaker** | Design pattern for automatic failure handling that disables a mechanism after repeated failures. Detection methods implement this by tracking consecutive failures (via `_failure_count`) and auto-disabling after threshold (default: 3 failures). Prevents wasted CPU cycles on broken detection methods. | `DetectionMethod` |
| **Device Manager** | Coordinator for enumerating, opening, and monitoring multiple StreamDock devices. Uses transport layer (LibUSBHIDAPI or MockTransport) to enumerate devices, opens them automatically on detection, and monitors via udev for hot-plug events. Maintains a list of active devices in `self.streamdocks`. | `DeviceManager` class |
| **Event Queue** | Thread-safe `queue.Queue` for dispatching callbacks to worker threads. Key events from HID reader thread are placed in this queue and consumed by worker threads. Allows non-blocking callback execution so HID reader doesn't stall waiting for callbacks to complete. | `StreamDock._event_queue` |
| **Failure Counter** | Counter tracking consecutive detection failures before auto-disabling a method. | `DetectionMethod._failure_count` |
| **Mock Device** | Simulated device implementation for testing without physical hardware. | `MockDevice`, `MockTransport` |
| **Priority** | Numeric value determining the order in which window rules are evaluated (higher = checked first). | `WindowRule.priority` |
| **Reader Thread** | Background daemon thread that continuously reads HID events from the device in a blocking loop. Parses incoming packets, determines which key was pressed/released, and dispatches appropriate callbacks via the event queue. Auto-restarts if terminated while device is open. | `StreamDock._setup_reader()` |
| **Rule Engine** | Component managing window rules with priority-based evaluation. Rules are sorted by priority (higher first), then by insertion order. On window change, iterates through sorted rules, executes the first match, and stops. Falls back to default callback if no rules match. | `RuleEngine` class |
| **Strategy Pattern** | Object-oriented design pattern used for detection methods. Abstract base class (`DetectionMethod`) defines interface (`detect()`, `is_available()`, etc.) and concrete implementations (`KdotoolDetection`, `KWinDynamicScriptingDetection`, etc.) provide algorithm-specific logic. Allows runtime selection and fallback between detection strategies. | `DetectionMethod` hierarchy |
| **Thread Pool** | Collection of worker threads (default: 4) processing key callbacks asynchronously from the event queue. Each thread runs `_worker_loop()` which blocks on queue.get(), executes the callback, and repeats. Prevents callback delays from blocking HID event processing. | `StreamDock` workers (DEFAULT_WORKER_THREADS=4) |
| **Transport Error** | Exception class for HID communication failures with optional error codes. | `TransportError` |
| **Worker Thread** | Background thread from thread pool that executes callbacks from event queue. | `StreamDock._worker_loop()` |

## Image & Visual Elements

| Term | Definition | Related Classes/Modules |
| :--- | :--- | :--- |
| **Background Image** | Full-device image visible behind/around the individual key icons. | `HIDTransport.set_background_img()` |
| **CairoSVG** | Library for rendering SVG vector graphics to raster images. | Image helpers |
| **Image Format** | Required format for key images: JPEG encoding, 288x288 pixels for 293v3 model. Images are automatically resized and converted to JPEG by image helpers. Other formats (PNG, SVG, etc.) are accepted as input but converted before sending to device. | Device specification (293v3) |
| **Image Helper** | Utility module for image processing, conversion, and rendering. | `image_helpers/` |
| **Key Flip** | Boolean tuple indicating whether key images should be flipped horizontally/vertically. | `StreamDock.KEY_FLIP` |
| **Key Pixel Dimensions** | Resolution of individual key display area (288x288 for 293v3). | `StreamDock.KEY_PIXEL_WIDTH/HEIGHT` |
| **Key Rotation** | Angle in degrees to rotate key images during rendering. | `StreamDock.KEY_ROTATION` |
| **PIL Helper** | Pillow-based utilities for image manipulation and format conversion. | `pil_helper.py` |
| **Refresh** | Operation that commits pending visual changes and updates the physical device display. Sends a special packet to the device to flush the display buffer. Called automatically after `Layout.apply()` or can be called manually after individual `set_key_image()` calls. | `StreamDock.refresh()` |
| **Temporary Text Image** | Dynamically generated PNG image file created from text configuration for key labels. The ConfigLoader generates these images using PIL when a key specifies `text:` instead of `image:`. Files are stored temporarily and cleaned up on ConfigLoader destruction. | `ConfigLoader` temp files |

## Error Handling & Reliability

| Term | Definition | Related Classes/Modules |
| :--- | :--- | :--- |
| **Auto-Disable** | Automatic deactivation of a detection method after exceeding failure threshold. | `DetectionMethod.disable()` |
| **Fallback Chain** | Ordered sequence of detection methods tried sequentially until one succeeds. Default order: (1) KdotoolDetection, (2) KWinDynamicScriptingDetection, (3) PlasmaTaskManagerDetection, (4) KWinBasicDetection, (5) XWindowDetection. As methods fail and auto-disable, later methods in chain are tried. | `WindowMonitor` detection strategy list |
| **Failure Threshold** | Maximum number of consecutive failures before a detection method is disabled (default: 3). | `DetectionMethod.MAX_FAILURES` |
| **Handle Stale** | Condition where HID device handle becomes invalid (typically after system sleep/wake cycle or device reconnection). Manifests as failed write operations. Lock monitor handles this by attempting graceful wake, then falling back to close/reopen if write fails. | `LockMonitor` recovery logic |
| **Recovery** | Process of re-establishing device connection after failure or system state change. | `LockMonitor._reopen_device_and_restore()` |
| **Timeout** | Maximum duration to wait for a command/operation to complete before considering it failed. | Detection methods, HID operations |

## Testing & Development

| Term | Definition | Related Classes/Modules |
| :--- | :--- | :--- |
| **Fixture** | Test setup/teardown component providing consistent test environment. | Test suite |
| **Mock Mode** | Testing mode using simulated device and transport instead of real hardware. | `MockDevice`, `MockTransport` |
| **Unit Test** | Isolated test verifying a single component's behavior with mocked dependencies. | `tests/` directory |

---

## Abbreviations & Acronyms

| Term | Full Form | Context |
| :--- | :--- | :--- |
| **ADR** | Architecture Decision Record | Documentation of significant design decisions |
| **API** | Application Programming Interface | Interface contracts for modules |
| **HID** | Human Interface Device | USB device class for keyboards, mice, etc. |
| **KDE** | K Desktop Environment | Linux desktop environment (Plasma) |
| **PID** | Process ID | Operating system process identifier |
| **PIL** | Python Imaging Library | Image processing library (Pillow fork) |
| **RGB** | Red-Green-Blue | Color representation format |
| **SVG** | Scalable Vector Graphics | Vector image format |
| **UCB1** | Upper Confidence Bound | Algorithm for multi-armed bandit problems |
| **USB** | Universal Serial Bus | Hardware connection standard |
| **VID** | Vendor ID | USB device vendor identifier |
| **YAML** | YAML Ain't Markup Language | Configuration file format |

---

## Platform-Specific Terms

### Wayland/KDE

| Term | Definition |
| :--- | :--- |
| **kdotool** | Command-line tool for window manipulation on Wayland/KDE, similar to xdotool for X11 |
| **KWin** | KDE's window manager for Wayland and X11 |
| **Plasma** | KDE's desktop environment (Plasma 5, Plasma 6) |
| **qdbus / qdbus6** | Qt D-Bus command-line tools (Qt5/Qt6 versions) |

### X11

| Term | Definition |
| :--- | :--- |
| **Window ID** | Unique hexadecimal identifier for X11 windows |
| **xprop** | X11 tool for querying window properties |

---

## Usage Guide for AI-Assisted Development

This section provides guidance on how to effectively use this glossary during AI-assisted development, debugging, and code generation tasks.

### Quick Reference Patterns

When working on different types of tasks, reference these glossary sections:

| Task Type | Relevant Sections | Key Terms to Know |
| :--- | :--- | :--- |
| **Adding new actions** | Action System, System Integration | ActionType, execute_actions(), launch_or_focus_application() |
| **Window detection issues** | Window Management & Detection, Error Handling | DetectionMethod, WindowInfo, Fallback Chain, Circuit Breaker |
| **Layout/key configuration** | Configuration & State Management, Core Hardware | Layout, Key, ConfigLoader, Key Mapping |
| **Device communication** | Core Hardware, Architecture | HID Transport, CRT Protocol, Packet, Event Queue |
| **Lock/unlock behavior** | System Integration, Error Handling | Lock Monitor, Lock Verification, Handle Stale, D-Bus |
| **Testing** | Testing & Development, Architecture | Mock Device, Mock Transport, Simulation Mode |

### Common Development Scenarios

#### Scenario 1: Implementing a New Action Type

1. Understand **ActionType** enum structure
2. Study **execute_action()** function in `actions.py`
3. Reference existing action implementations (e.g., **Execute Command**, **Launch or Focus**)
4. Consider impact on **YAML Configuration** schema
5. Update **ConfigLoader** validation if needed

#### Scenario 2: Debugging Window Detection Failures

1. Check **WindowInfo** structure returned by detection
2. Review **Detection Method** implementations and their availability
3. Understand **Fallback Chain** order and **Circuit Breaker** logic
4. Examine **Tool Availability Cache** for missing dependencies
5. Enable **Simulation Mode** for reproducible testing

#### Scenario 3: Adding Device Support

1. Study **Stream Dock 293v3** specifications
2. Understand **CRT Protocol** packet structure
3. Examine **Device Manager** enumeration logic
4. Review **HID Transport** implementation
5. Consider **Key Mapping** differences between models

### Cross-Reference Tips

- Terms in **ALL CAPS** within definitions refer to other glossary entries
- Module/class references in rightmost column link to source files
- ADR references (e.g., ADR-001, ADR-002) point to Architecture Decision Records
- When uncertain about a term's usage, search codebase for the Referenced Class/Module

### Code Generation Guidelines

When generating code:

1. **Use exact terminology**: Reference the "Term" column for precise naming
2. **Follow patterns**: Study "Related Classes/Modules" before implementing
3. **Maintain consistency**: Use the same abstractions as existing code (e.g., always use `WindowUtils` for window operations, not direct `kdotool` calls)
4. **Respect architecture**: Understand component relationships (e.g., `ConfigLoader` → `Layout` → `Key` → `StreamDock`)

### Integration Examples

**Example 1: Adding a Window Rule**
```python
# Reference: WindowRule, WindowMonitor, MatchField
window_monitor.add_window_rule(
    pattern="firefox",           # Matches class name
    callback=switch_to_firefox_layout,
    match_field=MatchField.CLASS,
    priority=10
)
```

**Example 2: Creating a Custom Action**  
```python
# Reference: ActionType, execute_action()
from StreamDock.actions import ActionType

custom_action = (ActionType.EXECUTE_COMMAND, "notify-send 'Hello'")
execute_action(custom_action, device=my_device)
```

**Example 3: Window Detection with Fallback**
```python
# Reference: DetectionMethod, WindowUtils, WindowInfo
methods = [KdotoolDetection(), XWindowDetection()]
for method in methods:
    if method.is_available():
        window_info = method.detect()
        if window_info:
            break
```

### Maintenance Guidelines

When updating this glossary:

1. **Add new terms** introduced by features/refactoring
2. **Update definitions** when implementation details change
3. **Maintain cross-references** between related terms
4. **Include practical context** (defaults, common patterns, gotchas)
5. **Link to ADRs** for architectural decisions

---

> [!TIP]
> When adding new features or classes, update this glossary to maintain project-wide consistency. Use these standardized terms in code comments, documentation, and variable names to ensure AI-assisted development tools have accurate context.

> [!IMPORTANT]
> For AI Development: This glossary serves as the canonical reference for domain terminology. When generating code, prioritize using these exact terms and their associated classes/modules to maintain consistency with the existing codebase architecture.

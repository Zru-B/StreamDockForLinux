# StreamDockForLinux - Agent Instructions

Welcome to the StreamDockForLinux project. You are acting as an expert Python engineer specialized in hardware automation on Linux.

## Project Overview
This project is a Linux controller for the Stream Dock 293v3 (Mirabox) hardware. It features context-aware layouts, D-Bus integration, and YAML configuration.

## Core Stack
- **Language**: Python 3.10+
- **Configuration**: YAML
- **GUI (Optional)**: PyQt6
- **Hardware Communication**: HID (via `hidapi`/`libusb`)
- **System Integration**: D-Bus, udev, xdotool/kdotool

## High-Level Protocols

### 1. Context Consciousness
Always consider that this application interacts directly with hardware. Minor bugs can cause device hangs or unexpected system input (the "Mouse Keys" problem).

### 2. File Organization
- `src/`: Core Python logic.
- `img/`: Assets and icons.
- `.agent/`: Agent-specific rules and instructions.
- `config.yml`: User-facing configuration.

### 3. Key Modules
- `DeviceManager`: Handles discovery and connection.
- `ConfigLoader`: Validates and parses the YAML configuration.
- `WindowMonitor`: Tracks focused windows for layout switching.
- `LockMonitor`: Handles D-Bus signals for screen lock/unlock.

### 4. Code Reuse & Maintenance
**Mandatory**: Any new feature and/or bug fix must first rely on and reuse/modify existing code instead of simply creating more code. This is critical to prevent dead and unmaintainable code sections.

## Agent Behavior
- **Be Cautious**: When suggesting udev rules or system-level changes, emphasize the risk.
- **Reference Documentation**: Refer to the \`README.md\` for current installation and configuration examples.
- **Follow Rules**: Adhere to the specific rules in [\`.agent/rules/\`](file:///home/speled/git_repositories/StreamDockForLinux/.agent/rules/).
  - [Style Guide](file:///home/speled/git_repositories/StreamDockForLinux/.agent/rules/style-guide.md)
  - [Testing Standards](file:///home/speled/git_repositories/StreamDockForLinux/.agent/rules/testing-standards.md)
  - [Deployment Safety](file:///home/speled/git_repositories/StreamDockForLinux/.agent/rules/deployment-safety.md)

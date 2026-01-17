# ADR-001: Use of hidapi via ctypes

- **Status**: Accepted
- **Date**: 2026-01-15

## Context
The Stream Dock 293v3 (Mirabox) hardware communicates over USB HID. Traditional Linux methods like `hidraw` can suffer from permission issues, kernel driver conflicts (e.g., `hid-generic` grabbing the device), and inconsistent behavior across distributions.

## Decision
We use the `libhidapi-libusb.so` library via Python's `ctypes`. This allows us to:
1.  Bypass the kernel's generic HID driver if needed.
2.  Use a stable, well-understood C library for HID communication.
3.  Avoid heavy Python dependencies for low-level byte manipulation.

## Consequences
- **Requirements**: The system must have `libhidapi-libusb0` (or similar) installed.
- **Complexity**: Manual memory management and argument type mapping via `ctypes` is required.
- **Interaction**: We must ensure udev rules correctly identify the device and potentially unbind it from `hid-generic` to allow the application to claim the interface.

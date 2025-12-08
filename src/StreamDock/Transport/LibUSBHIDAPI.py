"""
LibUSBHIDAPI module - Pure Python HID transport for StreamDock devices.

This module now uses a pure Python implementation instead of the native
libtransport.so library, providing cross-platform compatibility.
"""

from .HIDTransport import HIDTransport

# Re-export HIDTransport as LibUSBHIDAPI for backward compatibility
LibUSBHIDAPI = HIDTransport

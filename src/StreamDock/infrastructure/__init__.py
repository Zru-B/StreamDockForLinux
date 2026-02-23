"""
Infrastructure layer for StreamDock.

This package provides hardware and system abstractions for the StreamDock application,
following the layered architecture design.
"""

from .device_registry import DeviceRegistry, TrackedDevice
from .hardware_interface import DeviceInfo, HardwareInterface, InputEvent
from .linux_system_interface import LinuxSystemInterface
from .system_interface import SystemInterface, WindowInfo
from .usb_hardware import USBHardware

__all__ = [
    'HardwareInterface', 'DeviceInfo', 'InputEvent', 'USBHardware',
    'SystemInterface', 'WindowInfo', 'LinuxSystemInterface',
    'DeviceRegistry', 'TrackedDevice'
]

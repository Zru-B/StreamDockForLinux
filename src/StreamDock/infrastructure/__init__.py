"""
Infrastructure layer for StreamDock.

See README.md in this directory for layer rules and key abstractions.
"""

from .device_registry import DeviceRegistry, TrackedDevice
from .hardware_interface import DeviceInfo, HardwareInterface, InputEvent
from .linux_system_interface import LinuxSystemInterface
from .linux_window_manager import LinuxWindowManager
from .system_interface import SystemInterface, WindowInfo
from .usb_hardware import USBHardware
from .usb_hotplug_monitor import USBHotplugMonitor
from .window_interface import WindowInterface

__all__ = [
    'HardwareInterface', 'DeviceInfo', 'InputEvent', 'USBHardware',
    'SystemInterface', 'WindowInfo', 'WindowInterface',
    'LinuxSystemInterface', 'LinuxWindowManager',
    'DeviceRegistry', 'TrackedDevice',
    'USBHotplugMonitor',
]

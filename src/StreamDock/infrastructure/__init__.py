"""
Infrastructure layer for StreamDock.

This package provides hardware and system abstractions for the StreamDock application,
following the layered architecture design.
"""

from .hardware_interface import HardwareInterface, DeviceInfo, InputEvent
from .usb_hardware import USBHardware

__all__ = ['HardwareInterface', 'DeviceInfo', 'InputEvent', 'USBHardware']

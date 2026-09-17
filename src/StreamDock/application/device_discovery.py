"""
Device discovery.

Enumeration is deliberately available without building an Application: the GUI
needs to populate its device picker before anything is connected, and the
headless entry point needs to resolve a --device argument up front.
"""

import logging
from typing import List, Optional

from StreamDock.devices.product_ids import STREAMDOCK_VID, SUPPORTED_PIDS
from StreamDock.infrastructure import HardwareInterface, USBHardware
from StreamDock.infrastructure.hardware_interface import DeviceInfo

logger = logging.getLogger(__name__)


def discover_devices(hardware: Optional[HardwareInterface] = None) -> List[DeviceInfo]:
    """
    Enumerate every supported Stream Dock currently attached.

    Args:
        hardware: Hardware abstraction to enumerate through. A throwaway
            USBHardware is created when omitted - enumeration does not open
            anything, so this is safe to call while a device is already open.

    Returns:
        Discovered devices, in enumeration order. Empty on any failure.
    """
    hardware = hardware or USBHardware()

    devices: List[DeviceInfo] = []
    for product_id in SUPPORTED_PIDS:
        try:
            devices.extend(hardware.enumerate_devices(STREAMDOCK_VID, product_id))
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error enumerating %04x:%04x: %s", STREAMDOCK_VID, product_id, e)

    logger.debug("Discovered %d device(s)", len(devices))
    return devices


def device_key(device: DeviceInfo) -> str:
    """
    Build a selector key that is unique among the attached devices.

    DeviceInfo.device_id is VID:PID:serial, but this hardware reports an empty
    serial, so two identical docks share one id. Fall back to the USB path in
    that case - it is unique while both are plugged in, which is all a device
    picker needs.

    Args:
        device: Discovered device

    Returns:
        Key suitable for identifying this device in a UI or on the CLI
    """
    if device.serial_number:
        return device.device_id
    return f"{device.vendor_id:04x}:{device.product_id:04x}@{device.path}"


def device_label(device: DeviceInfo) -> str:
    """
    Build a human-readable name for a device picker entry.

    Args:
        device: Discovered device

    Returns:
        Display string, e.g. 'Stream Dock 293v3 (1-3:1.0)'
    """
    name = device.product or device.manufacturer or "Stream Dock"
    detail = device.serial_number or device.path
    return f"{name} ({detail})" if detail else name


def find_device(device_id: str,
                hardware: Optional[HardwareInterface] = None) -> Optional[DeviceInfo]:
    """
    Look up a single device by device_key() or by DeviceInfo.device_id.

    Both forms are accepted so a --device value copied from either the GUI or
    a log line resolves.

    Args:
        device_id: Key from device_key(), or a '6603:1006:<serial>' device_id
        hardware: Optional hardware abstraction, as for discover_devices()

    Returns:
        The matching device, or None if it is no longer attached.
    """
    for device in discover_devices(hardware):
        if device_id in (device_key(device), device.device_id):
            return device

    logger.debug("Device not found: %s", device_id)
    return None

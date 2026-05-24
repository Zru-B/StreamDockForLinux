"""
Device registry for path-independent device tracking.

This module provides the DeviceRegistry class that tracks devices by their
stable identifiers (VID:PID:Serial) instead of volatile USB paths, enabling
automatic reconnection when devices are unplugged and replugged.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

from .hardware_interface import DeviceInfo, HardwareInterface

logger = logging.getLogger(__name__)


@dataclass
class TrackedDevice:
    """
    Information about a tracked device.

    This class maintains both the current device information and the
    actual device instance, allowing us to track devices even when
    they become temporarily disconnected.

    Attributes:
        device_info: Current device information (includes path)
        device_instance: Actual device object (e.g., StreamDock293V3)
        last_seen: Timestamp when device was last detected
        is_connected: Whether device is currently connected
    """
    device_info: DeviceInfo
    device_instance: Any
    last_seen: float = field(default_factory=time.time)
    is_connected: bool = True


class DeviceRegistry:
    """
    Registry for managing devices with path-independent tracking.

    This class solves the device reconnection problem by tracking devices
    using stable identifiers (VID:PID:Serial) instead of USB paths that
    can change when devices are unplugged and replugged.

    Key Features:
    - Tracks devices by device_id (VID:PID:Serial) not by path
    - Automatically reconnects devices when they reappear with new paths
    - Maintains device registry even when devices are disconnected
    - Supports multiple devices of the same model (different serials)

    Design Pattern: Registry pattern with stable key-based lookup
    """

    def __init__(self, hardware_interface: HardwareInterface):
        """
        Initialize device registry.

        Args:
            hardware_interface: Hardware abstraction for device communication
        """
        self._hardware = hardware_interface
        self._devices: Dict[str, TrackedDevice] = {}  # device_id -> TrackedDevice
        logger.debug("DeviceRegistry initialized")

    def enumerate_and_register(self, vid: int, pid: int, device_class: Type) -> List[Any]:
        """
        Enumerate devices and register them with auto-reconnection.

        For each discovered device:
        1. Check if already registered (by stable device_id)
        2. If registered but disconnected or path changed: reconnect
        3. If not registered: create new device instance and register

        This method is the core of auto-reconnection: when a device reappears
        with a different USB path but same VID:PID:Serial, it will be
        recognized and reconnected automatically.

        Args:
            vid: USB Vendor ID to enumerate
            pid: USB Product ID to enumerate
            device_class: Device class to instantiate (e.g., StreamDock293V3)

        Returns:
            List of device instances (both existing and newly created)

        Design Contract:
            - Same device (by serial) always returns same instance
            - Device instances persist across reconnections
            - Caller can safely cache returned instances
        """
        devices_info = self._hardware.enumerate_devices(vid, pid)
        logger.debug("Enumerated %d devices for VID=0x%04x, PID=0x%04x", len(devices_info), vid, pid)

        result = []

        for device_info in devices_info:
            device_id = device_info.device_id  # Stable: VID:PID:Serial

            if device_id in self._devices:
                # Known device - check if reconnection needed
                tracked = self._devices[device_id]

                # Reconnect if: (1) marked disconnected OR (2) path changed
                needs_reconnect = (
                    not tracked.is_connected or
                    tracked.device_info.path != device_info.path
                )

                if needs_reconnect:
                    logger.info(
                        "Reconnecting device %s: %s -> %s",
                        device_id,
                        tracked.device_info.path,
                        device_info.path
                    )

                    # Update device info with new path
                    tracked.device_info = device_info
                    tracked.is_connected = True
                    tracked.last_seen = time.time()

                    # Reopen device at new path
                    if self._reopen_device(tracked):
                        logger.info("Device %s successfully reconnected", device_id)
                    else:
                        logger.error("Failed to reconnect device %s", device_id)
                        tracked.is_connected = False
                else:
                    # Device already connected at same path - just update timestamp
                    tracked.last_seen = time.time()
                    logger.debug("Device %s already connected at %s", device_id, device_info.path)

                result.append(tracked.device_instance)

            else:
                # New device - create instance and register
                logger.info("Registering new device %s at %s", device_id, device_info.path)

                try:
                    device_instance = device_class(self._hardware, device_info)
                    tracked = TrackedDevice(
                        device_info=device_info,
                        device_instance=device_instance,
                        is_connected=True
                    )
                    self._devices[device_id] = tracked
                    result.append(device_instance)
                    logger.debug("Device %s registered successfully", device_id)

                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.error("Failed to create device instance for %s: %s", device_id, e, exc_info=True)

        return result

    def get_device(self, device_id: str) -> Optional[Any]:
        """
        Get device instance by stable device ID.

        Args:
            device_id: Stable device identifier (VID:PID:Serial)

        Returns:
            Device instance if registered, None otherwise

        Design Contract:
            - Returns same instance for same device_id across calls
            - Returns None if device never registered
            - Returns instance even if device currently disconnected
        """
        tracked = self._devices.get(device_id)
        if tracked:
            logger.debug("Retrieved device %s", device_id)
            return tracked.device_instance
        
        logger.debug("Device %s not found in registry", device_id)
        return None

    def get_all_devices(self) -> List[Any]:
        """
        Get all registered device instances.

        Returns:
            List of all device instances (includes disconnected devices)

        Design Contract:
            - Includes both connected and disconnected devices
            - Order is not guaranteed
        """
        devices = [tracked.device_instance for tracked in self._devices.values()]
        logger.debug("Retrieved %d devices from registry", len(devices))
        return devices

    def get_connected_devices(self) -> List[Any]:
        """
        Get only currently connected device instances.

        Returns:
            List of connected device instances
        """
        devices = [
            tracked.device_instance
            for tracked in self._devices.values()
            if tracked.is_connected
        ]
        logger.debug("Retrieved %d connected devices", len(devices))
        return devices

    def mark_disconnected(self, device_id: str) -> None:
        """
        Mark a device as disconnected without removing from registry.

        This is a soft disconnection - the device remains in the registry
        and will auto-reconnect when it reappears.

        Args:
            device_id: Stable device identifier

        Design Contract:
            - Device remains in registry after marking disconnected
            - Future enumerate_and_register() will reconnect
            - Safe to call multiple times
        """
        if device_id in self._devices:
            self._devices[device_id].is_connected = False
            logger.info("Device %s marked as disconnected", device_id)
        else:
            logger.warning("Attempted to mark unknown device %s as disconnected", device_id)

    def remove_device(self, device_id: str) -> None:
        """
        Permanently remove device from registry.

        Use this when you want to completely forget about a device.
        If the device reappears, it will be treated as a new device.

        Args:
            device_id: Stable device identifier

        Design Contract:
            - Device completely removed from registry
            - Future enumerate_and_register() will create new instance
            - Safe to call even if device not in registry
        """
        if device_id in self._devices:
            del self._devices[device_id]
            logger.info("Device %s removed from registry", device_id)
        else:
            logger.debug("Attempted to remove unknown device %s", device_id)

    def get_device_count(self) -> int:
        """
        Get total number of registered devices.

        Returns:
            Number of devices in registry (includes disconnected)
        """
        return len(self._devices)

    def is_device_connected(self, device_id: str) -> bool:
        """
        Check if a device is currently connected.

        Args:
            device_id: Stable device identifier

        Returns:
            True if device is registered and connected, False otherwise
        """
        tracked = self._devices.get(device_id)
        return tracked.is_connected if tracked else False

    def _reopen_device(self, tracked: TrackedDevice) -> bool:
        """
        Reopen device at new path.

        This is called during reconnection to open the device
        communication channel at the new USB path.

        Args:
            tracked: TrackedDevice to reopen

        Returns:
            True if successfully reopened, False otherwise
        """
        try:
            success = self._hardware.open_device(tracked.device_info)
            if success:
                logger.debug("Device reopened at %s", tracked.device_info.path)
            else:
                logger.warning("Failed to reopen device at %s", tracked.device_info.path)
            return success
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error reopening device: %s", e, exc_info=True)
            return False

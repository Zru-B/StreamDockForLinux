"""
Hardware interface abstraction for StreamDock devices.

This module provides the abstract interface for hardware communication,
allowing different implementations (USB, Mock, etc.) while keeping the
rest of the application hardware-agnostic.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DeviceInfo:
    """
    Information about a discovered HID device.
    
    This class represents a hardware device that has been discovered through
    USB enumeration. The path may change if the device is reconnected, which
    is why DeviceRegistry tracks devices by VID/PID/Serial instead.
    
    Attributes:
        vendor_id: USB Vendor ID
        product_id: USB Product ID
        serial_number: Device serial number (stable identifier)
        path: USB device path (e.g., '/dev/hidraw0') - may change on reconnect
        manufacturer: Manufacturer string from USB descriptor
        product: Product name string from USB descriptor
    """
    vendor_id: int
    product_id: int
    serial_number: str
    path: str
    manufacturer: str = ""
    product: str = ""
    
    @property
    def device_id(self) -> str:
        """
        Generate a stable device identifier from VID:PID:Serial.
        
        This ID remains constant even if the USB path changes.
        """
        return f"{self.vendor_id:04x}:{self.product_id:04x}:{self.serial_number}"


@dataclass
class InputEvent:
    """
    Input event from a hardware device.
    
    Represents a button press or release event from the StreamDock hardware.
    
    Attributes:
        button_index: Zero-based button index (0-14 for 15-key device)
        event_type: Type of event ('press' or 'release')
        timestamp: Time when event was captured
    """
    button_index: int
    event_type: str  # 'press' or 'release'
    timestamp: float = field(default_factory=time.time)


class HardwareInterface(ABC):
    """
    Abstract interface for hardware communication.
    
    This interface abstracts USB/HID communication from the rest of the application.
    Implementations should wrap platform-specific hardware APIs.
    
    Design Pattern: Strategy pattern - allows swapping hardware implementations
    Testing: Can be mocked for testing business logic without real hardware
    """
    
    @abstractmethod
    def enumerate_devices(self, vid: int, pid: int) -> List[DeviceInfo]:
        """
        Discover all devices matching the given Vendor ID and Product ID.
        
        Args:
            vid: USB Vendor ID (e.g., 0x6603)
            pid: USB Product ID (e.g., 0x1006)
            
        Returns:
            List of DeviceInfo objects for all matching devices found
            
        Design Contract:
            - Returns empty list if no devices found
            - Does not raise exceptions for "no devices"
            - VID=0 and PID=0 means enumerate all devices
        """
        pass
    
    @abstractmethod
    def open_device(self, device_info: DeviceInfo) -> bool:
        """
        Open a device for communication.
        
        Args:
            device_info: Device information from enumerate_devices()
            
        Returns:
            True if device opened successfully, False otherwise
            
        Design Contract:
            - Only one device can be open at a time
            - Opening a device when one is already open should close the first
            - Returns False on any error (permissions, device not found, etc.)
        """
        pass
    
    @abstractmethod
    def close_device(self) -> None:
        """
        Close the currently open device.
        
        Design Contract:
            - Safe to call even if no device is open
            - Releases all hardware resources
            - After close, is_connected() should return False
        """
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if a device is currently connected and open.
        
        Returns:
            True if device is open and responsive, False otherwise
            
        Design Contract:
            - Returns False if device was disconnected
            - Returns False if device was never opened
            - May perform a lightweight check (e.g., query device status)
        """
        pass
    
    @abstractmethod
    def set_brightness(self, level: int) -> bool:
        """
        Set the display brightness.
        
        Args:
            level: Brightness level (0-100)
            
        Returns:
            True if brightness was set successfully, False otherwise
            
        Design Contract:
            - Values outside 0-100 should be clamped
            - Returns False if no device is open
            - Brightness change should be immediate
        """
        pass
    
    @abstractmethod
    def send_image(self, image_data: bytes, button_index: int) -> bool:
        """
        Send an image to a specific button.
        
        Args:
            image_data: Raw image data in the format expected by the device
            button_index: Button index (0-based)
            
        Returns:
            True if image was sent successfully, False otherwise
            
        Design Contract:
            - Returns False if no device is open
            - Returns False if button_index is out of range
            - Image format is device-specific (caller's responsibility)
        """
        pass
    
    @abstractmethod
    def read_input(self, timeout_ms: int = 0) -> Optional[InputEvent]:
        """
        Read an input event from the device.
        
        Args:
            timeout_ms: Timeout in milliseconds (0 = non-blocking, -1 = infinite)
            
        Returns:
            InputEvent if a button was pressed, None if timeout or no event
            
        Design Contract:
            - Returns None on timeout (not an error)
            - Returns None if no device is open
            - Blocking behavior when timeout_ms = -1
            - Non-blocking when timeout_ms = 0
        """
        pass

"""
USB/HID hardware implementation for StreamDock devices.

This module implements the HardwareInterface using the existing HIDTransport
class, providing a clean adapter layer without modifying the legacy code.
"""

import logging
from typing import List, Optional

from StreamDock.transport.hid_transport import HIDTransport
from .hardware_interface import HardwareInterface, DeviceInfo, InputEvent


logger = logging.getLogger(__name__)


class USBHardware(HardwareInterface):
    """
    USB/HID implementation of HardwareInterface.
    
    This class wraps the existing HIDTransport implementation, providing
    format conversion and a cleaner API while preserving all existing functionality.
    
    Design Pattern: Adapter pattern - wraps HIDTransport without modification
    """
    
    def __init__(self):
        """Initialize USB hardware interface."""
        self._transport = HIDTransport()
        self._current_device: Optional[DeviceInfo] = None
        logger.debug("USBHardware initialized")
    
    def enumerate_devices(self, vid: int, pid: int) -> List[DeviceInfo]:
        """
        Enumerate USB devices matching VID/PID.
        
        Wraps HIDTransport.enumerate() and converts to DeviceInfo objects.
        """
        try:
            devices = self._transport.enumerate(vid, pid)
            logger.debug(f"Enumerated {len(devices)} devices with VID=0x{vid:04x}, PID=0x{pid:04x}")
            
            device_info_list = []
            for dev in devices:
                # Convert HIDTransport format to DeviceInfo
                path = dev['path']
                if isinstance(path, bytes):
                    path = path.decode('utf-8', errors='replace')
                
                serial = dev.get('serial_number', '')
                if serial is None:
                    serial = ''
                
                device_info = DeviceInfo(
                    vendor_id=dev['vendor_id'],
                    product_id=dev['product_id'],
                    serial_number=serial,
                    path=path,
                    manufacturer=dev.get('manufacturer_string', ''),
                    product=dev.get('product_string', '')
                )
                device_info_list.append(device_info)
                logger.debug(f"  Device: {device_info.device_id} at {device_info.path}")
            
            return device_info_list
        
        except Exception as e:
            logger.error(f"Error enumerating devices: {e}", exc_info=True)
            return []
    
    def open_device(self, device_info: DeviceInfo) -> bool:
        """
        Open a device for communication.
        
        Wraps HIDTransport.open(), converting path to bytes if needed.
        """
        try:
            # Close existing device if any
            if self._current_device is not None:
                logger.debug(f"Closing existing device: {self._current_device.device_id}")
                self.close_device()
            
            # Convert path to bytes for HIDTransport
            path = device_info.path
            if isinstance(path, str):
                path = path.encode('utf-8')
            
            logger.info(f"Opening device: {device_info.device_id} at {device_info.path}")
            result = self._transport.open(path)
            
            if result == 1:
                self._current_device = device_info
                logger.info(f"Successfully opened device: {device_info.device_id}")
                return True
            else:
                logger.warning(f"Failed to open device: {device_info.device_id}")
                return False
        
        except Exception as e:
            logger.error(f"Error opening device {device_info.path}: {e}", exc_info=True)
            return False
    
    def close_device(self) -> None:
        """
        Close the currently open device.
        
        Wraps HIDTransport.close().
        """
        if self._current_device is not None:
            logger.info(f"Closing device: {self._current_device.device_id}")
            try:
                self._transport.close()
            except Exception as e:
                logger.error(f"Error closing device: {e}", exc_info=True)
            finally:
                self._current_device = None
        else:
            logger.debug("close_device() called but no device was open")
    
    def is_connected(self) -> bool:
        """
        Check if a device is currently connected.
        
        Returns True if we have an open device. Note: This doesn't actively
        probe the device, just checks if we think it's open.
        """
        return self._current_device is not None
    
    def set_brightness(self, level: int) -> bool:
        """
        Set display brightness.
        
        Clamps level to 0-100 range and delegates to HIDTransport.
        """
        if not self.is_connected():
            logger.warning("Cannot set brightness: no device connected")
            return False
        
        # Clamp brightness to valid range
        level = max(0, min(100, level))
        
        try:
            logger.debug(f"Setting brightness to {level}%")
            result = self._transport.set_brightness(level)
            
            if result == 1:
                logger.debug(f"Successfully set brightness to {level}%")
                return True
            else:
                logger.warning(f"Failed to set brightness to {level}%")
                return False
        
        except Exception as e:
            logger.error(f"Error setting brightness: {e}", exc_info=True)
            return False
    
    def send_image(self, image_data: bytes, button_index: int) -> bool:
        """
        Send an image to a specific button.
        
        Delegates to HIDTransport.set_key_img().
        """
        if not self.is_connected():
            logger.warning("Cannot send image: no device connected")
            return False
        
        try:
            logger.debug(f"Sending image to button {button_index}")
            result = self._transport.set_key_img(image_data, len(image_data), button_index)
            
            if result == 1:
                logger.debug(f"Successfully sent image to button {button_index}")
                return True
            else:
                logger.warning(f"Failed to send image to button {button_index}")
                return False
        
        except Exception as e:
            logger.error(f"Error sending image to button {button_index}: {e}", exc_info=True)
            return False
    
    def read_input(self, timeout_ms: int = 0) -> Optional[InputEvent]:
        """
        Read an input event from the device.
        
        Wraps HIDTransport.read_() and converts to InputEvent.
        """
        if not self.is_connected():
            return None
        
        try:
            # HIDTransport.read_() returns tuple: (raw_bytes, ack, ok, key, status)
            data = self._transport.read_(513, timeout_ms)
            
            if data is None:
                return None
            
            raw_bytes, ack, ok, key, status = data
            
            # key >= 0 indicates a valid button press
            if key >= 0:
                logger.debug(f"Button {key} pressed")
                return InputEvent(
                    button_index=key,
                    event_type='press'
                )
            
            return None
        
        except Exception as e:
            logger.error(f"Error reading input: {e}", exc_info=True)
            return None

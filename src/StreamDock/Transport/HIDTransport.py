"""
Pure Python implementation of the StreamDock HID transport protocol.
Replaces the libtransport.so native library.

Uses libhidapi-libusb backend via ctypes for direct USB communication,
as the StreamDock device doesn't create hidraw devices.

Packet Structure (513 bytes):
[0]: Report ID (0 for output)
[1-3]: Signature "CRT"
[4-5]: 0
[6-8]: Command (ASCII, 3 chars)
[9-12]: Data/Size (Big Endian)
[13]: Data/Index
[14+]: Payload data

Commands:
- "LIG" - setBrightness: [11]=Percent
- "CLE" - keyClear: [12]=KeyIndex (255 for all keys)
- "DIS" - wakeScreen
- "STP" - refresh
- "LOG" - setBackgroundImg/setKeyImg: [9-12]=Size (BE), [13]=Target (1 for BG, KeyIndex for keys)
- "MOD" - switchMode: [11]=Mode+'1' (ASCII)
- Disconnected: "CLE" with [11]='D', [12]='C'
"""

import ctypes
import os
from ctypes import (
    POINTER,
    Structure,
    c_char_p,
    c_int,
    c_size_t,
    c_ubyte,
    c_ushort,
    c_void_p,
    c_wchar_p,
)
from typing import Dict, List, Optional, Tuple

# Load libhidapi-libusb (NOT hidraw - the StreamDock requires libusb backend)
_hidapi = None
for lib_name in [
    "libhidapi-libusb.so.0",
    "libhidapi-libusb.so",
    "libhidapi.so.0",
    "libhidapi.so",
]:
    try:
        _hidapi = ctypes.CDLL(lib_name)
        break
    except OSError:
        continue

if _hidapi is None:
    raise ImportError(
        "Could not load libhidapi-libusb. Please install hidapi with libusb backend."
    )


class _hid_device_info(Structure):
    """C structure for hid_device_info from hidapi."""

    pass


_hid_device_info._fields_ = [
    ("path", c_char_p),
    ("vendor_id", c_ushort),
    ("product_id", c_ushort),
    ("serial_number", c_wchar_p),
    ("release_number", c_ushort),
    ("manufacturer_string", c_wchar_p),
    ("product_string", c_wchar_p),
    ("usage_page", c_ushort),
    ("usage", c_ushort),
    ("interface_number", c_int),
    ("next", POINTER(_hid_device_info)),
]

# Setup hidapi function signatures
_hidapi.hid_init.restype = c_int
_hidapi.hid_init.argtypes = []

_hidapi.hid_exit.restype = c_int
_hidapi.hid_exit.argtypes = []

_hidapi.hid_enumerate.restype = POINTER(_hid_device_info)
_hidapi.hid_enumerate.argtypes = [c_ushort, c_ushort]

_hidapi.hid_free_enumeration.restype = None
_hidapi.hid_free_enumeration.argtypes = [POINTER(_hid_device_info)]

_hidapi.hid_open_path.restype = c_void_p
_hidapi.hid_open_path.argtypes = [c_char_p]

_hidapi.hid_close.restype = None
_hidapi.hid_close.argtypes = [c_void_p]

_hidapi.hid_read.restype = c_int
_hidapi.hid_read.argtypes = [c_void_p, POINTER(c_ubyte), c_size_t]

_hidapi.hid_write.restype = c_int
_hidapi.hid_write.argtypes = [c_void_p, POINTER(c_ubyte), c_size_t]

_hidapi.hid_set_nonblocking.restype = c_int
_hidapi.hid_set_nonblocking.argtypes = [c_void_p, c_int]

_hidapi.hid_get_input_report.restype = c_int
_hidapi.hid_get_input_report.argtypes = [c_void_p, POINTER(c_ubyte), c_size_t]

# Initialize hidapi
_hidapi.hid_init()


class HIDTransport:
    """
    Pure Python HID transport for StreamDock devices.
    Drop-in replacement for the ctypes wrapper around libtransport.so.
    """

    PACKET_SIZE = 513  # 0x201
    DATA_CHUNK_SIZE = 512  # 0x200
    DUAL_PACKET_SIZE = 1025  # 0x401 - for DualDevice methods
    DUAL_DATA_CHUNK_SIZE = 1024  # 0x400 - for DualDevice methods
    SIGNATURE = b"CRT"

    class hid_device_info:
        """
        Structure to match the original hid_device_info for compatibility.
        """

        def __init__(self, device_dict: dict):
            self.path = device_dict.get("path", b"")
            self.vendor_id = device_dict.get("vendor_id", 0)
            self.product_id = device_dict.get("product_id", 0)
            self.serial_number = device_dict.get("serial_number", "")
            self.release_number = device_dict.get("release_number", 0)
            self.manufacturer_string = device_dict.get("manufacturer_string", "")
            self.product_string = device_dict.get("product_string", "")
            self.usage_page = device_dict.get("usage_page", 0)
            self.usage = device_dict.get("usage", 0)
            self.interface_number = device_dict.get("interface_number", -1)

    def __init__(self):
        self._device: Optional[c_void_p] = None
        self._last_read: Optional[bytes] = None

    def _create_packet(self, command: bytes, data: bytes = b"") -> bytearray:
        """
        Create a 513-byte packet with the StreamDock protocol format.

        Args:
            command: 3-byte ASCII command (e.g., b'LIG', b'CLE')
            data: Additional data bytes to include after the header

        Returns:
            513-byte packet ready to send
        """
        packet = bytearray(self.PACKET_SIZE)
        packet[0] = 0  # Report ID
        packet[1:4] = self.SIGNATURE  # "CRT"
        packet[4] = 0
        packet[5] = 0
        packet[6 : 6 + len(command)] = command

        if data:
            # Copy data starting at appropriate offset
            data_start = 9
            end_pos = min(data_start + len(data), self.PACKET_SIZE)
            packet[data_start:end_pos] = data[: end_pos - data_start]

        return packet

    def _write_packet(self, packet: bytearray) -> int:
        """
        Write a packet to the HID device.

        Returns:
            Number of bytes written, or -1 on error
        """
        if not self._device:
            return -1

        try:
            data = (c_ubyte * len(packet))(*packet)
            return _hidapi.hid_write(self._device, data, len(packet))
        except Exception:
            return -1

    def open(self, path: bytes) -> int:
        """
        Open a HID device by path.

        Args:
            path: Device path (bytes)

        Returns:
            1 on success, -1 on failure
        """
        try:
            if isinstance(path, str):
                path = path.encode("utf-8")

            self._device = _hidapi.hid_open_path(path)
            if not self._device:
                return -1

            _hidapi.hid_set_nonblocking(self._device, 0)
            return 1
        except Exception:
            self._device = None
            return -1

    def close(self):
        """Close the HID device."""
        if self._device:
            try:
                _hidapi.hid_close(self._device)
            except Exception:
                pass
            self._device = None

    def getInputReport(self, length: int) -> Optional[bytes]:
        """
        Get an input report from the device.

        Args:
            length: Maximum length to read

        Returns:
            Bytes read, or None on error
        """
        if not self._device:
            return None

        try:
            # Create buffer with report ID = 1
            buffer = (c_ubyte * length)()
            buffer[0] = 1  # Report ID
            result = _hidapi.hid_get_input_report(self._device, buffer, length)
            if result >= 0:
                return bytes(buffer[:result])
            return None
        except Exception:
            return None

    def read_(self, length: int) -> Optional[Tuple[bytes, str, str, int, int]]:
        """
        Read data from the HID device.

        Args:
            length: Number of bytes to read

        Returns:
            Tuple of (raw_bytes, ack_response, ok_response, key, status) or None
        """
        MAX_LENGTH = 13
        if not self._device:
            return None

        try:
            buffer = (c_ubyte * MAX_LENGTH)()
            result = _hidapi.hid_read(self._device, buffer, MAX_LENGTH)

            if result > 0:
                result_bytes = bytes(buffer[:result])
                self._last_read = result_bytes

                if len(result_bytes) > 0:
                    ack_response = result_bytes[:3].decode("utf-8", errors="ignore")
                    ok_response = (
                        result_bytes[5:7].decode("utf-8", errors="ignore")
                        if len(result_bytes) > 6
                        else ""
                    )
                    key = result_bytes[9] if len(result_bytes) > 9 else 0
                    status = result_bytes[10] if len(result_bytes) > 10 else 0

                    return result_bytes, ack_response, ok_response, key, status
            return None
        except Exception:
            return None

    def deleteRead(self):
        """Clear the last read buffer."""
        self._last_read = None

    def wirte(self, data: bytes, length: int) -> int:
        """
        Write raw data to the device.
        Note: Method name kept as 'wirte' for backward compatibility with original code.

        Args:
            data: Data to write
            length: Length of data

        Returns:
            Number of bytes written, or -1 on error
        """
        if not self._device:
            return -1

        try:
            buffer = (c_ubyte * length)(*data[:length])
            return _hidapi.hid_write(self._device, buffer, length)
        except Exception:
            return -1

    def enumerate(self, vid: int, pid: int) -> List[Dict]:
        """
        Enumerate HID devices matching the given VID/PID.

        Args:
            vid: Vendor ID (0 for any)
            pid: Product ID (0 for any)

        Returns:
            List of device dictionaries
        """
        device_list = []
        try:
            device_enumeration = _hidapi.hid_enumerate(vid, pid)
            if device_enumeration:
                current_device = device_enumeration
                while current_device:
                    if current_device.contents.interface_number == 0:
                        path = current_device.contents.path
                        if isinstance(path, bytes):
                            path = path.decode("utf-8")
                        device_list.append(
                            {
                                "path": path,
                                "vendor_id": current_device.contents.vendor_id,
                                "product_id": current_device.contents.product_id,
                            }
                        )
                    current_device = current_device.contents.next
                _hidapi.hid_free_enumeration(device_enumeration)
        except Exception:
            pass

        return device_list

    def freeEnumerate(self, devs):
        """
        Free enumeration results.
        Note: In Python, this is handled by garbage collection, but kept for API compatibility.
        """
        pass

    def setBrightness(self, percent: int) -> int:
        """
        Set display brightness.

        Args:
            percent: Brightness percentage (0-100)

        Returns:
            1 on success, -1 on failure
        """
        # Clamp value to 0-100
        percent = max(0, min(100, percent))

        packet = bytearray(self.PACKET_SIZE)
        packet[0] = 0  # Report ID
        packet[1:4] = self.SIGNATURE  # "CRT"
        packet[4] = 0
        packet[5] = 0
        packet[6] = ord("L")
        packet[7] = ord("I")
        packet[8] = ord("G")
        packet[9] = 0
        packet[10] = 0
        packet[11] = percent

        result = self._write_packet(packet)
        return 1 if result == self.PACKET_SIZE else -1

    def setBackgroundImg(self, buffer: bytes, size: int) -> int:
        """
        Set background image from raw data.

        Args:
            buffer: Image data bytes
            size: Size of image data

        Returns:
            1 on success, -1 on failure
        """
        # Create header packet with LOG command
        packet = bytearray(self.PACKET_SIZE)
        packet[0] = 0  # Report ID
        packet[1:4] = self.SIGNATURE  # "CRT"
        packet[4] = 0
        packet[5] = 0
        packet[6] = ord("L")
        packet[7] = ord("O")
        packet[8] = ord("G")
        # Size in big-endian (bytes 9-12)
        packet[9] = (size >> 24) & 0xFF
        packet[10] = (size >> 16) & 0xFF
        packet[11] = (size >> 8) & 0xFF
        packet[12] = size & 0xFF
        packet[13] = 1  # Target: 1 for background

        if self._write_packet(packet) == -1:
            return -1

        # Send data in chunks
        chunk_size = self.DATA_CHUNK_SIZE
        offset = 0

        while offset < size:
            data_packet = bytearray(self.PACKET_SIZE)
            data_packet[0] = 0  # Report ID

            # Calculate how much data to copy
            remaining = size - offset
            copy_size = min(chunk_size, remaining)

            # Copy data starting at byte 1
            data_packet[1 : 1 + copy_size] = buffer[offset : offset + copy_size]

            if self._write_packet(data_packet) == -1:
                return -1

            offset += chunk_size

        return 1

    def setBackgroundImgFromFile(self, path: bytes) -> int:
        """
        Set background image from file path (513-byte packets).

        Args:
            path: File path to image

        Returns:
            1 on success, -1 on failure
        """
        try:
            # Handle various path types (bytes, str, c_char_p)
            if hasattr(path, "value"):
                path = path.value  # c_char_p
            if isinstance(path, bytes):
                path = path.decode("utf-8")

            file_size = os.path.getsize(path)

            # Create header packet with LOG command
            packet = bytearray(self.PACKET_SIZE)
            packet[0] = 0  # Report ID
            packet[1:4] = self.SIGNATURE  # "CRT"
            packet[4] = 0
            packet[5] = 0
            packet[6] = ord("L")
            packet[7] = ord("O")
            packet[8] = ord("G")
            # Size in big-endian (bytes 9-12)
            packet[9] = (file_size >> 24) & 0xFF
            packet[10] = (file_size >> 16) & 0xFF
            packet[11] = (file_size >> 8) & 0xFF
            packet[12] = file_size & 0xFF
            packet[13] = 1  # Target: 1 for background

            if self._write_packet(packet) == -1:
                return -1

            # Read and send file in chunks
            with open(path, "rb") as f:
                chunk_size = self.DATA_CHUNK_SIZE  # 512 bytes
                while True:
                    data = f.read(chunk_size)
                    if not data:
                        break

                    data_packet = bytearray(self.PACKET_SIZE)
                    data_packet[0] = 0  # Report ID
                    data_packet[1 : 1 + len(data)] = data

                    if self._write_packet(data_packet) == -1:
                        return -1

            return 1
        except Exception:
            return -1

    def setBackgroundImgDualDevice(self, path: bytes) -> int:
        """
        Set background image from file path (for dual device).

        Args:
            path: File path to image

        Returns:
            1 on success, -1 on failure
        """
        try:
            # Handle various path types (bytes, str, c_char_p)
            if hasattr(path, "value"):
                path = path.value  # c_char_p
            if isinstance(path, bytes):
                path = path.decode("utf-8")

            file_size = os.path.getsize(path)

            # DualDevice background uses "LOG" command with 1025-byte packets
            packet = bytearray(self.DUAL_PACKET_SIZE)
            packet[0] = 0  # Report ID
            packet[1:4] = self.SIGNATURE  # "CRT"
            packet[4] = 0
            packet[5] = 0
            packet[6] = ord("L")  # "LOG" command for background
            packet[7] = ord("O")
            packet[8] = ord("G")
            # Size in big-endian (bytes 9-12)
            packet[9] = (file_size >> 24) & 0xFF
            packet[10] = (file_size >> 16) & 0xFF
            packet[11] = (file_size >> 8) & 0xFF
            packet[12] = file_size & 0xFF
            packet[13] = 1  # Target: 1 for background

            if self._write_packet(packet) == -1:
                return -1

            # Read and send file in chunks (1024 bytes for DualDevice)
            with open(path, "rb") as f:
                chunk_size = self.DUAL_DATA_CHUNK_SIZE  # 1024 bytes
                while True:
                    data = f.read(chunk_size)
                    if not data:
                        break

                    data_packet = bytearray(self.DUAL_PACKET_SIZE)
                    data_packet[0] = 0  # Report ID
                    data_packet[1 : 1 + len(data)] = data

                    if self._write_packet(data_packet) == -1:
                        return -1

            return 1
        except Exception:
            return -1

    def setKeyImg(self, path: bytes, key: int) -> int:
        """
        Set key image from file path.

        Args:
            path: File path to image
            key: Key index

        Returns:
            1 on success, -1 on failure
        """
        try:
            # Handle various path types (bytes, str, c_char_p)
            if hasattr(path, "value"):
                path = path.value  # c_char_p
            if isinstance(path, bytes):
                path = path.decode("utf-8")

            file_size = os.path.getsize(path)

            # Create header packet
            packet = bytearray(self.PACKET_SIZE)
            packet[0] = 0  # Report ID
            packet[1:4] = self.SIGNATURE  # "CRT"
            packet[4] = 0
            packet[5] = 0
            packet[6] = ord("L")
            packet[7] = ord("O")
            packet[8] = ord("G")
            # Size in big-endian
            packet[9] = (file_size >> 24) & 0xFF
            packet[10] = (file_size >> 16) & 0xFF
            packet[11] = (file_size >> 8) & 0xFF
            packet[12] = file_size & 0xFF
            packet[13] = key  # Target: key index

            if self._write_packet(packet) == -1:
                return -1

            # Read and send file in chunks
            with open(path, "rb") as f:
                chunk_size = self.DATA_CHUNK_SIZE
                while True:
                    data = f.read(chunk_size)
                    if not data:
                        break

                    data_packet = bytearray(self.PACKET_SIZE)
                    data_packet[0] = 0
                    data_packet[1 : 1 + len(data)] = data

                    if self._write_packet(data_packet) == -1:
                        return -1

            return 1
        except Exception:
            return -1

    def setKeyImgDualDevice(self, path: bytes, key: int) -> int:
        """
        Set key image from file path (for dual device).

        Args:
            path: File path to image
            key: Key index

        Returns:
            1 on success, -1 on failure
        """
        try:
            # Handle various path types (bytes, str, c_char_p)
            if hasattr(path, "value"):
                path = path.value  # c_char_p
            if isinstance(path, bytes):
                path = path.decode("utf-8")

            file_size = os.path.getsize(path)

            # DualDevice uses "BAT" command (not "LOG") with 1025-byte packets
            packet = bytearray(self.DUAL_PACKET_SIZE)
            packet[0] = 0  # Report ID
            packet[1:4] = self.SIGNATURE  # "CRT"
            packet[4] = 0
            packet[5] = 0
            packet[6] = ord("B")  # "BAT" command for DualDevice
            packet[7] = ord("A")
            packet[8] = ord("T")
            # Size in big-endian (bytes 9-12)
            packet[9] = (file_size >> 24) & 0xFF
            packet[10] = (file_size >> 16) & 0xFF
            packet[11] = (file_size >> 8) & 0xFF
            packet[12] = file_size & 0xFF
            packet[13] = key  # Target: key index

            if self._write_packet(packet) == -1:
                return -1

            # Read and send file in chunks (1024 bytes for DualDevice)
            with open(path, "rb") as f:
                chunk_size = self.DUAL_DATA_CHUNK_SIZE  # 1024 bytes
                while True:
                    data = f.read(chunk_size)
                    if not data:
                        break

                    data_packet = bytearray(self.DUAL_PACKET_SIZE)
                    data_packet[0] = 0  # Report ID
                    data_packet[1 : 1 + len(data)] = data

                    if self._write_packet(data_packet) == -1:
                        return -1

            return 1
        except Exception:
            return -1

    def setKeyImgDataDualDevice(self, path: bytes, key: int) -> int:
        """
        Set key image data (for dual device).
        Same as setKeyImgDualDevice in this implementation.

        Args:
            path: File path to image
            key: Key index

        Returns:
            1 on success, -1 on failure
        """
        return self.setKeyImgDualDevice(path, key)

    def keyClear(self, index: int) -> int:
        """
        Clear a specific key.

        Args:
            index: Key index to clear

        Returns:
            1 on success, -1 on failure
        """
        packet = bytearray(self.PACKET_SIZE)
        packet[0] = 0  # Report ID
        packet[1:4] = self.SIGNATURE  # "CRT"
        packet[4] = 0
        packet[5] = 0
        packet[6] = ord("C")
        packet[7] = ord("L")
        packet[8] = ord("E")
        packet[9] = 0
        packet[10] = 0
        packet[11] = 0
        packet[12] = index & 0xFF

        result = self._write_packet(packet)
        return 1 if result != -1 else -1

    def keyAllClear(self) -> int:
        """
        Clear all keys.

        Returns:
            1 on success, -1 on failure
        """
        packet = bytearray(self.PACKET_SIZE)
        packet[0] = 0  # Report ID
        packet[1:4] = self.SIGNATURE  # "CRT"
        packet[4] = 0
        packet[5] = 0
        packet[6] = ord("C")
        packet[7] = ord("L")
        packet[8] = ord("E")
        packet[9] = 0
        packet[10] = 0
        packet[11] = 0
        packet[12] = 0xFF  # 255 = all keys

        result = self._write_packet(packet)
        return 1 if result != -1 else -1

    def wakeScreen(self) -> int:
        """
        Wake up the screen.

        Returns:
            1 on success, -1 on failure
        """
        packet = bytearray(self.PACKET_SIZE)
        packet[0] = 0  # Report ID
        packet[1:4] = self.SIGNATURE  # "CRT"
        packet[4] = 0
        packet[5] = 0
        packet[6] = ord("D")
        packet[7] = ord("I")
        packet[8] = ord("S")

        result = self._write_packet(packet)
        return 1 if result != -1 else -1

    def refresh(self) -> int:
        """
        Refresh/stop the device display.

        Returns:
            1 on success, -1 on failure
        """
        packet = bytearray(self.PACKET_SIZE)
        packet[0] = 0  # Report ID
        packet[1:4] = self.SIGNATURE  # "CRT"
        packet[4] = 0
        packet[5] = 0
        packet[6] = ord("S")
        packet[7] = ord("T")
        packet[8] = ord("P")

        result = self._write_packet(packet)
        return 1 if result != -1 else -1

    def disconnected(self) -> int:
        """
        Send disconnect signal to device.

        Returns:
            1 on success, -1 on failure
        """
        packet = bytearray(self.PACKET_SIZE)
        packet[0] = 0  # Report ID
        packet[1:4] = self.SIGNATURE  # "CRT"
        packet[4] = 0
        packet[5] = 0
        packet[6] = ord("C")
        packet[7] = ord("L")
        packet[8] = ord("E")
        packet[9] = 0
        packet[10] = 0
        packet[11] = ord("D")  # 'D' for disconnect
        packet[12] = ord("C")  # 'C' for clear/disconnect

        result = self._write_packet(packet)
        return 1 if result != -1 else -1

    def switchMode(self, mode: int) -> int:
        """
        Switch device mode.

        Args:
            mode: Mode number (0-2)

        Returns:
            1 on success, -1 on failure
        """
        if mode < 0 or mode > 2:
            return -1

        packet = bytearray(self.PACKET_SIZE)
        packet[0] = 0  # Report ID
        packet[1:4] = self.SIGNATURE  # "CRT"
        packet[4] = 0
        packet[5] = 0
        packet[6] = ord("M")
        packet[7] = ord("O")
        packet[8] = ord("D")
        packet[9] = 0
        packet[10] = 0
        packet[11] = ord("1") + mode  # Mode as ASCII: '1', '2', or '3'

        result = self._write_packet(packet)
        return 1 if result != -1 else -1


# Alias for backward compatibility
LibUSBHIDAPI = HIDTransport

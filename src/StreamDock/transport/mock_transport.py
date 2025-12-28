"""
Mock HID transport for testing and headless mode.
"""
import logging
from typing import Optional, List, Dict, Tuple
from queue import Queue, Empty

class MockTransport:
    """
    Mock HID transport that simulates a StreamDock device.
    Supports reading from a simulated event queue and logging writes.
    """
    
    PACKET_SIZE = 513
    SIGNATURE = b'CRT'
    
    def __init__(self):
        self._device_open = False
        self.logger = logging.getLogger(__name__)
        # Queue to store simulated input reports (what the device sends to PC)
        self.input_queue = Queue()
        # Log of packets sent to the device (what PC sends to device)
        self.sent_packets = []
        
    def open(self, path: bytes) -> int:
        """Simulate opening the device."""
        self.logger.info(f"Opening mock device at {path}")
        self._device_open = True
        return 1
        
    def close(self):
        """Simulate closing the device."""
        self.logger.info("Closing mock device")
        self._device_open = False
        
    def read_(self, length: int) -> Optional[Tuple[bytes, str, str, int, int]]:
        """
        Read from the simulated input queue.
        Returns tuple format expected by StreamDock.read():
        (raw_bytes, ack_response, ok_response, key, status)
        """
        if not self._device_open:
            return None
            
        try:
            # Blocking read with timeout to simulate hardware waiting for events
            # Use a short timeout so we can check for device closure
            data = self.input_queue.get(timeout=0.5)
            
            # Parse the data to return the expected tuple format
            # Default empty values
            ack = ""
            ok = ""
            key = 0
            status = 0
            
            if len(data) >= 3:
                ack = data[:3].decode('utf-8', errors='ignore')
            if len(data) >= 7:
                ok = data[5:7].decode('utf-8', errors='ignore')
            if len(data) > 9:
                key = data[9]
            if len(data) > 10:
                status = data[10]
                
            return data, ack, ok, key, status
            
        except Empty:
            return None
            
    def _write_packet(self, packet: bytearray) -> int:
        """Log the written packet."""
        if not self._device_open:
            return -1
            
        # Store packet for inspection
        self.sent_packets.append(bytes(packet))
        
        # Log interesting commands
        cmd = packet[6:9].decode('ascii', errors='ignore')
        if cmd == 'LIG':
            self.logger.info(f"[Mock] Set Brightness: {packet[11]}%")
        elif cmd == 'CLE':
            self.logger.info(f"[Mock] Clear Key: {packet[12]} (255=All)")
        elif cmd == 'DIS':
            self.logger.info("[Mock] Wake Screen")
        elif cmd == 'STP':
            self.logger.info("[Mock] Refresh")
        elif cmd == 'LOG':
            target = packet[13]
            self.logger.info(f"[Mock] Set Image. Target: {target} (1=BG, >1=Key)")
            
        return len(packet)

    # Implement all other methods required by HIDTransport interface
    # They generally just return success (1) or delegate to _write_packet
    
    def set_brightness(self, percent: int) -> int:
        packet = bytearray(self.PACKET_SIZE)
        packet[6:9] = b'LIG'
        packet[11] = percent
        return 1 if self._write_packet(packet) > 0 else -1

    def key_clear(self, index: int) -> int:
        packet = bytearray(self.PACKET_SIZE)
        packet[6:9] = b'CLE'
        packet[12] = index
        return 1 if self._write_packet(packet) > 0 else -1

    def key_all_clear(self) -> int:
        packet = bytearray(self.PACKET_SIZE)
        packet[6:9] = b'CLE'
        packet[12] = 0xFF
        return 1 if self._write_packet(packet) > 0 else -1

    def wake_screen(self) -> int:
        packet = bytearray(self.PACKET_SIZE)
        packet[6:9] = b'DIS'
        return 1 if self._write_packet(packet) > 0 else -1

    def refresh(self) -> int:
        packet = bytearray(self.PACKET_SIZE)
        packet[6:9] = b'STP'
        return 1 if self._write_packet(packet) > 0 else -1
        
    def disconnected(self) -> int:
        self.logger.info("[Mock] Sending disconnected signal")
        return 1
        
    def enumerate(self, vid: int, pid: int) -> List[Dict]:
        """Return a fake device if we are the mock transport."""
        return [{
            'path': 'mock_device_path_1',
            'vendor_id': 0x6603,
            'product_id': 0x1006,
            'interface_number': 0
        }]
        
    def set_key_img(self, path: bytes, key: int) -> int:
        # Just log it
        packet = bytearray(self.PACKET_SIZE)
        packet[6:9] = b'LOG'
        packet[13] = key
        return 1 if self._write_packet(packet) > 0 else -1
        
    def set_background_img_from_file(self, path: bytes) -> int:
        packet = bytearray(self.PACKET_SIZE)
        packet[6:9] = b'LOG'
        packet[13] = 1 # BG
        return 1 if self._write_packet(packet) > 0 else -1
        
    # Helpers for simulation
    def simulate_key_press(self, key_index: int):
        """Simulate a key press event (ACK..OK..Key..1)."""
        # Format: ACK \0 \0 OK \0 \0 Key State
        # Indices: 0-2=ACK, 5-6=OK, 9=Key, 10=State
        packet = bytearray(13)
        packet[0:3] = b'ACK'
        packet[5:7] = b'OK'
        packet[9] = key_index
        packet[10] = 1 # Pressed
        self.input_queue.put(bytes(packet))
        
    def simulate_key_release(self, key_index: int):
        """Simulate a key release event (ACK..OK..Key..0)."""
        packet = bytearray(13)
        packet[0:3] = b'ACK'
        packet[5:7] = b'OK'
        packet[9] = key_index
        packet[10] = 0 # Released
        self.input_queue.put(bytes(packet))

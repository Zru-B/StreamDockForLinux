import logging
import time
from .stream_dock import StreamDock
from ..product_ids import USBVendorIDs, USBProductIDs

class MockDevice(StreamDock):
    """
    Mock StreamDock device for testing and headless mode.
    Doesn't perform real USB I/O or image processing.
    """
    KEY_MAP = True # Use standard mapping
    
    def __init__(self, transport, dev_info):
        super().__init__(transport, dev_info)
        self.logger = logging.getLogger(__name__)
        self.logger.info("MockStreamDock initialized")

    def set_brightness(self, percent):
        self.logger.info(f"Setting brightness to {percent}")
        return self.transport.set_brightness(percent)
    
    def set_touchscreen_image(self, path):
        self.logger.info(f"Setting touchscreen image from {path}")
        return 1 # Success

    def set_key_image(self, key, path):
        origin = key
        key = self.key(key)
        self.logger.info(f"Setting key {origin} (mapped {key}) image from {path}")
        return self.transport.set_key_img(path.encode('utf-8'), key)

    def set_key_image_data(self, key, path):
        pass
    
    def get_serial_number(self, length=32):
        return b'MOCKSERIAL123'

    def key_image_format(self):
        return {
            'size': (112, 112),
            'format': "JPEG",
            'rotation': 180,
            'flip': (False, False)
        }
    
    def touchscreen_image_format(self):
        return {
            'size': (800, 480),
            'format': "JPEG",
            'rotation': 180,
            'flip': (False, False)
        }
        
    # Simulation helpers
    def simulate_press(self, key_number):
        """Simulate a physical key press."""
        # Map physical key to hardware index if needed
        # But MockTransport expects raw hardware index.
        # StreamDock.key() maps logical->hardware.
        # But wait, StreamDock.read() does: k = KEY_MAPPING[arr[9]]
        # So transport should send HARDWARE index.
        # KEY_MAPPING reverse map?
        # KEY_MAPPING: {1: 11, ...} means Hardware 1 -> Logical 11
        # StreamDock check: if arr[9] (hardware) is in KEY_MAPPING keys.
        
        self.transport.simulate_key_press(key_number)
        
    def simulate_release(self, key_number):
        """Simulate a physical key release."""
        self.transport.simulate_key_release(key_number)

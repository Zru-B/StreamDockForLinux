import logging
import time
from .StreamDock import StreamDock

logger = logging.getLogger(__name__)

class DummyTransport:
    def open(self, path): pass
    def disconnected(self): pass
    def keyClear(self, index): pass
    def keyAllClear(self): pass
    def wakeScreen(self): pass
    def refresh(self): pass
    def read_(self, length): return None
    def screen_On(self): return None
    def setBrightness(self, percent): pass
    def enumerate(self, vid=0, pid=0):
        return [{'path': "DUMMY_DEVICE", 'vendor_id': 0, 'product_id': 0}]

class DummyStreamDock(StreamDock):
    """
    Represents a dummy StreamDock device for testing/debugging without hardware.
    """
    KEY_MAP = True
    
    def __init__(self, transport=None, devInfo=None):
        # If transport is not provided, create a dummy one
        if transport is None:
            transport = DummyTransport()

        # Mock devInfo if not provided
        if devInfo is None:
            devInfo = {
                'vendor_id': 0,
                'product_id': 0,
                'path': "DUMMY_DEVICE"
            }
            
        super().__init__(transport, devInfo)
        logger.info("[DummyStreamDock] Initialize")

    def open(self):
        logger.info(f"[DummyStreamDock] Open device: {self.path}")
        self._setup_reader(self._read)

    def init(self):
        logger.info("[DummyStreamDock] Init device")
        super().init()

    def close(self):
        logger.info("[DummyStreamDock] Close device")
        super().close()
        
    def _read(self):
        logger.debug("[DummyStreamDock] Start reader thread")
        while self.run_read_thread:
            # Sleep to simulate idle device and prevent high CPU usage
            time.sleep(0.1)
        logger.debug("[DummyStreamDock] Stop reader thread")

    def wakeScreen(self):
        logger.debug("[DummyStreamDock] Wake screen")

    def set_brightness(self, percent):
        logger.debug(f"[DummyStreamDock] Set brightness: {percent}%")

    def clearAllIcon(self):
        logger.debug("[DummyStreamDock] Clear all icons")

    def refresh(self):
        logger.debug("[DummyStreamDock] Refresh")

    def set_key_image(self, key, image):
        logger.debug(f"[DummyStreamDock] Set key image: key={key}")

    def set_touchscreen_image(self, image):
        logger.debug("[DummyStreamDock] Set touchscreen image")

    def get_serial_number(self):
        return "DUMMY_SERIAL_12345"

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

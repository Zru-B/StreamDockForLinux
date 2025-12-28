import ctypes
import random
import logging

from .stream_dock import StreamDock
from ..image_helpers.pil_helper import *


class StreamDock293V3(StreamDock):
    KEY_MAP = True
    def __init__(self, transport1, devInfo):
        super().__init__(transport1, devInfo)
        self.logger = logging.getLogger(__name__)

    def set_brightness(self, percent):
        return self.transport.set_brightness(percent)
    
    def set_touchscreen_image(self, path):
        temp_svg_file = None
        try:
            if not os.path.exists(path):
                self.logger.error(f"Touchscreen image file not found: {path}")
                return -1
            image, temp_svg_file = load_image(path, target_size=(800, 480))
            image = to_native_touchscreen_format(self, image)
            temp_image_path = "rotated_touchscreen_image_" + str(random.randint(9999, 999999)) + ".jpg"
            image.save(temp_image_path)
            
            path_bytes = temp_image_path.encode('utf-8')
            c_path = ctypes.c_char_p(path_bytes)
            res = self.transport.set_background_img_dual_device(c_path)
            os.remove(temp_image_path)
            return res
        
        except Exception:
            self.logger.exception(f"Failed to set touchscreen image from {path}")
            return -1
        finally:
            if temp_svg_file and os.path.exists(temp_svg_file):
                os.remove(temp_svg_file)

    def set_key_image(self, key, path):
        temp_svg_file = None
        try:
            origin = key
            key = self.key(key)
            if not os.path.exists(path):
                self.logger.error(f"Key image file not found: {path} (Key {origin})")
                return -1
            if origin not in range(1, 16):
                self.logger.error(f"Key index out of range: {origin}")
                return -1
            image, temp_svg_file = load_image(path, target_size=(112, 112))
            image = to_native_key_format(self, image)
            temp_image_path = "rotated_key_image_" + str(random.randint(9999, 999999)) + ".jpg"
            image.save(temp_image_path)
            path_bytes = temp_image_path.encode('utf-8')
            c_path = ctypes.c_char_p(path_bytes)
            res = self.transport.set_key_img_dual_device(c_path, key)
            os.remove(temp_image_path)
            return res
            
        except Exception:
            self.logger.exception(f"Failed to set key image from {path} (Key {origin})")
            return -1
        finally:
            if temp_svg_file and os.path.exists(temp_svg_file):
                os.remove(temp_svg_file)

    def set_key_image_data(self, key, path):
        pass
    
    def get_serial_number(self,length):
        return self.transport.get_input_report(length)

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
    
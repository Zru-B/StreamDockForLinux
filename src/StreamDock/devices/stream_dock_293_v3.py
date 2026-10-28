import ctypes
import logging
import os
import tempfile

from ..image_helpers.pil_helper import *
from .stream_dock import StreamDock


class StreamDock293V3(StreamDock):
    KEY_MAP = True
    def __init__(self, transport1, devInfo):
        super().__init__(transport1, devInfo)
        self.logger = logging.getLogger(__name__)

    def set_brightness(self, percent):
        percent = max(0, min(100, int(percent)))
        result = self.transport.set_brightness(percent)
        if result == 1:
            self._current_brightness = percent
        return result

    def set_key_image(self, key, path):
        temp_svg_file = None
        try:
            if not os.path.exists(path):
                self.logger.error("Key image file not found: %s (Key %s)", path, key)
                return -1
            image, temp_svg_file = load_image(path, target_size=(112, 112))
            return self.set_key_pil_image(key, image)
        except Exception:
            self.logger.exception("Failed to set key image from %s (Key %s)", path, key)
            return -1
        finally:
            if temp_svg_file and os.path.exists(temp_svg_file):
                os.remove(temp_svg_file)

    def set_key_pil_image(self, key, image):
        origin = key
        if origin not in range(1, 16):
            self.logger.error("Key index out of range: %s", origin)
            return -1
        temp_image_path = None
        try:
            key = self.key(key)
            image = to_native_key_format(self, image)
            # The transport reads a path; keep the file out of the working directory.
            fd, temp_image_path = tempfile.mkstemp(suffix='.jpg', prefix='sdkey_native_')
            os.close(fd)
            image.save(temp_image_path, format='JPEG')
            c_path = ctypes.c_char_p(temp_image_path.encode('utf-8'))
            return self.transport.set_key_img_dual_device(c_path, key)
        except Exception:
            self.logger.exception("Failed to set key image (Key %s)", origin)
            return -1
        finally:
            if temp_image_path and os.path.exists(temp_image_path):
                os.remove(temp_image_path)

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

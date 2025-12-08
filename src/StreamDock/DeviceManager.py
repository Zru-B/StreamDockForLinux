import pyudev
import logging
from .ProductIDs import g_products
from .Transport.LibUSBHIDAPI import LibUSBHIDAPI

logger = logging.getLogger(__name__)

class DeviceManager:
    streamdocks = list()

    @staticmethod
    def _get_transport(transport):
        return LibUSBHIDAPI()

    def __init__(self, transport=None):
        self.transport = self._get_transport(transport)

    def enumerate(self):
        products = g_products
        for vid, pid, class_type in products:
            found_devices = self.transport.enumerate(vid = vid, pid = pid)
            self.streamdocks.extend(list([class_type(self.transport, d) for d in found_devices]))  
        return self.streamdocks

    def listen(self):
        products = g_products
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem='usb')

        for device in iter(monitor.poll, None):
            action = device.action
            
            if action not in ['add', 'remove']:
                continue
            if device.action == 'remove':
                for streamdock_to_remove in self.streamdocks:
                    if device.device_path.find(streamdock_to_remove.getPath()) != -1:
                        logger.info("[remove] path: " + streamdock_to_remove.getPath())
                        self.streamdocks.remove(streamdock_to_remove)
                        break
                    
            vendor_id_str = device.get('ID_VENDOR_ID')
            product_id_str = device.get('ID_MODEL_ID')

            if not vendor_id_str or not product_id_str:
                continue

            try:
                vendor_id = int(vendor_id_str, 16)
                product_id = int(product_id_str, 16)
            except ValueError:
                continue

            for vid, pid, class_type in products:
                if vendor_id == vid and product_id == pid:
                    if action == 'add':
                        dev_path = device.device_path.split('/')[-1] + ":1.0"  
                        full_path = dev_path  

                        found_devices = self.transport.enumerate(vid, pid)
                        for d in found_devices:
                            if d['path'].endswith(full_path):
                                logger.info(f"[add] path: {d['path']}")
                                newDevice = class_type(self.transport, d)
                                self.streamdocks.append(newDevice)
                                newDevice.open()
                                break

            


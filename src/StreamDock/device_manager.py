import logging

import pyudev

from .devices.mock import MockDevice
from .product_ids import g_products
from .transport.lib_usb_hid_api import LibUSBHIDAPI
from .transport.mock_transport import MockTransport


class DeviceManager:
    streamdocks = list()

    @staticmethod
    def _get_transport(transport):
        if transport == "mock":
            return MockTransport()
        return LibUSBHIDAPI()

    def __init__(self, transport=None):
        self.streamdocks = list()
        self.logger = logging.getLogger(__name__)
        self.transport = self._get_transport(transport)
        self.transport_mode = transport

    def enumerate(self):
        if self.transport_mode == "mock":
            self.streamdocks = [MockDevice(self.transport, d) for d in self.transport.enumerate(0, 0)]
            self.streamdocks[0].open() # Auto open mock device
            return self.streamdocks
            
        products = g_products
        for vid, pid, class_type in products:
            found_devices = self.transport.enumerate(vid = vid, pid = pid)
            self.streamdocks.extend(list([class_type(self.transport, d) for d in found_devices]))  
        return self.streamdocks

    def listen(self):
        if self.transport_mode == "mock":
            # In mock mode, we don't monitor udev. 
            # We just loop forever or wait for stop signal (but listen blocks, so we sleep)
            import time
            while True:
                time.sleep(1)
                
        products = g_products
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem='usb')

        for device in iter(monitor.poll, None):
            action = device.action
            
            if action not in ['add', 'remove']:
                continue
            if device.action == 'remove':
                for willRemoveDevice in self.streamdocks:
                    if device.device_path.find(willRemoveDevice.get_path()) != -1:
                        self.logger.info("[remove] path: " + willRemoveDevice.get_path())
                        self.streamdocks.remove(willRemoveDevice)
                        break
                continue
                    
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
                                self.logger.info(f"[add] path: {d['path']}")
                                newDevice = class_type(self.transport, d)
                                self.streamdocks.append(newDevice)
                                newDevice.open()
                                break

            


class USBVendorIDs:
    """
    USB Vendor IDs for known StreamDock devices.
    """
    USB_PID_293V3 = 0x6603

class USBProductIDs:
    """
    USB Product IDs for known StreamDock devices.
    """
    USB_PID_STREAMDOCK_293V3EN = 0x1006

from .Devices.StreamDock293V3 import StreamDock293V3

g_products = [
    # 293 serial
    (USBVendorIDs.USB_PID_293V3, USBProductIDs.USB_PID_STREAMDOCK_293V3EN, StreamDock293V3)
]
"""
USB identifiers for the supported Stream Dock hardware.

Kept free of device-class imports so that enumeration, udev tooling and the
GUI can all read these without pulling in the HID transport.
"""

# HOTSPOTEKUSB
STREAMDOCK_VID = 0x6603

# MiraBox Stream Dock 293v3 ("HID DEMO")
STREAMDOCK_293V3_PID = 0x1006

# Every product id this application knows how to drive.
SUPPORTED_PIDS = (STREAMDOCK_293V3_PID,)

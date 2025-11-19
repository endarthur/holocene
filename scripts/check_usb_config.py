#!/usr/bin/env python3
"""Check USB device configuration."""

import sys
sys.path.insert(0, "C:/Users/endar/Documents/GitHub/holocene/src")

import usb.core
import usb.util
import usb.backend.libusb1

# Find libusb DLL
try:
    import usb1
    import os
    usb1_dir = os.path.dirname(usb1.__file__)
    dll_path = os.path.join(usb1_dir, "libusb-1.0.dll")
    backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path if os.path.exists(dll_path) else None)
except:
    backend = usb.backend.libusb1.get_backend()

# Find Paperang
VID = 0x4348
PID = 0x5584

device = usb.core.find(idVendor=VID, idProduct=PID, backend=backend)

if device is None:
    print("❌ Printer not found!")
    sys.exit(1)

print("✅ Printer found!")
print(f"\nDevice: {device}")
print(f"Vendor ID: 0x{device.idVendor:04x}")
print(f"Product ID: 0x{device.idProduct:04x}")

# Print configuration details
print("\n" + "=" * 60)
print("CONFIGURATION DETAILS")
print("=" * 60)

for cfg in device:
    print(f"\nConfiguration {cfg.bConfigurationValue}:")
    print(f"  Interfaces: {cfg.bNumInterfaces}")

    for intf in cfg:
        print(f"\n  Interface {intf.bInterfaceNumber}:")
        print(f"    Alt Setting: {intf.bAlternateSetting}")
        print(f"    Class: {intf.bInterfaceClass}")
        print(f"    Subclass: {intf.bInterfaceSubClass}")
        print(f"    Protocol: {intf.bInterfaceProtocol}")
        print(f"    Endpoints:")

        for ep in intf:
            direction = "IN" if (ep.bEndpointAddress & 0x80) else "OUT"
            print(f"      - 0x{ep.bEndpointAddress:02x} ({direction})")
            print(f"        Type: {ep.bmAttributes & 0x03}")
            print(f"        Max Packet Size: {ep.wMaxPacketSize}")

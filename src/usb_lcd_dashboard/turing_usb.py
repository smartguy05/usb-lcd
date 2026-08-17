"""Native USB transport for current-generation TURZX displays."""

from __future__ import annotations

import io
import struct
import time

from Crypto.Cipher import DES
from PIL import Image
import usb.core
import usb.util

VENDOR_ID = 0x1CBE
PRODUCT_SIZES = {
    0x0028: (480, 480),
    0x0046: (960, 320),
    0x0050: (1280, 720),
    0x0080: (1280, 800),
    0x0088: (1920, 480),
    0x0092: (1920, 462),
    0x0123: (1920, 720),
}


def _backend():
    """Use the bundled libusb DLL on Windows, falling back to system libusb."""
    try:
        import libusb_package

        return libusb_package.get_libusb1_backend()
    except ImportError:
        return None


def find_device():
    backend = _backend()
    devices = usb.core.find(idVendor=VENDOR_ID, find_all=True, backend=backend) or ()
    for device in devices:
        product_id = int(device.idProduct)
        if product_id in PRODUCT_SIZES:
            try:
                device.set_configuration()
            except usb.core.USBError:
                # WinUSB devices are commonly configured already.
                pass
            return device, product_id
    raise ConnectionError("no supported TURZX USB display found")


def _command(command: int, payload: bytes = b"") -> bytes:
    packet = bytearray(500)
    packet[0] = command
    packet[2:4] = b"\x1a\x6d"
    midnight = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
    packet[4:8] = struct.pack("<I", int((time.time() - midnight) * 1000))
    packet[8 : 8 + len(payload)] = payload
    key = b"slv3tuzx"
    encrypted = DES.new(key, DES.MODE_CBC, key).encrypt(packet + bytes(4))
    return encrypted + bytes(6) + b"\xa1\x1a"


def _transfer(device, data: bytes, timeout: int = 5000) -> bytes:
    interface = usb.util.find_descriptor(
        device.get_active_configuration(), bInterfaceNumber=0
    )
    if interface is None:
        raise ConnectionError("TURZX USB interface 0 is unavailable")
    endpoint_out = usb.util.find_descriptor(
        interface,
        custom_match=lambda endpoint: usb.util.endpoint_direction(
            endpoint.bEndpointAddress
        )
        == usb.util.ENDPOINT_OUT,
    )
    endpoint_in = usb.util.find_descriptor(
        interface,
        custom_match=lambda endpoint: usb.util.endpoint_direction(
            endpoint.bEndpointAddress
        )
        == usb.util.ENDPOINT_IN,
    )
    if endpoint_out is None or endpoint_in is None:
        raise ConnectionError("TURZX USB endpoints are unavailable")
    endpoint_out.write(data, timeout)
    response = bytes(endpoint_in.read(512, timeout))
    # Discard any trailing acknowledgements without delaying a frame.
    try:
        while True:
            endpoint_in.read(512, timeout=10)
    except usb.core.USBError:
        pass
    return response


def send_command(device, command: int, payload: bytes = b"") -> bytes:
    return _transfer(device, _command(command, payload))


def send_image(device, image: Image.Image) -> bytes:
    """Replace the screen with an opaque JPEG frame.

    PID 0092 advertises the PNG upload command, but its V2 firmware decodes a
    462x1920 PNG as repeated translucent bands over the stored wallpaper.  The
    vendor's JPEG command replaces the framebuffer correctly on the same unit.
    """
    stream = io.BytesIO()
    image.convert("RGB").save(
        stream,
        "JPEG",
        quality=95,
        subsampling=0,
        optimize=False,
        progressive=False,
    )
    encoded = stream.getvalue()
    if len(encoded) > 1024 * 1024:
        stream = io.BytesIO()
        image.convert("RGB").save(
            stream, "JPEG", quality=85, subsampling=2, optimize=False
        )
        encoded = stream.getvalue()
    return _transfer(device, _command(101, len(encoded).to_bytes(4, "big")) + encoded)

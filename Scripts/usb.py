"""USB property conversion shared by discovery and injector editing."""
import binascii
from . import plist


def property_integer(value):
    if isinstance(value, bool):
        raise ValueError("A USB property cannot be a boolean")
    if isinstance(value, int):
        return value
    data = plist.extract_data(value)
    if not isinstance(data, bytes) or not 1 <= len(data) <= 4:
        raise ValueError("Expected a USB integer or 1-4 bytes of little-endian data")
    return int(binascii.hexlify(data[::-1]), 16)


def port_data(value):
    number = property_integer(value)
    if not 1 <= number <= 255:
        raise ValueError("USB port numbers must be between 1 and 255")
    return plist.wrap_data(binascii.unhexlify("{:08x}".format(number))[::-1])


def connector_type(value):
    number = property_integer(value)
    if not 0 <= number <= 255:
        raise ValueError("USB connector types must be between 0 and 255")
    return number


def normalize_port(port):
    # The editor mutates legacy keys. Import modern-only injectors first,
    # then keep both spellings in sync, including the disabled state.
    for old, new, convert in (
        ("port", "usb-port-number", port_data),
        ("UsbConnector", "usb-port-type", connector_type)
    ):
        source = next((key for key in (old, "#"+old, new, "#"+new) if key in port), None)
        if source is None:
            continue
        value = convert(port[source])
        prefix = "#" if source.startswith("#") else ""
        for key in (old, "#"+old, new, "#"+new):
            port.pop(key, None)
        port[prefix+old] = value
        port[prefix+new] = value

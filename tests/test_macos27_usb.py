import copy
import io
import os
import re
import tempfile
import unittest
from collections import OrderedDict
from contextlib import redirect_stdout

from Scripts import plist, usb
from USBMap import USBMap as Mapper
from USBMapInjectorEdit import USBMap as Editor


class QuietUI:
    def __init__(self, commands):
        self.commands = iter(commands)

    def resize(self, *args):
        pass

    def head(self, *args):
        pass

    def grab(self, *args):
        return next(self.commands)


def editor(ports):
    obj = Editor.__new__(Editor)
    obj.plist_data = {"IOKitPersonalities": {"Test-XHC": {
        "IOProviderMergeProperties": {"ports": ports}
    }, "NoPorts": {}}}
    obj.w, obj.h = 80, 24
    obj.cs = obj.ce = obj.bs = obj.rs = obj.nm = ""
    return obj


class USBPropertiesTests(unittest.TestCase):
    def test_modern_only_import_and_save(self):
        for binary in (False, True):
            with self.subTest(binary=binary), tempfile.TemporaryDirectory() as temp:
                e = editor({"SS01": {"usb-port-number": b"\x11\0\0\0", "usb-port-type": 3}})
                e.plist_path = os.path.join(temp, "Info.plist")
                e.normalize_keys()
                # Exercise both input formats and the actual editor save path.
                with open(e.plist_path, "wb") as f:
                    plist.dump(e.plist_data, f, fmt=plist.FMT_BINARY if binary else plist.FMT_XML)
                with open(e.plist_path, "rb") as f:
                    e.plist_data = plist.load(f)
                self.assertTrue(e.save_plist())
                with open(e.plist_path, "rb") as f:
                    saved = plist.load(f)["IOKitPersonalities"]["Test-XHC"]["IOProviderMergeProperties"]["ports"]["SS01"]
                self.assertEqual(saved["port"], b"\x11\0\0\0")
                self.assertEqual(saved["usb-port-number"], saved["port"])
                self.assertEqual(saved["UsbConnector"], saved["usb-port-type"])
                self.assertIsInstance(saved["usb-port-type"], int)

    def test_modern_disabled_port_stays_disabled(self):
        p = {"#usb-port-number": b"\x19\0\0\0", "usb-port-type": 255, "Comment": "internal"}
        usb.normalize_port(p)
        self.assertNotIn("port", p)
        self.assertNotIn("usb-port-number", p)
        self.assertEqual(p["#port"], p["#usb-port-number"])
        self.assertEqual(p["Comment"], "internal")

    def test_legacy_edits_override_stale_modern_aliases(self):
        p = {"#port": b"\x11\0\0\0", "usb-port-number": b"\x11\0\0\0", "UsbConnector": 0, "usb-port-type": 3}
        usb.normalize_port(p)
        self.assertNotIn("usb-port-number", p)
        self.assertEqual(p["usb-port-type"], 0)

    def test_property_types(self):
        p = {"usb-port-number": 17, "usb-port-type": b"\xff"}
        usb.normalize_port(p)
        self.assertEqual(p["port"], b"\x11\0\0\0")
        self.assertEqual(p["usb-port-type"], 255)
        self.assertEqual(usb.connector_type(0), 0)
        self.assertEqual(usb.connector_type(b"\x03\0\0\0"), 3)

    def test_invalid_properties_rejected(self):
        for value in (0, -1, 256, True, b"", b"\0"*5, "17"):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                usb.port_data(value)

    def test_normalization_is_idempotent(self):
        p = {"usb-port-number": 25, "usb-port-type": 9}
        usb.normalize_port(p)
        first = copy.deepcopy(p)
        usb.normalize_port(p)
        self.assertEqual(p, first)

    def test_editor_display_order_controls_selection_and_highest_port(self):
        # Insertion order differs from numeric order. Port 256 is invalid;
        # use 17 and 2 to exercise both the >15 case and little-endian order.
        ports = OrderedDict((name, {"usb-port-number": number, "usb-port-type": 3})
                            for name, number in (("SS01", 17), ("HS02", 2)))
        e = editor(ports)
        e.u = QuietUI(["T:1:0", "1", "m"])
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            e.plist_path = os.path.join(temp, "Info.plist")
            e.edit_ports("Test-XHC")
        self.assertIn("#port", ports["HS02"])
        self.assertIn("#usb-port-number", ports["HS02"])
        self.assertEqual(ports["HS02"]["usb-port-type"], 0)
        self.assertIn("port", ports["SS01"])
        props = e.plist_data["IOKitPersonalities"]["Test-XHC"]["IOProviderMergeProperties"]
        self.assertEqual(props["port-count"], b"\x11\0\0\0")

    def test_discovery_accepts_modern_data_and_integer_properties(self):
        for number, connector in (("<11000000>", "3"), ("17", "<03000000>")):
            with self.subTest(number=number):
                m = Mapper.__new__(Mapper)
                m.map_hubs = False
                m.usb_cont = re.compile(r"<class AppleUSBXHCIPCI,")
                m.usb_port = re.compile(r"<class AppleUSB30XHCIPort,")
                m.usb_hub = re.compile(r"<class AppleUSB30Hub,")
                m.usb_hubp = re.compile(r"<class AppleUSB30HubPort,")
                m.usb_ext = []
                m.ioreg = [
                    "+-o TestModel  <class IOPlatformExpertDevice, id 0x100, registered>",
                    "  +-o XHC@14000000  <class AppleUSBXHCIPCI, id 0x101, registered>",
                    "    +-o SS01@15100000  <class AppleUSB30XHCIPort, id 0x102, registered>",
                    "      {", '        "usb-port-number" = '+number,
                    '        "usb-port-type" = '+connector, "      }"
                ]
                m.get_ioservice_path = lambda line: "IOService:/TestModel/XHC"
                ports = m.populate_controllers()["XHC@14000000"]["ports"]
                self.assertEqual(ports["11000000"]["connector"], 3)

    def test_generated_map_has_both_keys_and_maximum_port_number(self):
        m = Mapper.__new__(Mapper)
        m.smbios = "TestModel"
        m.merged_list = {"XHC": {"type": "AppleUSBXHCIPCI", "parent_name": "XHC", "ports": {
            "01000000": {"type": "AppleUSB20XHCIPort", "port": "01000000", "connector": 0, "enabled": True},
            "11000000": {"type": "AppleUSB30XHCIPort", "port": "11000000", "connector": 3, "enabled": True},
            "19000000": {"type": "AppleUSB30XHCIPort", "port": "19000000", "connector": 255, "enabled": False}
        }}}
        props = m.build_info_plist()["IOKitPersonalities"]["TestModel-XHC"]["IOProviderMergeProperties"]
        self.assertEqual(props["port-count"], b"\x11\0\0\0")
        self.assertEqual(props["ports"]["HS01"]["usb-port-type"], 0)
        self.assertEqual(props["ports"]["SS01"]["usb-port-number"], b"\x11\0\0\0")
        self.assertIn("#usb-port-number", props["ports"]["SS02"])


if __name__ == "__main__":
    unittest.main()

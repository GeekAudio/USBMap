# macOS 27 USB maps and macOS 26 isolation

This branch fixes map import, discovery, and editing. It does not make more
than 15 root ports work without an independently verified kernel patch.

## Map format

Keep both `port` and `usb-port-number` as four-byte little-endian Data. Keep
`UsbConnector` and `usb-port-type` as Integer values. A disabled port must
use both `#port` and `#usb-port-number`; an active modern alias must not
survive disabling its legacy alias. Modern-only injectors are imported
before the editor operates on the legacy keys. If both aliases disagree,
the legacy key represents the editor's latest change and takes precedence.

`port-count` is the highest enabled port number, not the number of entries.
For example, two enabled ports numbered 1 and 17 require `port-count = 17`.

## What an SSDT can fix

ACPI mapping can supply the correct root-port `_ADR`, connector `_UPC`, and
location `_PLD` definitions. `SSDT-USBX` supplies USB power properties; it
does not map ports or remove the driver's limit. A wake `_PRW` patch controls
wake claims and does not restore SuperSpeed enumeration.

The [alternate XHUB approach](https://github.com/5T33Z0/OC-Little-Translated/tree/main/Content/03_USB_Fixes/ACPI_Mapping_USB_Ports/XHUB_Method)
disables the original root hub on macOS and defines a separate mapped hub.
Use the real namespace from the machine's DSDT. Check for an existing
`RHUB._STA` before adding another one. Retain firmware methods needed by
the controller and audit existing replacement SSDTs before combining them.
This requires the original DSDT and related tables, not just a registry
snapshot. Compiling a standalone SSDT does not establish namespace safety.

An XHUB map still requires at most 15 enabled root ports per controller,
or a working port-limit patch. A USB 3 socket commonly needs two entries:
one HS and one SS. Keep keyboard, mouse, internal Bluetooth, and internal
hubs when selecting a 15-port map. Physical socket and Type-C orientation
testing is required before discarding other entries.

## Isolate macOS 26

`_OSI("Darwin")` matches both macOS versions. OpenCore's ACPI Add/Delete/Patch
entries have no `MinKernel`/`MaxKernel` OS version filter. Adding a new
SSDT to a shared configuration can therefore affect both systems.

Use independent, bootable OpenCore configurations for 26 and 27, preferably
on separate boot media while testing. A directory named `OC-26` is only a
backup until its loader path and bootability are verified. Add the new
SSDT, any scoped rename, and changes to map injection only to the 27
configuration. Hash the 26 tree before and after preparing the trial.

For a kext-based trial, load a distinct map bundle with `MinKernel` and
`MaxKernel` set from the actual target Darwin version. Bound old USB map
injectors so their personalities do not overlap the new map. For the
examined Darwin 27 environment, use `27.0.0` through `27.99.99`; do not infer
this range solely from the macOS marketing version. USBMap does not edit
the user's EFI or automatically apply those bounds.

## Validation

`python3 -m unittest discover -s tests -v` covers modern-only XML/binary
round trips, disabled aliases, connector types including 0 and 255,
numeric selection order, discovery, and generated maps.

The development machine was macOS 27.2 build 26B123, Darwin 27.2.0 x86_64.
Read-only discovery found 15 USB2 root ports and no USB3 root ports. That
is the pre-trial observation, not a successful hardware test of this fork.
No bootloader, ACPI table, or live map was installed by the regression tests.

After a trial boot, count the controller's direct port children, check
unique locationIDs and SS ports, then test USB2/USB3 hotplug, Type-C both
orientations, Bluetooth, and sleep/wake. Verify the unchanged 26 path by
booting it separately.

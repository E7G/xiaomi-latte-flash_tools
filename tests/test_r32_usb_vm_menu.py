#!/usr/bin/env python3
"""No-host-disk tests for the disposable USB boot-menu instrumentation."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from instrument_r32_usb_menu import instrument

DEFAULT = (
    "menuentry 'Arch Linux' {\n"
    "\tlinux /vmlinuz-linux-latte-integrated-7-2 "
    "root=UUID=6c0a601a-f31f-402f-9238-53f9302533f0 rw rootflags=subvol=@ loglevel=3 quiet splash\n"
    "\tinitrd /initramfs-linux-latte-integrated-7-2.img\n"
    "}\n"
)


class UsbMenuTest(unittest.TestCase):
    def test_adds_only_the_diagnostic_menu_instrumentation(self):
        text = instrument(DEFAULT)
        self.assertIn("root=UUID=6c0a601a-f31f-402f-9238-53f9302533f0 rw rootflags=subvol=@", text)
        self.assertIn("\tinitrd /initramfs-linux-latte-integrated-7-2.img\n", text)
        self.assertIn("console=ttyS0,115200", text)
        self.assertIn("systemd.mask=mipad2-usb-installer.service", text)
        self.assertIn("echo R32_USB_GRUB_ENTERED=1", text)
        self.assertNotIn("quiet", text)
        self.assertNotIn("loglevel=3", text)

    def test_requires_expected_root_and_kernel(self):
        for old, new in (
            ("root=UUID=", "root=PARTUUID="),
            ("rootflags=subvol=@", "rootflags=subvol=@home"),
            ("vmlinuz-linux-latte-integrated-7-2", "vmlinuz-linux"),
            ("quiet splash", "quiet; reboot"),
        ):
            with self.assertRaises(ValueError, msg=old):
                instrument(DEFAULT.replace(old, new))

    def test_handles_the_fallback_initrd_without_replacing_it(self):
        extra = DEFAULT.replace("/initramfs-linux-latte-integrated-7-2.img",
                                "/initramfs-linux-latte-integrated-7-2-fallback.img")
        text = instrument(DEFAULT + extra)
        self.assertEqual(text.count("echo R32_USB_GRUB_ENTERED=1"), 2)
        self.assertIn("/initramfs-linux-latte-integrated-7-2-fallback.img", text)


if __name__ == "__main__":
    unittest.main()

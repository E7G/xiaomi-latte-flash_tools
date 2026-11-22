"""Exercise the exact rootfs bezel-key rule staging and systemd map."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "build_rootfs.sh").read_text()
HELPER_START = "install_mipad2_navkeys_rule() {\n"
HELPER = HELPER_START + TEXT.split(HELPER_START, 1)[1].split("\n}\n", 1)[0] + "\n}\n"
NAME = "61-mipad2-navkeys-72.rules"
SOURCE = ROOT / "device_files" / NAME
SHIP = Path("usr/lib/udev/rules.d") / NAME
DMI = "dmi:bvnByosoft:svnXiaomiInc:pnMipad2:pvrMIPad-P0:"
STOCK = f"evdev:name:FTSC1000:00 2808:509C Keyboard:{DMI}"
EXPECTED = {"KEYBOARD_KEY_70016=menu", "KEYBOARD_KEY_70029=leftmeta",
            "KEYBOARD_KEY_7002a=back", "KEYBOARD_KEY_700e0=reserved",
            "KEYBOARD_KEY_700e3=reserved"}
STUB = r'''
run() {
    printf '%s\n' "$*" >> "$trace"
    case "$*" in
        'systemd-hwdb --strict update') systemd-hwdb --root "$mount_dir" --strict update ;;
        'udevadm hwdb --update') return 0 ;;
        *) return 58 ;;
    esac
}
'''


class NavkeyHwdb(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mipad2 image ")
        self.addCleanup(temp.cleanup)
        self.target = Path(temp.name)
        self.env = os.environ | {"mount_dir": str(self.target), "device_file": str(SOURCE.parent),
                                 "trace": str(self.target / "called")}
        # The regular systemd package supplies this record in the real image.
        dist = self.target / "usr/lib/udev/hwdb.d/60-keyboard.hwdb"
        dist.parent.mkdir(parents=True)
        dist.write_text(STOCK + "\n" +
                        "\n".join(" " + key for key in sorted(EXPECTED)) + "\n")

    def stage(self, release):
        subprocess.run(["bash", "-ec", STUB + HELPER + "\ninstall_mipad2_navkeys_rule"],
                       env=self.env | {"kernel_release": release}, check=True, timeout=10)

    def keys(self, lookup):
        out = subprocess.run(["systemd-hwdb", "--root", str(self.target), "query", lookup],
                             check=True, text=True, capture_output=True, timeout=5).stdout
        return {l for l in out.splitlines() if l.startswith("KEYBOARD_KEY_")}

    def test_integrated_72_image_stages_a_valid_udev_rule(self):
        self.stage("7.2.15-mipad2-integrated-lpat31")
        self.assertEqual((self.target / SHIP).read_bytes(), SOURCE.read_bytes())
        self.assertEqual((self.target / SHIP).stat().st_mode & 0o777, 0o644)
        subprocess.run(["udevadm", "verify", str(self.target / SHIP)], check=True, timeout=5)
        self.assertEqual(self.keys(STOCK), EXPECTED)
        self.assertEqual(self.keys(STOCK.replace("FTSC1000:00", "hid-over-i2c")), set())
        self.assertEqual((self.target / "called").read_text(), "systemd-hwdb --strict update\n")

    def test_rule_pins_kernel_and_input_topology_before_applying_keymap(self):
        rule = SOURCE.read_text()
        apply = rule.index('IMPORT{builtin}="hwdb')
        for token in ('SUBSYSTEM=="input"', 'KERNEL=="event[0-9]*"',
                      'ATTRS{name}=="hid-over-i2c 2808:509C Keyboard"',
                      'ATTRS{phys}=="i2c-FTSC1000"', 'ATTR{[dmi/id]sys_vendor}=="Xiaomi Inc"',
                      'ATTR{[dmi/id]product_name}=="Mipad2"', 'PROGRAM=="/usr/bin/uname -r"',
                      'RESULT=="7.2.[0-9]*-mipad2-*"'):
            self.assertIn(token, rule[:apply])
        self.assertIn("evdev:name:FTSC1000:00 2808:509C Keyboard:", rule[apply:])
        self.assertIn('IMPORT{builtin}="keyboard"', rule[apply:])

    def test_other_and_legacy_images_are_not_touched(self):
        for release in ("6.14.0-mipad2-cachyos", "7.2.15-arch1-1", "7.20.1-mipad2-other"):
            self.stage(release)
            self.assertFalse((self.target / SHIP).exists())
        self.assertEqual((self.target / "called").read_text(), "udevadm hwdb --update\n" * 3)

    def test_common_image_config_installs_rule_without_navkey_daemon(self):
        body = TEXT.split("\nconfig_packages() {\n", 1)[1]
        self.assertIn("\n\tinstall_mipad2_navkeys_rule\n", body)
        self.assertIn("systemctl disable mipad2-navkeys.service", body)
        self.assertNotIn("enable mipad2-navkeys.service", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)

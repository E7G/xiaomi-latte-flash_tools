"""Compile and query the exact rootfs navigation-key staging function."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "device_files"
TEXT = (ROOT / "build_rootfs.sh").read_text()
HELPER = ("install_mipad2_navkeys_hwdb() {\n" +
          TEXT.split("install_mipad2_navkeys_hwdb() {\n", 1)[1].split("\n}\n", 1)[0] + "\n}\n")
SHIP = "usr/lib/udev/hwdb.d/61-mipad2-navkeys.hwdb"
DMI = "dmi:bvnByosoft:svnXiaomiInc:pnMipad2:pvrMIPad-P0:"
LOOKUP = f"evdev:name:hid-over-i2c 2808:509C Keyboard:{DMI}"
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
        self.env = os.environ | {"mount_dir": str(self.target), "device_file": str(SOURCE),
                                 "trace": str(self.target / "called")}

    def stage(self, release):
        subprocess.run(["bash", "-ec", STUB + HELPER + "\ninstall_mipad2_navkeys_hwdb"],
                       env=self.env | {"kernel_release": release}, check=True, timeout=10)

    def keys(self, lookup):
        out = subprocess.run(["systemd-hwdb", "--root", str(self.target), "query", lookup],
                             check=True, text=True, capture_output=True, timeout=5).stdout
        return {l for l in out.splitlines() if l.startswith("KEYBOARD_KEY_")}

    def test_integrated_72_image_matches_real_udev_lookup(self):
        self.stage("7.2.15-mipad2-integrated-lpat31")
        self.assertEqual((self.target / SHIP).read_bytes(),
                         (SOURCE / "61-mipad2-navkeys.hwdb").read_bytes())
        self.assertEqual((self.target / SHIP).stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.keys(LOOKUP), EXPECTED)
        self.assertEqual((self.target / "called").read_text(), "systemd-hwdb --strict update\n")

    def test_sibling_and_other_board_never_get_mapping(self):
        self.stage("7.2.0-mipad2-integrated-r2")
        for q in (LOOKUP.replace(" Keyboard", ""), LOOKUP.replace(" Keyboard", " UNKNOWN"),
                  LOOKUP.replace("509C", "509D"), LOOKUP.replace("pnMipad2:", "pnMipad20:"),
                  LOOKUP.replace("svnXiaomiInc:", "svnAlldocube:")):
            with self.subTest(lookup=q):
                self.assertEqual(self.keys(q), set())

    def test_admin_hwdb_remains_higher_priority(self):
        p = self.target / "etc/udev/hwdb.d/99-user.hwdb"
        p.parent.mkdir(parents=True)
        p.write_text(LOOKUP + "\n KEYBOARD_KEY_7002a=escape\n")
        self.stage("7.2.15-mipad2-integrated-lpat31")
        self.assertIn(" KEYBOARD_KEY_7002a=escape\n", p.read_text())
        self.assertEqual(self.keys(LOOKUP),
                         EXPECTED - {"KEYBOARD_KEY_7002a=back"} | {"KEYBOARD_KEY_7002a=escape"})

    def test_legacy_other_and_host_releases_are_not_touched(self):
        for release in ("6.14.0-mipad2-cachyos", "7.2.15-arch1-1", "7.20.1-mipad2-other"):
            self.stage(release)
            self.assertFalse((self.target / SHIP).exists())
        self.assertEqual((self.target / "called").read_text(), "udevadm hwdb --update\n" * 3)

    def test_common_image_config_installs_rule_without_navkey_daemon(self):
        body = TEXT.split("\nconfig_packages() {\n", 1)[1]
        self.assertIn("\n\tinstall_mipad2_navkeys_hwdb\n", body)
        self.assertIn("systemctl disable mipad2-navkeys.service", body)
        self.assertNotIn("enable mipad2-navkeys.service", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)

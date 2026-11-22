import shlex
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "device_files/mipad2-camera-init-focus.service"
PCI = "/sys/bus/pci/devices/0000:00:03.0"


class CameraFocusGuard(unittest.TestCase):
    def setUp(self):
        unit = UNIT.read_text()
        self.conditions = [shlex.split(s.partition("=")[2])
                           for s in unit.splitlines() if s.startswith("ExecCondition=")]
        self.assertEqual(self.conditions, [
            ["/usr/bin/grep", "-qx", "0x8086", PCI + "/vendor"],
            ["/usr/bin/grep", "-qx", "0x22b8", PCI + "/device"],
        ])
        self.assertIn("\nExecStart=/usr/local/sbin/mipad2-camera-init-focus\n", unit)
        self.assertIn("\nAfter=systemd-udev-trigger.service\n", unit)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.sys = Path(d.name)

    def check(self):
        # systemd executes these in order, then ExecStart only on all success.
        for exe, flags, key, path in self.conditions:
            status = subprocess.run([exe, flags, key, str(self.sys / Path(path).name)],
                                    capture_output=True, timeout=5).returncode
            if status:
                return status
        return 0

    def pci(self, vendor, device):
        (self.sys / "vendor").write_text(vendor + "\n")
        (self.sys / "device").write_text(device + "\n")

    def test_no_isp_skips_instead_of_waiting_for_otp(self):
        self.assertEqual(self.check(), 2)

    def test_unrelated_function_at_the_same_bdf_skips(self):
        self.pci("0x1234", "0x22b8")
        self.assertEqual(self.check(), 1)

    def test_other_intel_device_at_the_same_bdf_skips(self):
        self.pci("0x8086", "0x22b0")
        self.assertEqual(self.check(), 1)

    def test_probed_isp_remains_eligible_with_no_otp_node_yet(self):
        self.pci("0x8086", "0x22b8")
        self.assertEqual(self.check(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Validate the 7.2 installer board and MMC identity without a block device."""
from pathlib import Path
import subprocess
import tempfile
import unittest

TEXT = (Path(__file__).resolve().parents[1] / "device_files/mipad2-install-to-emmc").read_text()
BODY = TEXT.split("# BEGIN MIPAD2_72_INSTALL_TARGET\n", 1)[1].split(
    "# END MIPAD2_72_INSTALL_TARGET", 1)[0]
DIE = r'''die() { echo "$*" >&2; exit 1; }'''


class TargetIdentity(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="latte sysfs ")
        self.addCleanup(tmp.cleanup)
        self.system = Path(tmp.name) / "dmi"
        self.card = Path(tmp.name) / "mmcblk0"
        self.system.mkdir()
        (self.card / "device").mkdir(parents=True)
        (self.system / "sys_vendor").write_text("Xiaomi Inc\n")
        (self.system / "product_name").write_text("Mipad2\n")
        (self.card / "device/type").write_text("MMC\n")
        (self.card / "removable").write_text("0\n")

    def check(self, release="7.2.15-mipad2-integrated-lpat31"):
        script = "\n".join(("set -Eeuo pipefail", DIE, BODY,
                            'require_mipad2_72_install_target "$@"', 'echo accepted'))
        return subprocess.run(
            ["bash", "-c", script, "fixture", release, str(self.system), str(self.card)],
            capture_output=True, text=True, timeout=3,
        )

    def test_real_mipad2_system_id_and_internal_mmc(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(result.stdout, "accepted\n")

    def test_other_system_even_with_fixed_mmc_is_not_an_install_target(self):
        for path, other in (("sys_vendor", "QEMU"), ("product_name", "Mipad3")):
            p = self.system / path
            previous = p.read_text()
            p.write_text(other + "\n")
            result = self.check()
            self.assertNotEqual(result.returncode, 0, result)
            self.assertNotIn("accepted", result.stdout)
            p.write_text(previous)

    def test_wrong_media_or_removable_storage_rejected(self):
        for path, other in (("device/type", "SD"), ("removable", "1")):
            p = self.card / path
            previous = p.read_text()
            p.write_text(other + "\n")
            self.assertNotEqual(self.check().returncode, 0)
            p.write_text(previous)

    def test_unknown_board_and_card_fail_closed(self):
        (self.card / "device/type").unlink()
        self.assertNotEqual(self.check().returncode, 0)
        (self.card / "device/type").write_text("MMC\n")
        (self.system / "product_name").unlink()
        self.assertNotEqual(self.check().returncode, 0)

    def test_other_kernel_path_unchanged(self):
        (self.system / "sys_vendor").unlink()
        (self.card / "device/type").unlink()
        self.assertEqual(self.check("6.14.0-mipad2-cachyos").returncode, 0)

    def test_skip_if_running_from_emmc_then_gate_before_writes(self):
        skip = TEXT.index('\nif [[ $source_disk == "$target" ]]; then')
        board = TEXT.index('\nrequire_mipad2_72_install_target "$release" /sys/class/dmi/id /sys/block/mmcblk0')
        efi = TEXT.index('\nrequire_legacy_boot_mode /sys/firmware/efi')
        snapshot = TEXT.index('\nbtrfs subvolume snapshot -r ')
        erase = TEXT.index('\nsgdisk --zap-all')
        self.assertTrue(skip < board < efi < snapshot < erase)


if __name__ == "__main__":
    unittest.main(verbosity=2)

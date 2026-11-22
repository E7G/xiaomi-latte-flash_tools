"""Exercise the production mount resolver with real findmnt mountinfo parsing."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "device_files/mipad2-install-to-emmc").read_text()
HELP = TEXT.split("# BEGIN RESOLVE_INSTALL_MOUNT_SOURCE\n", 1)[1].split(
    "# END RESOLVE_INSTALL_MOUNT_SOURCE", 1)[0]

# Deliberately use already-existing character device pathnames to exercise
# canonical resolution unprivileged. The production caller separately requires
# both paths and their parent disks to be block devices.
ROOT_MOUNT = "41 11 0:81 /@ / rw,relatime - btrfs /dev/null rw,ssd,subvolid=256,subvol=/@\n"
ESP_MOUNT = "42 41 8:1 / /boot rw,relatime - vfat /dev/zero rw\n"
HOME_MOUNT = "43 41 0:82 /@home /home rw,relatime - btrfs /dev/null rw,ssd\n"
STAGE = r'''
findmnt() { command findmnt --tab-file "$MOUNTINFO" "$@"; }
resolve_install_mount_source "$1"
'''


class InstallMountSource(unittest.TestCase):
    def go(self, path, mounts=ROOT_MOUNT + ESP_MOUNT + HOME_MOUNT):
        with tempfile.TemporaryDirectory() as tmp:
            info = Path(tmp) / "mountinfo"
            info.write_text(mounts)
            return subprocess.run(
                ["bash", "-c", "set -Eeuo pipefail\n" + HELP + STAGE, "fixture", path],
                env=os.environ | {"MOUNTINFO": str(info)},
                text=True, capture_output=True, timeout=5,
            )

    def test_resolves_btrfs_anonymous_device_without_subvolume_suffix(self):
        result = self.go("/")
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(result.stdout, "/dev/null\n")

    def test_resolves_separate_esp(self):
        result = self.go("/boot")
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(result.stdout, "/dev/zero\n")

    def test_requires_exact_mountpoint(self):
        for missing in ("/boot", "/var"):
            result = self.go(missing, ROOT_MOUNT)
            self.assertNotEqual(result.returncode, 0, result)
            self.assertEqual(result.stdout, "")

    def test_missing_nondev_and_ambiguous_source_all_fail(self):
        cases = (
            ROOT_MOUNT.replace("/dev/null", "/dev/nonexistent-mipad2-block-test"),
            ROOT_MOUNT.replace("/dev/null", "/run/fixture-image"),
            ROOT_MOUNT + ROOT_MOUNT.replace("41 11", "43 41").replace("/dev/null", "/dev/zero"),
        )
        for mounts in cases:
            with self.subTest(mounts=mounts):
                result = self.go("/", mounts)
                self.assertNotEqual(result.returncode, 0, result)
                self.assertEqual(result.stdout, "")

    def test_real_block_and_common_parent_checks_still_precede_writes(self):
        source = TEXT.index("source_root=$(resolve_install_mount_source /)")
        real_block = TEXT.index("[[ -b $source_root && -b $source_boot ]]")
        disk = TEXT.index("[[ -b $source_disk && -b $boot_disk ]]")
        same_parent = TEXT.index('[[ $source_disk == "$boot_disk" ]]')
        internal_skip = TEXT.index('if [[ $source_disk == "$target" ]];')
        efi_gate = TEXT.index("\nrequire_legacy_boot_mode /sys/firmware/efi")
        erase = TEXT.index("\nsgdisk --zap-all")
        self.assertTrue(source < real_block < disk < same_parent < internal_skip < efi_gate < erase)


if __name__ == "__main__":
    unittest.main(verbosity=2)

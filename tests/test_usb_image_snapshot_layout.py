"""Exercise the 7.2 builder's image layout and nested-subvolume guard."""
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "build_rootfs.sh").read_text()
HELP = TEXT.split("# BEGIN USB_SNAPSHOT_LAYOUT\n", 1)[1].split(
    "# END USB_SNAPSHOT_LAYOUT", 1)[0]
STUB = r'''
btrfs() {
    [[ "$1 $2 $3" == 'subvolume list -o' ]] || return 10
    case "$TEST:$4" in
        nested-root:"$IMAGE"|nested-home:"$IMAGE/home") printf 'nested subvolume\n';;
        failure:"$IMAGE/home") return 13;;
        *:"$IMAGE"|*:"$IMAGE/home") return 0;;
        *) return 11;;
    esac
    return 0
}
'''


class ImageSnapshotLayout(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="latte image ")
        self.addCleanup(tmp.cleanup)
        self.image = Path(tmp.name)
        (self.image / "home").mkdir()

    def go(self, action, package="linux-latte-integrated-7-2-lpat31", fault="flat"):
        return subprocess.run(
            ["bash", "-c", "set -eu\n" + STUB + HELP + "\n" + action],
            env=os.environ | {"IMAGE": str(self.image), "KERNEL_PKGBASE": package, "TEST": fault},
            text=True, capture_output=True, timeout=5,
        )

    def test_72_images_prepare_regular_private_directories(self):
        for name in ("linux-latte-integrated-7-2", "linux-latte-integrated-7-2-lpat31"):
            result = self.go('prepare_usb_snapshot_layout "$IMAGE"', package=name)
            self.assertEqual(result.returncode, 0, result)
            for directory in ("machines", "portables"):
                info = (self.image / "var/lib" / directory).lstat()
                self.assertTrue(stat.S_ISDIR(info.st_mode))
                self.assertEqual(stat.S_IMODE(info.st_mode), 0o700)

    def test_existing_payload_is_not_modified(self):
        folder = self.image / "var/lib/machines"
        folder.mkdir(parents=True)
        data = folder / "existing"
        data.write_bytes(b"container payload")
        result = self.go('prepare_usb_snapshot_layout "$IMAGE"')
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(data.read_bytes(), b"container payload")

    def test_legacy_image_is_not_changed_or_checked(self):
        result = self.go('prepare_usb_snapshot_layout "$IMAGE"; require_flat_usb_snapshot_layout "$IMAGE"',
                         package="linux-latte-cachyos", fault="nested-root")
        self.assertEqual(result.returncode, 0, result)
        self.assertFalse((self.image / "var").exists())

    def test_build_checks_both_subvolumes_and_fails_closed(self):
        action = 'require_flat_usb_snapshot_layout "$IMAGE"'
        self.assertEqual(self.go(action).returncode, 0)
        for fault in ("nested-root", "nested-home", "failure"):
            with self.subTest(fault=fault):
                result = self.go(action, fault=fault)
                self.assertNotEqual(result.returncode, 0, result)
                if fault.startswith("nested-"):
                    self.assertIn("USB image has nested Btrfs subvolumes", result.stderr)

    def test_preparation_precedes_package_hooks_and_check_precedes_conversion(self):
        calls = TEXT.split("\nall() {\n", 1)[1]
        i = calls.index("\tmount_img\n")
        p = calls.index('\tprepare_usb_snapshot_layout "$mount_dir"\n')
        packages = calls.index("\tinstall_packages\n")
        clean = calls.index("\tcleanup_rootfs\n")
        check = calls.index('\trequire_flat_usb_snapshot_layout "$mount_dir"\n')
        convert = calls.index("\tconvert\n")
        self.assertTrue(i < p < packages < clean < check < convert)


if __name__ == "__main__":
    unittest.main(verbosity=2)

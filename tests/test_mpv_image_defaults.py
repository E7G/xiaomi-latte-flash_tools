"""Exercise the real image-builder defaults without a mounted or live /etc."""
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILDER = (ROOT / "build_rootfs.sh").read_text(encoding="utf-8")
CONFIG = ROOT / "device_files/mipad2-mpv.conf"
HELPER = re.search(r"^install_mipad2_mpv_defaults\(\) \{\n[\s\S]+?^\}", BUILDER, re.M)
if HELPER is None:
    raise RuntimeError("mpv defaults installer function disappeared")


class MpvImageDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mipad2 mpv ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "rootfs"
        self.etc = self.root / "etc"
        self.etc.mkdir(parents=True)
        self.dest = self.etc / "mpv/mpv.conf"

    def install(self, ok=True):
        cmd = "set -eu\numask 077\n" + HELPER.group() + (
            '\nmount_dir="$1"; device_file="$2"; install_mipad2_mpv_defaults'
        )
        return subprocess.run(
            ["bash", "-c", cmd, "test", str(self.root), str(CONFIG.parent)],
            check=ok, capture_output=True, text=True, timeout=5,
        )

    def test_default_uses_only_the_physically_qualified_combination(self):
        self.install()
        self.assertEqual(stat.S_IMODE(self.dest.stat().st_mode), 0o644)
        self.assertEqual(self.dest.read_bytes(), CONFIG.read_bytes())
        values = dict(line.split("=", 1) for line in self.dest.read_text().splitlines()
                      if line.strip() and not line.startswith("#"))
        self.assertEqual(values, {"hwdec": "auto-copy", "gpu-api": "opengl",
                                  "hwdec-codecs": "h264,vp8"})
        first = self.dest.stat()
        self.install()
        self.assertEqual((first.st_ino, first.st_mtime_ns),
                         (self.dest.stat().st_ino, self.dest.stat().st_mtime_ns))

    def test_preserves_preexisting_system_and_per_user_config(self):
        self.dest.parent.mkdir()
        self.dest.write_text("hwdec=no\n")
        self.dest.chmod(0o600)
        user = self.root / "home/test/.config/mpv/mpv.conf"
        user.parent.mkdir(parents=True)
        user.write_text("gpu-api=vulkan\n")
        self.install()
        self.assertEqual(self.dest.read_text(), "hwdec=no\n")
        self.assertEqual(stat.S_IMODE(self.dest.stat().st_mode), 0o600)
        self.assertEqual(user.read_text(), "gpu-api=vulkan\n")

    def test_preserves_dangling_config_symlink_without_writing_target(self):
        self.dest.parent.mkdir()
        target = self.base / "missing"
        self.dest.symlink_to(target)
        self.install()
        self.assertEqual(self.dest.readlink(), target)
        self.assertFalse(target.exists())

    def test_preserves_config_directory_symlink_without_crossing_root(self):
        target = self.base / "outside"
        target.mkdir()
        self.dest.parent.symlink_to(target)
        self.install()
        self.assertEqual(list(target.iterdir()), [])

    def test_rejects_rootfs_etc_symlink(self):
        self.etc.rmdir()
        outside = self.base / "elsewhere"
        outside.mkdir()
        self.etc.symlink_to(outside)
        self.assertNotEqual(self.install(ok=False).returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_install_is_called_in_shared_desktop_configuration(self):
        body = BUILDER.split("config_packages() {\n", 1)[1].split("\n}\n", 1)[0]
        call = "\n\tinstall_mipad2_mpv_defaults\n"
        self.assertEqual(body.count(call), 1)
        self.assertLess(body.index(call), body.index("配置 service"))


if __name__ == "__main__":
    unittest.main()

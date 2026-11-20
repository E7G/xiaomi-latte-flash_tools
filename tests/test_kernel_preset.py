#!/usr/bin/env python3
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
HOOK = (REPO / "device_files/mipad2-kernel-package.install").read_text()
PRESET = "/etc/mkinitcpio.d/linux-latte-cachyos.preset"
LEGACY = 'ALL_kver="/usr/lib/modules/6.14.0-mipad2-cachyos/vmlinuz"'
STABLE = 'ALL_kver="/usr/lib/mipad2-kernel/vmlinuz"'
CUSTOM_OPTIONS = 'fallback_options="-S autodetect -A custom"\n'


class KernelPresetTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory, "kernel.preset")
        self.hook = Path(directory, "kernel.install")
        self.assertEqual(HOOK.count(PRESET), 1)
        self.hook.write_text(HOOK.replace(PRESET, '"$TEST_PRESET"'))

    def run_hook(self, event):
        subprocess.run(["bash", "-ec", f'source "$1"; {event}', "bash", str(self.hook)],
                       env={**os.environ, "TEST_PRESET": str(self.path)}, check=True)

    def test_migrates_legacy_generation_and_keeps_local_options(self):
        self.path.write_text(LEGACY + "\n" + CUSTOM_OPTIONS)
        self.run_hook("post_upgrade")
        expected = STABLE + "\n" + CUSTOM_OPTIONS
        self.assertEqual(self.path.read_text(), expected)
        self.run_hook("post_upgrade")
        self.assertEqual(self.path.read_text(), expected)

    def test_absent_preset_is_left_for_fresh_rootfs(self):
        self.run_hook("post_install")
        self.assertFalse(self.path.exists())
        self.assertIn(STABLE, (REPO / "build_rootfs.sh").read_text())

    def test_custom_kernel_path_is_preserved(self):
        custom = 'ALL_kver="/usr/lib/modules/6.14.0-private/vmlinuz"\n'
        self.path.write_text(custom)
        self.run_hook("post_upgrade")
        self.assertEqual(self.path.read_text(), custom)

    def test_linked_user_preset_is_left_alone(self):
        user_preset = self.path.with_name("custom.preset")
        user_preset.write_text(LEGACY + "\n")
        self.path.symlink_to(user_preset)
        self.run_hook("post_upgrade")
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(user_preset.read_text(), LEGACY + "\n")


if __name__ == "__main__":
    unittest.main()

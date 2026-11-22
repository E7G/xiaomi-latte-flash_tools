"""Test the production EFI read and its position before any destructive steps."""
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = (REPO / "device_files/mipad2-install-to-emmc").read_text(encoding="utf-8")
GATE = SRC.split("# BEGIN LEGACY_INSTALL_SECURE_BOOT_GATE\n", 1)[1].split(
    "# END LEGACY_INSTALL_SECURE_BOOT_GATE\n", 1)[0]
SECURE_BOOT = "SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"
STUB = "StubInfo-4a67b082-0a4c-41cf-b6c7-440b29bb8c4f"
ATTR = b"\x06\x00\x00\x00"


class InstallerGate(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.efi = Path(tmp.name) / "efi"
        self.vars = self.efi / "efivars"
        self.flag = self.vars / SECURE_BOOT

    def probe(self):
        return subprocess.run(
            ["bash", "-c",
             'set -Eeuo pipefail\n'
             'die() { printf "%s\\n" "$1" >&2; exit 1; }\n'
             + GATE + '\nrequire_legacy_boot_mode "$1"\nprintf "eligible\\n"\n',
             "gate-fixture", str(self.efi)],
            capture_output=True, text=True, timeout=5,
        )

    def variable(self, value):
        self.vars.mkdir(parents=True, exist_ok=True)
        self.flag.write_bytes(value)

    def rejected(self, detail):
        p = self.probe()
        self.assertEqual(p.returncode, 1, p)
        self.assertEqual(p.stdout, "")
        self.assertIn(detail, p.stderr)
        self.assertIn("未写入 eMMC", p.stderr)

    def test_exact_disabled_secure_boot_allows_legacy(self):
        self.variable(ATTR + b"\x00")
        p = self.probe()
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "eligible\n", ""))

    def test_enabled_secure_boot_is_refused(self):
        self.variable(ATTR + b"\x01")
        self.rejected("不支持开启 Secure Boot")

    def test_missing_runtime_or_missing_variable_is_not_disabled(self):
        self.rejected("无法确认")
        self.vars.mkdir(parents=True)
        self.rejected("无法确认")

    def test_wrong_guid_or_symlink_cannot_supply_the_setting(self):
        self.vars.mkdir(parents=True)
        fake = self.vars / "SecureBoot-00000000-0000-0000-0000-000000000000"
        fake.write_bytes(ATTR + b"\x00")
        self.rejected("无法确认")
        self.flag.symlink_to(fake)
        self.rejected("无法确认")

    def test_wrong_length_never_uses_zero_prefix_as_disabled(self):
        for blob in (b"", ATTR, ATTR + b"\x00\x01", ATTR + b"\x00" + b"\x01"*64):
            self.variable(blob)
            self.rejected("长度异常")

    def test_invalid_value_rejected(self):
        self.variable(ATTR + b"\x02")
        self.rejected("状态异常")

    def test_detected_uki_even_with_secure_boot_off_is_refused(self):
        self.variable(ATTR + b"\x00")
        (self.vars / STUB).write_bytes(ATTR + b"stub")
        self.rejected("不支持直接 UKI 启动")

    def test_gate_between_internal_self_skip_and_every_write(self):
        gate = SRC.index("\nrequire_legacy_boot_mode /sys/firmware/efi\n")
        self.assertGreater(gate, SRC.index('if [[ $source_disk == "$target" ]]; then'))
        for operation in ('\nsleep 5\n', '\nbtrfs subvolume snapshot -r', '\nswapoff ',
                          '\nsgdisk --zap-all', '\ndd if=', '\nmkfs.btrfs -f'):
            self.assertLess(gate, SRC.index(operation), operation)


if __name__ == "__main__":
    unittest.main(verbosity=2)

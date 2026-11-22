"""Pre-erase tests for the nested Btrfs subvolume snapshot check (no disks)."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "device_files/mipad2-install-to-emmc").read_text()
HELPER = TEXT.split("# BEGIN CHECK_INSTALL_SNAPSHOT\n", 1)[1].split(
    "# END CHECK_INSTALL_SNAPSHOT", 1)[0]
FAKE_FIND = r'''
die() { printf '%s\n' "$1" >&2; exit 1; }
find() {
    if [[ "$#" != 9 || "$2 $3 $4 $5 $6 $7 $8 $9" != '-xdev -type d -inum 2 -printf 1 -quit' ]]; then
        printf 'unexpected find arguments\n' >&2
        return 6
    fi
    printf '%s\n' "$1" >> "$LOG"
    case "$FAULT:$1" in
        "nested-root:$1") if [[ "$1" == */root-snap ]]; then printf 1; fi ;;
        "nested-home:$1") if [[ "$1" == */home-snap ]]; then printf 1; fi ;;
        "read-error:$1") if [[ "$1" == */home-snap ]]; then return 7; fi ;;
    esac
}
'''


class InstallSnapshotCheck(unittest.TestCase):
    def run_gate(self, fault):
        with tempfile.TemporaryDirectory(prefix="mipad2 snapshot ") as temp:
            log = Path(temp) / "ops"
            result = subprocess.run(
                ["bash", "-c", "set -Eeuo pipefail\n" + FAKE_FIND + HELPER + r'''
require_complete_install_snapshot "$1/root-snap" @
require_complete_install_snapshot "$1/home-snap" @home
printf 'target reached\n' >> "$LOG"
''', "fixture", temp],
                env=os.environ | {"FAULT": fault, "LOG": str(log)},
                text=True, capture_output=True, timeout=5)
            return result, [Path(line).name for line in log.read_text().splitlines()]

    def test_flat_snapshots_allow_install(self):
        result, ops = self.run_gate("ok")
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(ops, ["root-snap", "home-snap", "target reached"])

    def test_nested_root_stops_install(self):
        result, ops = self.run_gate("nested-root")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("@ 含嵌套子卷", result.stderr)
        self.assertEqual(ops, ["root-snap"])

    def test_nested_home_stops_install(self):
        result, ops = self.run_gate("nested-home")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("@home 含嵌套子卷", result.stderr)
        self.assertEqual(ops, ["root-snap", "home-snap"])

    def test_failed_scan_stops_install(self):
        result, ops = self.run_gate("read-error")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("无法检查 Btrfs 子卷 @home", result.stderr)
        self.assertEqual(ops, ["root-snap", "home-snap"])

    def test_installer_checks_exact_send_snapshots_before_touching_target(self):
        root_check = '\nrequire_complete_install_snapshot "$source_top/$root_snap" @\n'
        home_check = '\nrequire_complete_install_snapshot "$source_top/$home_snap" @home\n'
        self.assertGreater(TEXT.index(root_check),
                           TEXT.index('btrfs subvolume snapshot -r "$source_top/@home"'))
        self.assertGreater(TEXT.index(home_check), TEXT.index(root_check))
        self.assertLess(TEXT.index(home_check), TEXT.index('\nswapoff '))
        self.assertLess(TEXT.index(home_check), TEXT.index('\nsgdisk --zap-all '))
        self.assertIn('btrfs send "$source_top/$root_snap"', TEXT)
        self.assertIn('btrfs send "$source_top/$home_snap"', TEXT)


if __name__ == "__main__":
    unittest.main(verbosity=2)

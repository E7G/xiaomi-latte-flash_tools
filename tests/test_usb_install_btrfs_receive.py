"""Fail-safe tests of the real received-subvolume activation helper (no disks)."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "device_files/mipad2-install-to-emmc").read_text()
HELPER = TEXT.split("# BEGIN ACTIVATE_RECEIVED_SUBVOLUMES\n", 1)[1].split(
    "# END ACTIVATE_RECEIVED_SUBVOLUMES", 1)[0]
FAKE_BTRFS = r'''
die() { printf '%s\n' "$1" >&2; exit 1; }
btrfs() {
    case "$1 $2" in
        'property get')
            case "${4##*/}" in
                receive-@home) if [[ $FAULT == source ]]; then echo ro=false; else echo ro=true; fi ;;
                receive-@) echo ro=true ;;
                @home) if [[ $FAULT == readonly ]]; then echo ro=true; else echo ro=false; fi ;;
                @) echo ro=false ;;
                *) return 20 ;;
            esac
            ;;
        'subvolume snapshot')
            printf 'snapshot %s to %s\n' "${3##*/}" "${4##*/}" >> "$LOG"
            if [[ $FAULT == snapshot && "${4##*/}" == @home ]]; then return 21; fi
            mkdir -- "$4"
            ;;
        'subvolume show')
            if [[ $FAULT == invalid_id ]]; then echo 'Subvolume ID: bad'
            else echo 'Subvolume ID: 258'; fi
            ;;
        'subvolume set-default')
            printf 'default %s\n' "$3" >> "$LOG"
            [[ $FAULT != default ]]
            ;;
        'filesystem sync')
            printf 'sync\n' >> "$LOG"
            [[ $FAULT != sync ]]
            ;;
        'subvolume delete')
            printf 'delete %s %s\n' "${3##*/}" "${4##*/}" >> "$LOG"
            ;;
        *) return 22 ;;
    esac
}
'''


class ReceiveActivation(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mipad2 receive ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.log = self.root / "ops"
        self.log.touch()
        for n in ("receive-@", "receive-@home"):
            (self.root / n).mkdir()

    def invoke(self, fault="none"):
        p = subprocess.run(["bash", "-c", "set -Eeuo pipefail\n" + FAKE_BTRFS + HELPER
                             + '\nactivate_received_subvolumes "$1" receive-@ receive-@home',
                             "fixture", str(self.root)],
                           env=os.environ | {"LOG": str(self.log), "FAULT": fault},
                           capture_output=True, text=True, timeout=5)
        return p, self.log.read_text().splitlines()

    def test_verify_default_and_sync_before_cleanup(self):
        p, ops = self.invoke()
        self.assertEqual(p.returncode, 0, p)
        self.assertEqual(ops, ["snapshot receive-@ to @", "snapshot receive-@home to @home",
                               "default 258", "sync", "delete receive-@ receive-@home"])

    def test_source_must_be_read_only(self):
        p, ops = self.invoke("source")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(ops, [])

    def test_existing_destination_is_not_overwritten(self):
        (self.root / "@").mkdir()
        p, ops = self.invoke()
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(ops, [])

    def test_dangling_destination_symlink_is_also_existing(self):
        (self.root / "@home").symlink_to(self.root / "nowhere")
        p, ops = self.invoke()
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(ops, [])

    def test_activation_errors_retain_both_received_subvolumes(self):
        cases = {"snapshot": 2, "readonly": 2, "invalid_id": 2, "default": 3, "sync": 4}
        for fault, count in cases.items():
            with self.subTest(fault=fault):
                self.log.write_text("")
                for path in (self.root / "@", self.root / "@home"):
                    if path.is_dir():
                        path.rmdir()
                p, ops = self.invoke(fault)
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual(len(ops), count)
                self.assertTrue((self.root / "receive-@").is_dir())
                self.assertTrue((self.root / "receive-@home").is_dir())
                self.assertFalse(any(o.startswith("delete ") for o in ops))

    def test_installer_uses_helper_after_both_receive_operations(self):
        call = TEXT.index('\nactivate_received_subvolumes "$target_top" "$root_snap" "$home_snap"\n')
        self.assertEqual(TEXT[:call].count('| btrfs receive "$target_top"'), 2)
        self.assertNotIn('btrfs property set -ts "$target_top', TEXT)


if __name__ == "__main__":
    unittest.main(verbosity=2)

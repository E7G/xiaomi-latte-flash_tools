"""Qualify 7.2 encoded-stream selection, fallback and transfer failure ordering."""
from pathlib import Path
import os
import subprocess
import unittest

TEXT = (Path(__file__).resolve().parents[1] / "device_files/mipad2-install-to-emmc").read_text()
HELP = TEXT.split("# BEGIN BTRFS_SNAPSHOT_TRANSPORT\n", 1)[1].split(
    "# END BTRFS_SNAPSHOT_TRANSPORT", 1)[0]
FAKE = r"""
btrfs() {
    case "$1:$2" in
        send:--help)
            echo probe >&2
            if [[ "$FAULT" == broken ]]; then return 2; fi
            if [[ "$FAULT" != unsupported ]]; then echo '--compressed-data'; fi
            ;;
        receive:*)
            [[ "$2" == "target mount" ]] || return 22
            cat
            ;;
        send:*)
            shift
            printf 'send:%s\n' "$@"
            if [[ "$FAULT" == sender ]]; then return 5; fi
            ;;
        *) return 23;;
    esac
}
"""


class BtrfsTransport(unittest.TestCase):
    def go(self, release="7.2.15-mipad2-integrated-lpat31", fault="ok"):
        actual_pipeline = next(l for l in TEXT.splitlines() if l.startswith('btrfs send "') and "$root_snap" in l)
        call = r'''
configure_btrfs_snapshot_transport "$1"
printf 'mount:%s\n' "$snapshot_receive_opts"
source_top='source mount'
root_snap='root snapshot'
target_top='target mount'
''' + actual_pipeline + '\nprintf "activated\\n"'
        return subprocess.run(["bash", "-c", "set -Eeuo pipefail\n" + FAKE + HELP + call,
                               "fixture", release],
                              env=os.environ | {"FAULT": fault},
                              capture_output=True, text=True, timeout=5)

    def test_72_compact_mode_and_argument_boundaries(self):
        run = self.go()
        self.assertEqual(run.returncode, 0, run)
        self.assertEqual(run.stdout.splitlines(), [
            "mount:subvolid=5,compress=zstd:3", "send:--compressed-data",
            "send:source mount/root snapshot", "activated",
        ])

    def test_unsupported_helpers_fall_back_before_any_copy(self):
        for problem in ("unsupported", "broken"):
            with self.subTest(fault=problem):
                run = self.go(fault=problem)
                self.assertEqual(run.returncode, 0, run)
                self.assertEqual(run.stdout.splitlines(), [
                    "mount:subvolid=5,compress=zstd:3", "send:source mount/root snapshot", "activated",
                ])

    def test_non72_never_probes_or_changes_existing_mode(self):
        for release in ("6.14.0-mipad2-cachyos", "7.2.15-generic"):
            run = self.go(release=release)
            self.assertEqual(run.returncode, 0, run)
            self.assertEqual(run.stderr, "")
            self.assertEqual(run.stdout.splitlines(), [
                "mount:subvolid=5", "send:source mount/root snapshot", "activated",
            ])

    def test_failed_send_does_not_activate_or_retry(self):
        run = self.go(fault="sender")
        self.assertEqual(run.returncode, 5, run)
        self.assertNotIn("activated", run.stdout)
        self.assertEqual(run.stdout.count("send:source mount/root snapshot"), 1)

    def test_configuration_precedes_erase_and_mount_precedes_streams(self):
        config = TEXT.index('\nconfigure_btrfs_snapshot_transport "$release"')
        erase = TEXT.index('\nsgdisk --zap-all')
        mount = TEXT.index('\nmount -o "$snapshot_receive_opts" "$target_root" "$target_top"')
        send = TEXT.index('\nbtrfs send "$' + '{snapshot_send_args[@]}" "$source_top/$root_snap"')
        activate = TEXT.index('\nactivate_received_subvolumes "$target_top"')
        self.assertTrue(config < erase < mount < send < activate)


if __name__ == "__main__":
    unittest.main(verbosity=2)

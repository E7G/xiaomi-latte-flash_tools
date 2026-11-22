"""Qualify the 7.2 camera launcher and boot/interactive focus split without a camera."""
import os
from pathlib import Path
import shlex
import stat
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = (ROOT / "device_files/mipad2-camera-launch").read_text()
INIT = (ROOT / "device_files/mipad2-camera-init-focus").read_text()


class CameraLauncher(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="mipad2-camera-")
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.otp = self.root / "nvmem"
        self.state = self.root / "state"
        self.log = self.root / "log"
        self.lens = self.root / "v4l-subdev3"
        self.af_log = self.root / "af.log"
        self.init = (
            INIT.replace("NVMEM=/sys/bus/nvmem/devices/mipad2-t4ka3-otp/nvmem",
                         "NVMEM=" + shlex.quote(str(self.otp)))
            .replace("STATE=/run/mipad2-camera-af.env",
                     "STATE=" + shlex.quote(str(self.state)))
            .replace("/dev/v4l-subdev*", str(self.root / "v4l-subdev*"))
        )
        self.wrapper = (
            WRAPPER.replace("/usr/local/bin/mipad2-camera-af", str(self.bin / "af"))
            .replace("/tmp/mipad2-camera-af.log", str(self.af_log))
        )
        self.af_runs = self.root / "ran-af"
        self.executable("af", 'printf "%s\\n" "$@" > "$AF_RUNS"')
        self.executable("snapshot", 'printf "snapshot <%s>\\n" "$@" >> "$LOG"')
        self.executable("sudo", "printf 'sudo <%s>\\n' \"$@\" >> \"$LOG\"; exit 13")
        self.executable(
            "sleep", r'''
printf "wait:%s\n" "$1" >> "$LOG"
if [ -f "$DEFERRED" ]; then mv "$DEFERRED" "$OTP"; fi
''',
        )
        self.executable(
            "v4l2-ctl", r'''
[ "$1" = -d ] && [ -f "$2" ] || exit 2
case "$3" in
    --list-ctrls) printf 'probe:%s\n' "$2" >> "$LOG"; echo focus_absolute;;
    --set-ctrl=focus_absolute=*) printf 'set:%s\n' "$3" >> "$LOG";;
    *) exit 3;;
esac
''',
        )

    def executable(self, name, commands):
        p = self.bin / name
        p.write_text("#!/bin/sh\nset -eu\n" + commands + "\n")
        p.chmod(0o755)

    def go(self, script, *args):
        return subprocess.run(
            ["sh", "-c", script, "fixture", *args],
            env=os.environ | {
                "PATH": str(self.bin) + ":" + os.environ["PATH"],
                "LOG": str(self.log), "OTP": str(self.otp),
                "DEFERRED": str(self.otp) + ".pending", "AF_RUNS": str(self.af_runs),
            },
            capture_output=True, text=True, timeout=6,
        )

    def seed_otp(self, path=None):
        # Valid factory OTP group with infinity 237, macro 366.
        group = bytearray([1, 8, 9, 0, 237, 1, 110] + [0] * 9)
        group[15] = sum(group[1:15]) % 255
        (path or self.otp).write_bytes(bytes(16) + group)

    def test_normal_launch_does_not_wait_for_absent_rear_hardware(self):
        result = self.go(self.init, "--no-wait")
        self.assertEqual(result.returncode, 1, result)
        self.assertFalse(self.log.exists())
        self.seed_otp()
        result = self.go(self.init, "--no-wait")
        self.assertEqual(result.returncode, 6, result)
        self.assertFalse(self.log.exists())
        self.assertFalse(self.state.exists())

    def test_boot_default_can_wait_for_delayed_hardware(self):
        self.seed_otp(self.otp.with_suffix(".pending"))
        self.lens.touch()
        result = self.go(self.init)
        self.assertEqual(result.returncode, 0, result)
        self.assertTrue(self.log.read_text().startswith("wait:0.25\n"))

    def test_nowait_uses_identical_calibration_and_replaces_state_atomically(self):
        self.seed_otp()
        self.lens.touch()
        self.state.write_bytes(b"old valid state")
        old = self.state.stat().st_ino
        result = self.go(self.init, "--no-wait")
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(
            self.log.read_text().splitlines(), [f"probe:{self.lens}", "set:--set-ctrl=focus_absolute=237"],
        )
        self.assertEqual(
            self.state.read_text().splitlines(),
            ["MIPAD2_AF_INFINITY=237", "MIPAD2_AF_MACRO=366", f"MIPAD2_AF_DEVICE={self.lens}"],
        )
        self.assertNotEqual(self.state.stat().st_ino, old)
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o644)
        self.assertEqual(list(self.root.glob("state.*")), [])

    def test_invalid_calibration_and_bad_mode_preserve_published_state(self):
        self.seed_otp()
        data = bytearray(self.otp.read_bytes())
        data[-1] ^= 0xff
        self.otp.write_bytes(data)
        self.state.write_bytes(b"published valid state")
        result = self.go(self.init, "--no-wait")
        self.assertEqual(result.returncode, 4, result)
        self.assertEqual(self.state.read_bytes(), b"published valid state")
        result = self.go(self.init, "--unexpected")
        self.assertEqual(result.returncode, 64, result)
        self.assertFalse(self.log.exists())

    def test_initialiser_failure_still_opens_normal_camera_with_original_arguments(self):
        result = self.go(self.wrapper, "--no-autofocus", "--fixture-flag", "two words")
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(
            self.log.read_text().splitlines(), [
                "sudo <-n>", "sudo </usr/local/sbin/mipad2-camera-init-focus>", "sudo <--no-wait>",
                "snapshot <--fixture-flag>", "snapshot <two words>",
            ],
        )
        self.assertFalse(self.af_runs.exists())

    def test_normal_launch_continues_if_interactive_preset_stalls(self):
        self.executable("sudo", "exec /bin/sleep 20")
        before = time.monotonic()
        result = self.go(self.wrapper, "--fixture-flag")
        took = time.monotonic() - before
        self.assertEqual(result.returncode, 0, result)
        self.assertLess(took, 5)
        self.assertEqual(self.log.read_text(), "snapshot <--fixture-flag>\n")

    def test_explicit_autofocus_actions_still_work(self):
        for option, mode in (("--autofocus", "--fast"), ("--full-autofocus", "--full")):
            with self.subTest(option=option):
                result = self.go(self.wrapper, option, "--fixture-flag")
                self.assertEqual(result.returncode, 0, result)
                self.assertEqual(self.af_runs.read_text(), mode + "\n")
                self.assertTrue(self.log.read_text().endswith("snapshot <--fixture-flag>\n"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

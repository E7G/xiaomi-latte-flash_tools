"""Exercise the exact legacy USB ESP gate and its serial renewal (no disks)."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "device_files/mipad2-install-to-emmc").read_text()
HELP = TEXT.split("# BEGIN LOCAL_ESP_IDENTITY\n", 1)[1].split("# END LOCAL_ESP_IDENTITY", 1)[0]
DIE = '''die() { printf '%s\\n' "$*" >&2; exit 1; }\n'''
STUB = r'''
fatlabel() {
    [[ "$1 $2 $3" == "--volume-id --reset $TARGET" && "$#" -eq 3 ]] || return 8
    printf 'attempt\n' >> "$LOG"
    [[ "$TEST" != failure ]]
}
blkid() {
    [[ "$*" == "-p -s UUID -o value -- $TARGET" ]] || return 9
    case "$TEST" in
        invalid) echo not-a-volume;;
        collision) echo ccaa-5511;;
        zero) echo 0000-0000;;
        retry)
            if [[ $(wc -l < "$LOG") -eq 1 ]]; then echo ccaa-5511; else echo 12ab-1cdd; fi ;;
        *) echo 12ab-1cdd;;
    esac
}
'''


class EspIdentity(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix="mipad2 esp ")
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.esp = self.root / "EFI/BOOT"
        self.esp.mkdir(parents=True)
        self.marker = self.esp / "mipad2-esp-local-v1.sha256"
        self.loader = self.esp / "BOOTX64.EFI"
        self.alt = self.esp / "grubx64.efi"
        content = b"synthetic signed-PE bytes"
        self.loader.write_bytes(content)
        self.alt.write_bytes(content)
        self.marker.write_text(hashlib.sha256(content).hexdigest() + "\n")
        self.log = self.root / "relabels"

    def entry(self, action, stub="", fault="ok"):
        return subprocess.run(
            ["bash", "-c", "set -Eeuo pipefail\n" + DIE + stub + HELP + "\n" + action,
             "fixture", str(self.root)], capture_output=True, text=True, timeout=5,
            env=os.environ | {"TARGET": str(self.root / "dest"), "LOG": str(self.log), "TEST": fault})

    def validate(self):
        return self.entry('require_local_esp_loader "$1"')

    def test_matching_new_loader_is_accepted(self):
        p = self.validate()
        self.assertEqual(p.returncode, 0, p)

    def test_old_loader_without_sidecar_and_changed_loader_are_rejected(self):
        value = self.marker.read_text()
        self.marker.unlink()
        self.assertNotEqual(self.validate().returncode, 0)
        self.marker.write_text(value)
        self.alt.write_bytes(b"a renamed older loader")
        self.assertNotEqual(self.validate().returncode, 0)

    def test_empty_loaders_and_symlinks_are_rejected(self):
        self.loader.write_bytes(b"")
        self.alt.write_bytes(b"")
        self.marker.write_text(hashlib.sha256(b"").hexdigest() + "\n")
        self.assertNotEqual(self.validate().returncode, 0)
        self.loader.write_bytes(b"content")
        self.alt.unlink()
        self.alt.symlink_to(self.loader)
        self.marker.write_text(hashlib.sha256(b"content").hexdigest() + "\n")
        self.assertNotEqual(self.validate().returncode, 0)

    def test_sidecar_matches_exact_builder_output_format(self):
        builder = (ROOT / "build_rootfs.sh").read_text()
        line = next(l.strip() for l in builder.splitlines() if "esp-local-v1.sha256" in l)
        p = self.entry('mount_dir="$1"\n'
                       'mkdir "$mount_dir/boot"\nln -s ../EFI "$mount_dir/boot/EFI"\n'
                       'boot_signature_hash=$(sha256sum < "$mount_dir/EFI/BOOT/grubx64.efi")\n'
                       + line + '\nrequire_local_esp_loader "$mount_dir/boot"')
        self.assertEqual(p.returncode, 0, p)

    def reboot_id(self, fault):
        self.log.write_text("")
        p = self.entry('reidentify_cloned_esp "$TARGET" CCAA-5511', STUB, fault)
        return p, len(self.log.read_text().splitlines())

    def test_collision_retries_and_returns_new_canonical_id(self):
        p, count = self.reboot_id("retry")
        self.assertEqual(p.returncode, 0, p)
        self.assertEqual(p.stdout.strip(), "12AB-1CDD")
        self.assertEqual(count, 2)

    def test_bad_reidentification_never_returns_source_or_zero(self):
        for fault, count in [("collision", 3), ("zero", 3), ("invalid", 1), ("failure", 1)]:
            with self.subTest(fault=fault):
                p, actual = self.reboot_id(fault)
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual(p.stdout, "")
                self.assertEqual(actual, count)

    def test_missing_target_tool_refuses_before_writes(self):
        for tool in ("fsck.fat", "fatlabel", "grub-mkconfig"):
            with self.subTest(tool=tool):
                stub = f'command() {{ [[ "$1" == -v && "$2" != "{tool}" ]]; }}\n'
                p = self.entry("require_install_tools", stub)
                self.assertNotEqual(p.returncode, 0, p)
                self.assertIn(tool, p.stderr)
        scripts = (ROOT / "build_rootfs.sh").read_text()
        self.assertIn("btrfs-progs dosfstools ", scripts)

    def test_source_gate_precedes_erase_and_target_recheck_precedes_fstab(self):
        guard = TEXT.index("\nrequire_local_esp_loader /boot\n")
        legacy = TEXT.index("\nrequire_legacy_boot_mode /sys/firmware/efi\n")
        erase = TEXT.index("\nsgdisk --zap-all")
        clone = TEXT.index('\ndd if="$source_boot"')
        reidentify = TEXT.index('\nboot_uuid=$(reidentify_cloned_esp ')
        check = TEXT.index('\nrequire_local_esp_loader "$target_mnt/boot"')
        fstab = TEXT.index('\ncat > "$target_mnt/etc/fstab"')
        deps = TEXT.index("\nrequire_install_tools\n")
        self.assertTrue(legacy < deps < guard < erase < clone < reidentify < check < fstab)
        self.assertIn("UUID=$boot_uuid /boot vfat", TEXT)


if __name__ == "__main__":
    unittest.main(verbosity=2)

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = (Path(__file__).resolve().parents[1] / "build_rootfs.sh").read_text()


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL is required")
class ImageSigningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="Mi Pad EFI fixtures ")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.keys = Path(cls.tmp.name)
        for name in ("matching", "unrelated"):
            subprocess.run(
                ["openssl", "req", "-new", "-x509", "-newkey", "rsa:2048",
                 "-nodes", "-days", "2", "-subj", "/CN=isolated test fixture",
                 "-keyout", str(cls.keys / (name + ".key")),
                 "-out", str(cls.keys / (name + ".crt"))],
                check=True, capture_output=True,
            )

    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="Mi Pad image ")
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)

    def shell(self, program, **inputs):
        env = os.environ.copy()
        for k in ("MIPAD2_EFI_SIGNING_KEY", "MIPAD2_EFI_SIGNING_CERT"):
            env.pop(k, None)
        env.update({k: str(v) for k, v in inputs.items()})
        return subprocess.run(["bash", "-e", "-c", program], cwd=self.root,
                              env=env, capture_output=True, text=True)

    def preflight(self, key=None, cert=None):
        start = SCRIPT.index('efi_key="')
        end = SCRIPT.index('if [[ $EUID -ne 0 ]]', start)
        env = {}
        if key is not None:
            env["MIPAD2_EFI_SIGNING_KEY"] = self.keys / key
        if cert is not None:
            env["MIPAD2_EFI_SIGNING_CERT"] = self.keys / cert
        return self.shell(SCRIPT[start:end], **env)

    def test_valid_optional_pair_with_space_in_path(self):
        r = self.preflight("matching.key", "matching.crt")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_legacy_omission_preserves_existing_path(self):
        r = self.preflight()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_pairs_fail_before_filesystem_changes(self):
        for key, cert, message in (
            ("matching.key", None, "Supply both"),
            (None, "matching.crt", "Supply both"),
            ("missing.key", "matching.crt", "Supply both"),
            ("matching.key", "unrelated.crt", "does not match"),
        ):
            with self.subTest(key=key, cert=cert):
                r = self.preflight(key, cert)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(message, r.stderr)
                self.assertEqual(list(self.root.iterdir()), [])

    def run_image_signer(self, fail_verify=False):
        # Run the actual signing block with a target-root fixture. Simulated
        # chroot commands cannot touch the host. Test stdin and cert plumbing;
        # Authenticode is tested separately against real kernel/GRUB binaries.
        start = SCRIPT.index('if [[ -n "$efi_key" ]]; then', SCRIPT.index("config_grub()"))
        end = SCRIPT.index("run grub-script-check /boot/grub/grub.cfg", start)
        block = SCRIPT[start:end] + "run grub-script-check /boot/grub/grub.cfg\n"
        stub = r"""
mount_dir="$PWD/rootfs"
mkdir -p "$mount_dir/boot/EFI/BOOT"
KERNEL_PKGBASE=linux-latte-integrated-7-2-lpat31
printf '%s\n' kernel > "$mount_dir/boot/vmlinuz-$KERNEL_PKGBASE"
efi_key="$MIPAD2_EFI_SIGNING_KEY"
efi_cert="$MIPAD2_EFI_SIGNING_CERT"
config_grub() {
"""
        run = r"""
run() {
    cmd=$1
    shift
    case "$cmd" in
        grub-mkstandalone)
            printf '%s\n' grub > "$mount_dir/boot/EFI/BOOT/grubx64.efi"
            ;;
        sbsign)
            [[ "$1" == --key && "$2" == /dev/stdin && "$3" == --cert &&
               "$4" == /boot/EFI/MOK.crt && "$5" == --output && $# == 7 ]]
            [[ "$(sha256sum)" == "$(sha256sum < "$efi_key")" ]]
            test -f "$mount_dir$7"
            printf '%s\n' 'test signed image' > "$mount_dir$6"
            ;;
        mv|cp)
            "$cmd" "$mount_dir$1" "$mount_dir$2"
            ;;
        sbverify)
            [[ "$1" == --cert && "$2" == /boot/EFI/MOK.crt && $# == 3 ]]
            [[ "$(sha256sum < "$mount_dir$2")" == "$(sha256sum < "$efi_cert")" ]]
            [[ "$(cat "$mount_dir$3")" == 'test signed image' ]]
            printf '%s\n' "$3" >> "$PWD/verified"
            [[ "$FAIL_VERIFY" == 0 ]]
            ;;
        grub-script-check)
            : ;;
        *)
            return 1 ;;
    esac
}
"""
        return self.shell(
            run + stub + block + "}\nconfig_grub\n",
            MIPAD2_EFI_SIGNING_KEY=self.keys / "matching.key",
            MIPAD2_EFI_SIGNING_CERT=self.keys / "matching.crt",
            FAIL_VERIFY=int(fail_verify),
        )

    def test_never_writes_private_key_and_verifies_three_pe_files(self):
        r = self.run_image_signer()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len((self.root / "verified").read_text().splitlines()), 3)
        self.assertFalse(list((self.root / "rootfs").rglob("*.key")))

    def test_certificate_verification_failure_aborts_without_writing_key(self):
        r = self.run_image_signer(fail_verify=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(len((self.root / "verified").read_text().splitlines()), 1)
        self.assertFalse(list((self.root / "rootfs").rglob("*.key")))


if __name__ == "__main__":
    unittest.main()

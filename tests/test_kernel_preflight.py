"""Run the kernel pacman preflight against isolated ESP/UEFI fixtures."""

import os
from pathlib import Path
import subprocess
import tempfile


SOURCE = Path(__file__).resolve().parents[1] / "device_files/mipad2-kernel-preflight"


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        efi = root / "efi"
        key = root / "MOK.key"
        cert = root / "MOK.crt"
        fstype = root / "fstype"
        free_kib = root / "free_kib"
        findmnt = root / "findmnt"
        df = root / "df"
        findmnt.write_text('#!/bin/sh\ncat "$TEST_ROOT/fstype"\n')
        df.write_text('#!/bin/sh\nprintf "Filesystem 1024-blocks Used Available Capacity Mounted on\\n/dev/test 262144 0 %s 0%% /boot\\n" "$(cat "$TEST_ROOT/free_kib")"\n')
        findmnt.chmod(0o755)
        df.chmod(0o755)
        script = root / "preflight"
        script.write_text(
            SOURCE.read_text()
            .replace("efi_dir=/sys/firmware/efi", f"efi_dir={efi}")
            .replace("mok_key=/etc/mipad2-secureboot/MOK.key", f"mok_key={key}")
            .replace("mok_cert=/boot/EFI/MOK.crt", f"mok_cert={cert}")
            .replace("/usr/bin/findmnt", str(findmnt))
            .replace("/usr/bin/df", str(df))
            .replace("/usr/bin/sbsign", "/usr/bin/true")
            .replace("/usr/bin/sbverify", "/usr/bin/true")
        )
        env = dict(os.environ, TEST_ROOT=str(root))

        def check(label, expected):
            result = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env)
            assert (result.returncode == 0) == expected, (label, result.stderr)
            print(f"{label}: OK")

        fstype.write_text("vfat\n")
        free_kib.write_text("65536\n")
        check("64 MiB ESP boundary", True)
        free_kib.write_text("65535\n")
        check("insufficient ESP space", False)
        free_kib.write_text("not-a-number\n")
        check("invalid free-space reading", False)
        free_kib.write_text("65536\n")
        fstype.write_text("ext4\n")
        check("ESP not mounted as vfat", False)
        fstype.write_text("vfat\n")

        vars_dir = efi / "efivars"
        vars_dir.mkdir(parents=True)
        check("unknown UEFI Secure Boot state", False)
        flag = vars_dir / "SecureBoot-test"
        flag.write_bytes(b"\0\0\0\0\0")
        check("Secure Boot disabled", True)
        flag.write_bytes(b"\0\0\0\0\1")
        check("Secure Boot enabled without key", False)
        subprocess.run(
            ["openssl", "req", "-new", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", str(key), "-out", str(cert), "-subj", "/CN=Mi Pad 2 test",
             "-days", "1"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        check("Secure Boot enabled with matching key", True)
        other = root / "other.crt"
        subprocess.run(
            ["openssl", "req", "-new", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", str(root / "other.key"), "-out", str(other),
             "-subj", "/CN=Other", "-days", "1"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        cert.write_bytes(other.read_bytes())
        check("mismatched key and certificate", False)


if __name__ == "__main__":
    main()

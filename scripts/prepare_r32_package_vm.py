#!/usr/bin/env python3
"""Prepare an isolated VM input from the exact, verified source-ci ALPM package."""
import argparse
import hashlib
import shutil
import struct
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

from resolve_kernel_artifact import digest, verify

MARKER = b"~Module signature appended~\n"
RELEASE = "7.2.15-mipad2-integrated-r32"


def check(condition, why):
    if not condition:
        raise ValueError(why)


def prepare(manifest, source, pin, work):
    info = verify(manifest, None, source, pin)
    check(info["package_format"] == "source-ci" and info["kernelrelease"] == RELEASE,
          "expected the R32 source package")
    package = Path(info["package"])
    work.mkdir()
    prefix = ("usr", "lib", "modules", RELEASE)
    root = work / "guest"
    modules = root.joinpath(*prefix)
    files = set()
    kern = work / "vmlinuz"
    with subprocess.Popen(["zstd", "-dc", "--", package], stdout=subprocess.PIPE) as z:
        with tarfile.open(fileobj=z.stdout, mode="r|") as tf:
            for item in tf:
                path = PurePosixPath(item.name)
                if path.parts[:4] != prefix or item.isdir():
                    continue
                check(item.isfile() and ".." not in path.parts, "bad input provenance")
                relative = PurePosixPath(*path.parts[4:])
                if str(relative) == "vmlinuz":
                    target = kern
                elif relative.parts[0] == "kernel" and relative.name.endswith(".ko.zst"):
                    target = modules / relative
                    files.add(relative)
                elif str(relative) in {"modules.builtin", "modules.builtin.modinfo", "modules.order"}:
                    target = modules / relative
                else:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(item) as stream, target.open("xb") as output:
                    shutil.copyfileobj(stream, output)
        while z.stdout.read(65536):
            pass
        check(z.wait() == 0, "could not decompress package")
    check(digest(package) == pin, "archive changed during preparation")
    check(kern.is_file() and len(files) == 37, "incomplete package module inventory")
    for name in ("modules.builtin", "modules.builtin.modinfo", "modules.order"):
        check((modules / name).is_file(), f"missing {name}")
    erofs = modules / "kernel/fs/erofs/erofs.ko.zst"
    check(erofs.is_file(), "missing negative-control source")
    signed = subprocess.check_output(["zstd", "-dc", "--", erofs])
    check(signed.endswith(MARKER), "EROFS is not a signed input")
    end = len(signed) - len(MARKER)
    footer = signed[end - 12:end]
    sig_len, = struct.unpack(">I", footer[8:])
    elf_end = end - 12 - sig_len
    check(elf_end > 64 and sig_len > 0 and signed.startswith(b"\x7fELF"),
          "malformed signed control module")
    # The signed original remains intact; the unsigned copy never leaves the
    # disposable guest initramfs and must not load with enforcement active.
    (root / "unsigned-erofs.ko").write_bytes(signed[:elf_end])
    print(f"PACKAGE_SHA256={pin}")
    print(f"KERNEL_SHA256={hashlib.sha256(kern.read_bytes()).hexdigest()}")
    print(f"PACKAGE_MODULES={len(files)}")
    print(f"PACKAGE_RELEASE={RELEASE}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest", type=Path)
    p.add_argument("source")
    p.add_argument("sha256")
    p.add_argument("work", type=Path)
    a = p.parse_args()
    prepare(a.manifest, a.source, a.sha256, a.work)

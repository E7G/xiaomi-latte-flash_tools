#!/usr/bin/env bash
# Boot a throwaway USB copy, not a disk attached to the runner or tablet.
set -euo pipefail
export LC_ALL=C
umask 077
image=$(realpath -e -- "$1")
expected=$2
out=$(realpath -e -- "$3")
[[ "$expected" =~ ^[a-f0-9]{64}$ ]]
test "$(sha256sum < "$image")" = "$expected  -"
test -z "$(find "$out" -mindepth 1 -maxdepth 1 -print -quit)"
script=$(cd -- "$(dirname -- "$0")" && pwd)
scratch=$(mktemp -d "$out/fixture.XXXXXXXX")
trap 'rc=$?; printf "%s\n" "$rc" > "$out/exit-status"; exit "$rc"' EXIT
cd -- "$scratch"
raw="$scratch/preview-usb.raw"
size=$(( (8 * 1024 + 256 + 2) * 1024 * 1024 ))
# Refuse a substituted or differently sized variant before allocating a raw copy.
bytes=$(xz --robot --list -- "$image" | awk '$1 == "totals" {print $5}')
test "$bytes" = "$size"
xz -dc -- "$image" | dd of="$raw" bs=4M conv=sparse status=none
test "$(stat -c %s "$raw")" = "$size"
sgdisk --verify "$raw" > "$out/gpt.txt"
grep -Fq 'No problems found.' "$out/gpt.txt"
sgdisk --info=1 "$raw" >> "$out/gpt.txt"
sgdisk --info=2 "$raw" >> "$out/gpt.txt"
grep -Fq 'First sector: 2048 ' "$out/gpt.txt"
grep -Fq 'First sector: 526336 ' "$out/gpt.txt"
esp="$raw@@1048576"
mcopy -i "$esp" ::EFI/BOOT/BOOTX64.EFI original.efi
mcopy -i "$esp" ::grub/grub.cfg original-grub.cfg
python3 -B "$script/instrument_r32_usb_menu.py" original-grub.cfg vm-grub.cfg
grub-script-check vm-grub.cfg
mcopy -o -i "$esp" vm-grub.cfg ::grub/grub.cfg
mcopy -i "$esp" ::EFI/BOOT/BOOTX64.EFI checked.efi
cmp original.efi checked.efi
printf 'USB_XZ_SHA256=%s\nBOOTX64_SHA256=%s\n' "$expected" "$(sha256sum < original.efi | cut -d' ' -f1)" > "$out/input.txt"

cp /usr/share/OVMF/OVMF_VARS_4M.fd vars.fd
python3 -B - "$raw" "$out/guest.serial.log" <<'PY'
import re
from pathlib import Path
import subprocess
import sys
import time

disk, log = map(Path, sys.argv[1:])
message = log.parent / "qemu.log"
with message.open("wb") as errors:
    vm = subprocess.Popen([
        "qemu-system-x86_64", "-machine", "q35,accel=tcg",
        "-cpu", "Westmere,family=6,model=76,stepping=3,movbe=on,rdrand=on",
        "-smp", "2", "-m", "2048", "-nodefaults", "-display", "none", "-vga", "std",
        "-serial", f"file:{log}", "-monitor", "none", "-nic", "none", "-no-reboot",
        "-smbios", "type=1,manufacturer=IsolatedFixture,product=NotMiPad2",
        "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd",
        "-drive", "if=pflash,format=raw,file=vars.fd",
        "-device", "qemu-xhci,id=xhci",
        "-drive", f"if=none,format=raw,id=usbpreview,file={disk}",
        "-device", "usb-storage,bus=xhci.0,drive=usbpreview,removable=on,bootindex=1",
    ], stdin=subprocess.DEVNULL, stdout=errors, stderr=errors)
    try:
        deadline = time.monotonic() + 200
        while time.monotonic() < deadline and vm.poll() is None:
            time.sleep(1)
            s = log.read_text(errors="replace") if log.exists() else ""
            s = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", s).replace("\r", "")
            if ("R32_USB_GRUB_ENTERED=1" in s and
                re.search(r"Linux version 7\.2\.15-mipad2-integrated-r32(?=\s)", s) and
                (re.search(r"Reached target .*Multi-User System", s) or "mipad2 login:" in s)):
                (log.parent / "guest.clean.log").write_text(s)
                break
        else:
            raise SystemExit("did not observe USB firmware-to-R32 rootfs boot")
    finally:
        if vm.poll() is None:
            vm.terminate()
            try:
                vm.wait(timeout=10)
            except subprocess.TimeoutExpired:
                vm.kill()
                vm.wait()
PY
printf 'PASS: actual USB preview booted R32 to userspace in an isolated VM\n' | tee "$out/result.txt"

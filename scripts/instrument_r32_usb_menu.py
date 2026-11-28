#!/usr/bin/env python3
"""Add a serial console only to the disposable copy of an R32 USB image."""
import re
from pathlib import Path
import sys

KERNEL = re.compile(r'^\s*(?:linux|linuxefi)\s+(?:"([^"]+)"|\'([^\']+)\'|(\S+))\s+')
FLAGS = (
    "console=ttyS0,115200 loglevel=6 systemd.log_target=console "
    "systemd.unit=multi-user.target systemd.show_status=yes plymouth.enable=0 "
    "systemd.mask=mipad2-usb-installer.service"
)


def instrument(raw):
    out = []
    found = 0
    for line in raw.splitlines():
        m = KERNEL.match(line)
        if not m:
            out.append(line)
            continue
        path = next(v for v in m.groups() if v is not None)
        if path.rsplit("/", 1)[-1] != "vmlinuz-linux-latte-integrated-7-2":
            raise ValueError("unexpected kernel in qualified USB GRUB configuration")
        args = line[m.end():]
        if not re.search(r"(?:^|\s)root=UUID=[a-fA-F0-9-]+(?=\s|$)", args):
            raise ValueError("missing original root UUID")
        if not re.search(r"(?:^|\s)rootflags=subvol=/?" + re.escape("@") + r"(?=[\s,]|$)", args):
            raise ValueError("missing original Btrfs root subvolume")
        if "\\" in args or ";" in args or "#" in args:
            raise ValueError("unexpected continuation or chained Linux command")
        args = re.sub(r"(?<!\S)(?:quiet|splash|(?:console|loglevel|plymouth\.enable|systemd\.unit)=[^\s]+)(?=\s|$)", "", args)
        out += [
            "    insmod serial",
            "    serial --unit=0 --speed=115200",
            "    terminal_output serial",
            "    echo R32_USB_GRUB_ENTERED=1",
            line[:m.end()] + args.rstrip() + " " + FLAGS,
        ]
        found += 1
    if not found:
        raise ValueError("no qualified boot entries found")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    source, target = map(Path, sys.argv[1:])
    result = instrument(source.read_text())
    with target.open("x") as f:
        f.write(result)

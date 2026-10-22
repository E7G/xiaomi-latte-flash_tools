#!/usr/bin/env python3
"""Stage tracked support sources, not transient makepkg $srcdir directories."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


PAYLOAD = [
    ('packages/mipad2-camera-support/shisp_2401a0_v21.bin', 'usr/lib/firmware/intel/ipu/shisp_2401a0_v21.bin', 0o644),
    ('packages/mipad2-camera-support/mipad2-camera.conf', 'etc/modules-load.d/mipad2-camera.conf', 0o644),
    ('brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt', 'usr/lib/firmware/brcm/brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt', 0o644),
    ('BCM4356A2.hcd', 'usr/lib/firmware/brcm/BCM4356A2.hcd', 0o644),
    ('packages/mipad2-alsa-ucm/cht-bsw-rt5659.conf', 'usr/share/alsa/ucm2/conf.d/cht-bsw-rt5659/cht-bsw-rt5659.conf', 0o644),
    ('packages/mipad2-alsa-ucm/HiFi.conf', 'usr/share/alsa/ucm2/conf.d/cht-bsw-rt5659/HiFi.conf', 0o644),
    ('packages/mipad2-usb-serial/mipad2-usb-serial', 'usr/local/libexec/mipad2-usb-serial', 0o755),
    ('packages/mipad2-usb-serial/mipad2-usb-serial.service', 'etc/systemd/system/mipad2-usb-serial.service', 0o644),
    ('packages/mipad2-usb-serial/mipad2-usb-serial-sleep', 'usr/lib/systemd/system-sleep/mipad2-usb-serial', 0o755),
    ('packages/mipad2-recovery/mp2-backup', 'usr/local/sbin/mp2-backup', 0o755),
    ('packages/mipad2-recovery/mp2-recover', 'usr/local/sbin/mp2-recover', 0o755),
    ('packages/mipad2-test-no-idle/mp2-test-no-idle', 'usr/local/sbin/mp2-test-no-idle', 0o755),
    ('packages/mipad2-test-no-idle/mp2-test-no-idle-denial', 'usr/local/libexec/mp2-test-no-idle-denial', 0o755),
    ('packages/mipad2-test-no-idle/mipad2-test-no-idle.service', 'etc/systemd/system/mipad2-test-no-idle.service', 0o644),
    ('tests/mipad2-hardware-smoke.sh', 'usr/local/libexec/mipad2-hardware-smoke', 0o755),
    ('tests/mipad2-camera-test.sh', 'usr/local/libexec/mipad2-camera-test', 0o755),
    ('tests/mipad2-camera-select.sh', 'usr/local/libexec/mipad2-camera-select', 0o755),
    ('tests/mipad2-hardware-audit.service', 'etc/systemd/system/mipad2-hardware-audit.service', 0o644),
]
PAYLOAD += [(f'packages/{pkg}/README', f'usr/share/doc/{pkg}/README', 0o644)
            for pkg in ('mipad2-camera-support', 'mipad2-alsa-ucm', 'mipad2-usb-serial',
                        'mipad2-recovery', 'mipad2-test-no-idle')]
MANIFEST = 'usr/share/doc/linux-latte-cachyos/support-payload.json'


def contained(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError(f'Invalid relative payload path: {relative}')
    target = root / path
    if root not in target.resolve().parents:
        raise ValueError(f'Payload escapes root: {target}')
    if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != root and root in p.parents):
        raise ValueError(f'Symlinked payload path: {target}')
    return target


def stage(source_root, package_root, dry_run=False):
    source_root = Path(source_root).resolve()
    package_root = Path(package_root).resolve()
    if source_root == package_root or source_root in package_root.parents:
        raise ValueError('Stage outside the source tree')
    prepared = []
    seen = set()
    # Validate the complete plan before creating/writing anything.
    for source, destination, mode in PAYLOAD:
        src = contained(source_root, 'fix_file/' + source)
        dst = contained(package_root, destination)
        if destination in seen:
            raise ValueError(f'Duplicate payload destination: {destination}')
        seen.add(destination)
        if not src.is_file():
            raise FileNotFoundError(f'Kernel source payload missing: {src}')
        prepared.append((src, dst, mode, hashlib.sha256(src.read_bytes()).hexdigest()))
    manifest_path = contained(package_root, MANIFEST)
    manifest = {'schema': 1, 'source_layout': 'tracked fix_file package sources',
                'files': {str(dst.relative_to(package_root)): {
                    'source': str(src.relative_to(source_root)), 'sha256': sha, 'mode': oct(mode)}
                    for src, dst, mode, sha in prepared}}
    if dry_run:
        return manifest
    for src, dst, mode, sha in prepared:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        dst.chmod(mode)
        if hashlib.sha256(dst.read_bytes()).hexdigest() != sha:
            raise RuntimeError(f'Payload copy verification failed: {dst}')
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    manifest_path.chmod(0o644)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root')
    parser.add_argument('package_root')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    result = stage(args.source_root, args.package_root, args.dry_run)
    print(json.dumps(result, indent=2))

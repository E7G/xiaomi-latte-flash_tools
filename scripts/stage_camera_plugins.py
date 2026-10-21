#!/usr/bin/env python3
"""Stage hash-pinned functional plugins, optionally source AAC, into a NEW package tree.

Not a complete camera package: no app, launcher, rootfs mutation or device
acceptance. Caller supplies the exact build receipt SHA, not an inferred latest.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

EXPECTED = {
    'gst-plugins-base': 'libgstencoding.so',
    'gst-plugins-good': 'libgstvideofilter.so',
    'gst-plugins-bad': 'libgstva.so',
}
ABI = {'gstreamer-1.0', 'gstreamer-base-1.0', 'gstreamer-video-1.0',
       'gstreamer-plugins-bad-1.0'}
AAC_ABI = {'libavcodec': '63.1.101', 'libavformat': '63.1.101',
           'libavfilter': '12.1.101', 'libavutil': '61.1.101'}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def regular(path, maximum):
    require(path.is_file() and not path.is_symlink(), f'Not a regular file: {path}')
    require(0 < path.stat().st_size <= maximum, f'File size outside bound: {path}')


def elf_check(path):
    with path.open('rb') as stream:
        require(stream.read(4) == b'\x7fELF', 'Not an ELF plugin')
    header = subprocess.check_output(['readelf', '-h', str(path)], text=True)
    require('Advanced Micro Devices X86-64' in header, 'Not an x86-64 plugin')
    dynamic = subprocess.check_output(['readelf', '-d', str(path)], text=True)
    require('RPATH' not in dynamic and 'RUNPATH' not in dynamic,
            'Build/runtime search path in exported plugin')
    needed = re.findall(r'\(NEEDED\).*?\[([^]]+)\]', dynamic)
    require(needed and all('/' not in value and '\\' not in value for value in needed),
            'Invalid dependency filenames')
    return needed


def aac_plan(root, package_root, receipt_sha256):
    require(re.fullmatch(r'[0-9a-f]{64}', receipt_sha256 or ''), 'Explicit AAC receipt SHA required')
    root = Path(root)
    require(not root.is_symlink(), 'Symlinked AAC root')
    root = root.resolve()
    require(root != package_root and root not in package_root.parents,
            'Package root must be outside AAC build tree')
    path = root / 'receipt.json'
    regular(path, 1024**2)
    require(sha(path) == receipt_sha256, 'AAC receipt hash mismatch')
    receipt = json.loads(path.read_text())
    require(receipt.get('schema') == 1 and receipt.get('state') == 'aac-plugin-built-host-only'
            and receipt.get('upstream_version') == '1.28.7', 'Wrong AAC build state/version')
    require(set(receipt.get('gstreamer_build_abi', {})) == ABI
            and all(v == '1.28.7' for v in receipt['gstreamer_build_abi'].values())
            and receipt.get('ffmpeg_build_abi') == AAC_ABI, 'AAC build ABI mismatch')
    recipe = receipt.get('recipe_sha256', '')
    require(re.fullmatch(r'[0-9a-f]{64}', recipe), 'Missing AAC recipe hash')
    require(receipt.get('plugin') == 'plugins/libgstlibav.so'
            and receipt.get('build_rpath_removed') is True
            and receipt.get('sdk_libraries_deployed') is False, 'Wrong AAC export plan')
    require(not (root / 'plugins').is_symlink(), 'Symlinked AAC plugin directory')
    source = root / 'plugins/libgstlibav.so'
    regular(source, 32 * 1024**2)
    require(sha(source) == receipt.get('binary_sha256')
            and source.stat().st_size == receipt.get('bytes'), 'AAC plugin hash/size mismatch')
    needed = elf_check(source)
    require(needed == receipt.get('needed_libraries')
            and {'libavcodec.so.63', 'libavutil.so.61'} <= set(needed), 'AAC dependency mismatch')
    relative = 'usr/local/lib/mipad2-gst-aac-source/' + recipe + '/plugin/libgstlibav.so'
    value = dict(sha256=receipt['binary_sha256'], bytes=receipt['bytes'], mode='0o755',
                 needed_libraries=needed)
    return source, relative, value, recipe


def stage(build_root, package_root, expected_receipt_sha256, dry_run=False,
          aac_root=None, aac_receipt_sha256=None):
    require(re.fullmatch(r'[0-9a-f]{64}', expected_receipt_sha256 or ''),
            'Explicit 64-character build receipt SHA-256 required')
    build_root, package_root = Path(build_root), Path(package_root)
    require(not build_root.is_symlink() and not package_root.is_symlink(), 'Symlinked root')
    build_root, package_root = build_root.resolve(), package_root.resolve()
    require(not package_root.exists(), 'Package root must be new')
    require(package_root != build_root and build_root not in package_root.parents,
            'Package root must be outside the build tree')
    require((aac_root is None) == (aac_receipt_sha256 is None),
            'AAC root and explicit receipt SHA must be supplied together')
    receipt_path = build_root / 'receipt.json'
    regular(receipt_path, 1024**2)
    require(sha(receipt_path) == expected_receipt_sha256, 'Build receipt hash mismatch')
    receipt = json.loads(receipt_path.read_text())
    require(receipt.get('schema') == 1 and receipt.get('state') == 'plugins-built-host-only',
            'Not a completed source build')
    require(receipt.get('upstream_version') == '1.28.7', 'Wrong GStreamer version')
    require(set(receipt.get('build_abi', {})) == ABI
            and all(value == '1.28.7' for value in receipt['build_abi'].values()),
            'Wrong or incomplete build ABI')
    recipe = receipt.get('recipe_sha256', '')
    require(re.fullmatch(r'[0-9a-f]{64}', recipe), 'Missing recipe hash')
    components = receipt.get('components', [])
    require(len(components) == 3 and {c.get('name') for c in components} == set(EXPECTED),
            'Wrong component set')
    prefix = 'usr/local/lib/mipad2-gst-functional/' + recipe + '/plugin/'
    files = {}
    planned = []
    for component in components:
        name = EXPECTED[component['name']]
        require(component.get('compiled') is True and component.get('build_rpath_removed') is True,
                'Component not compiled/exported')
        require(component.get('plugin') == 'plugins/' + name, 'Unexpected plugin path')
        source = build_root / 'plugins' / name
        require(not (build_root / 'plugins').is_symlink(), 'Symlinked plugin directory')
        regular(source, 32 * 1024**2)
        require(sha(source) == component.get('binary_sha256')
                and source.stat().st_size == component.get('bytes'), 'Plugin hash/size mismatch')
        needed = elf_check(source)
        require(needed == component.get('needed_libraries'), 'Dependency manifest mismatch')
        relative = prefix + name
        files[relative] = dict(sha256=component['binary_sha256'], bytes=component['bytes'],
                               mode='0o755', needed_libraries=needed)
        planned.append((source, package_root / relative))
    aac_recipe = None
    if aac_root is not None:
        source, relative, value, aac_recipe = aac_plan(aac_root, package_root, aac_receipt_sha256)
        require(relative not in files, 'Duplicate AAC payload destination')
        files[relative] = value
        planned.append((source, package_root / relative))
    manifest = dict(schema=1, source_build_receipt_sha256=expected_receipt_sha256,
                    recipe_sha256=recipe, upstream_version='1.28.7', files=files,
                    app_included=False, aac_included=aac_recipe is not None, launcher_included=False,
                    diagnostic_plugins_included=False, system_library_replacement=False,
                    image_qualified=False, device_acceptance_inferred=False)
    if aac_recipe is not None:
        manifest.update(aac_source_build_receipt_sha256=aac_receipt_sha256,
                        aac_recipe_sha256=aac_recipe, aac_ffmpeg_build_abi=AAC_ABI,
                        sdk_libraries_deployed=False)
    if dry_run:
        return manifest
    # All sources/receipt/ELF metadata checked before the first output write.
    package_root.mkdir(parents=True, exist_ok=False)
    for source, destination in planned:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o755)
        require(sha(destination) == files[str(destination.relative_to(package_root))]['sha256'],
                'Staged plugin hash mismatch')
    metadata = package_root / 'usr/share/doc/mipad2-gst-functional/manifest.json'
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(json.dumps(manifest, indent=2) + '\n')
    metadata.chmod(0o644)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build_root', type=Path)
    parser.add_argument('package_root', type=Path)
    parser.add_argument('--receipt-sha256', required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--aac-root', type=Path)
    parser.add_argument('--aac-receipt-sha256')
    args = parser.parse_args()
    print(json.dumps(stage(args.build_root, args.package_root, args.receipt_sha256,
                           args.dry_run, args.aac_root, args.aac_receipt_sha256), indent=2))

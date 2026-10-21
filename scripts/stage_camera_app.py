#!/usr/bin/env python3
"""Compose a pinned source app + FOUR source plugins into a new candidate tree.

No rootfs installation, stable launcher replacement, default promotion or image
qualification. All inputs validated before creating the output directory.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
from stage_camera_plugins import ABI, elf_check, regular, require, sha, stage


OVERRIDE = '''[org.gnome.Snapshot]
enable-hardware-encoding=true
enable-audio-recording=true
play-shutter-sound=false
is-maximized=true
countdown=0
'''


def app_plan(root, destination, pin):
    require(re.fullmatch(r'[0-9a-f]{64}', pin or ''), 'Explicit app receipt SHA required')
    root = Path(root)
    require(not root.is_symlink(), 'Symlinked app build root')
    root = root.resolve()
    require(root != destination and root not in destination.parents, 'Nested app output')
    receipt_path = root/'receipt.json'
    regular(receipt_path, 1024**2)
    require(sha(receipt_path) == pin, 'App receipt hash mismatch')
    receipt = json.loads(receipt_path.read_text())
    require(receipt.get('schema') == 1 and receipt.get('state') == 'source-application-built-staged-host-only',
            'App build incomplete')
    commit = receipt.get('source_commit', '')
    require(re.fullmatch(r'[0-9a-f]{40}', commit), 'Explicit app commit missing')
    prefix = '/usr/local/lib/mipad2-camera-source-'+commit[:12]
    require(receipt.get('prefix') == prefix, 'App compiled prefix mismatch')
    require(receipt.get('cargo_locked') is True and receipt.get('cargo_offline') is True
            and receipt.get('cargo_profile') == 'release' and receipt.get('rpath_absent') is True,
            'App build policy mismatch')
    require(set(receipt.get('gstreamer_build_abi', {})) == ABI
            and all(v == '1.28.7' for v in receipt['gstreamer_build_abi'].values()), 'App ABI mismatch')
    require(re.fullmatch(r'[0-9a-f]{64}', receipt.get('recipe_sha256', '')), 'App recipe missing')
    package = root/'package'
    require(package.is_dir() and not package.is_symlink(), 'App package missing/symlinked')
    files = receipt.get('files', {})
    require(isinstance(files, dict) and len(files) > 10, 'Incomplete app file manifest')
    actual = set()
    for path in package.rglob('*'):
        require(not path.is_symlink(), 'Symlinked app payload')
        if path.is_file():
            actual.add(path.relative_to(package).as_posix())
        else:
            require(path.is_dir(), 'Special app payload file')
    require(actual == set(files), 'Unexpected/missing app payload file')
    planned = []
    for name, entry in files.items():
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and '..' not in relative.parts
                and relative.as_posix() == name and name.startswith(prefix.lstrip('/')+'/'),
                'App path outside private prefix')
        source = package/name
        regular(source, 64*1024**2)
        require(entry.get('mode') in ['0o644', '0o755'] and sha(source) == entry.get('sha256')
                and source.stat().st_size == entry.get('bytes'), 'App file hash/size/mode mismatch')
        planned.append((source, name, int(entry['mode'], 8)))
    binary_name = prefix.lstrip('/')+'/bin/snapshot'
    require(binary_name in files and files[binary_name]['sha256'] == receipt.get('application_sha256'),
            'Application binary mismatch')
    needed = elf_check(package/binary_name)
    return receipt, planned, needed


def compose(app_root, output, app_receipt_sha256, plugin_root, plugin_receipt_sha256,
            aac_root, aac_receipt_sha256, dry_run=False):
    output = Path(output)
    require(not output.is_symlink(), 'Symlinked output')
    output = output.resolve()
    require(not output.exists(), 'Output must be new')
    app, planned, needed = app_plan(app_root, output, app_receipt_sha256)
    plugins = stage(plugin_root, output, plugin_receipt_sha256, True, aac_root, aac_receipt_sha256)
    require(plugins.get('aac_included') is True, 'Source AAC required')
    require(not (set(app['files']) & set(plugins['files'])), 'App/plugin destination collision')
    require(shutil.which('glib-compile-schemas') is not None, 'glib-compile-schemas missing')
    launcher = Path(__file__).with_name('camera_candidate_launcher.py')
    regular(launcher, 128*1024)
    compile(launcher.read_text(), str(launcher), 'exec')
    prefix = app['prefix']
    name = 'mipad2-camera-source-'+app['source_commit'][:12]
    config = dict(schema=1, prefix=prefix, source_commit=app['source_commit'], profile_name=name,
                  plugin_directories=sorted({str(PurePosixPath('/'+n).parent) for n in plugins['files']}),
                  diagnostic_actions=False, background_capture=False)
    manifest = dict(schema=1, state='camera-candidate-planned', source_commit=app['source_commit'],
                    app_receipt_sha256=app_receipt_sha256, application_sha256=app['application_sha256'],
                    plugin_build_receipt_sha256=plugin_receipt_sha256,
                    aac_build_receipt_sha256=aac_receipt_sha256,
                    prefix=prefix, launcher_recipe_sha256=sha(launcher),
                    composer_sha256=sha(__file__), app_needed_libraries=needed,
                    app_included=True, source_plugin_count=4, launcher_included=True,
                    private_settings=True, shutter_sound_default=False, dbus_activatable=False,
                    stable_desktop_changed=False, system_library_replacement=False,
                    sdk_libraries_deployed=False, device_tested=False, image_qualified=False)
    if dry_run:
        return manifest
    stage(plugin_root, output, plugin_receipt_sha256, False, aac_root, aac_receipt_sha256)
    for source, relative, mode in planned:
        path = output/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, path)
        path.chmod(mode)
        require(sha(path) == app['files'][relative]['sha256'], 'Copied app hash changed')
    app_base = output/prefix.lstrip('/')
    launch_path = app_base/'bin/mipad2-camera-candidate'
    shutil.copyfile(launcher, launch_path)
    launch_path.chmod(0o755)
    profile_path = app_base/'bin/candidate-profile.json'
    profile_path.write_text(json.dumps(config, indent=2)+'\n')
    profile_path.chmod(0o644)
    schemas = app_base/'share/glib-2.0/schemas'
    (schemas/'90_mipad2_candidate.gschema.override').write_text(OVERRIDE)
    subprocess.run(['glib-compile-schemas', '--strict', str(schemas)], check=True, capture_output=True)
    desktop = output/'usr/share/applications'/('org.gnome.Snapshot.MiPad2Source'+app['source_commit'][:12]+'.desktop')
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text('[Desktop Entry]\nType=Application\nName=Camera (MiPad2 source candidate)\n'
                       'Name[zh_CN]=相机（MiPad2 源码候选）\nExec='+prefix+'/bin/mipad2-camera-candidate\n'
                       'Icon='+prefix+'/share/icons/hicolor/scalable/apps/org.gnome.Snapshot.svg\n'
                       'Terminal=false\nDBusActivatable=false\nCategories=GNOME;GTK;AudioVideo;Video;\n', encoding='utf-8')
    desktop.chmod(0o644)
    files = {}
    for p in sorted(output.rglob('*')):
        require(not p.is_symlink(), 'Staged symlink')
        if p.is_file():
            files[p.relative_to(output).as_posix()] = dict(sha256=sha(p), bytes=p.stat().st_size,
                                                        mode=oct(p.stat().st_mode & 0o777))
    manifest.update(state='camera-candidate-staged-host-only', files=files,
                    desktop_file=desktop.relative_to(output).as_posix())
    metadata = output/'usr/share/doc/mipad2-camera-source/manifest.json'
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(json.dumps(manifest, indent=2)+'\n')
    metadata.chmod(0o644)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['app-root', 'output', 'plugin-root', 'aac-root']:
        p.add_argument('--'+key, required=True, type=Path)
    for key in ['app-receipt-sha256', 'plugin-receipt-sha256', 'aac-receipt-sha256']:
        p.add_argument('--'+key, required=True)
    p.add_argument('--dry-run', action='store_true')
    args = vars(p.parse_args())
    print(json.dumps(compose(**args), indent=2))

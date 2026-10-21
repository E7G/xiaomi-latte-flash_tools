#!/usr/bin/env python3
"""Opt-in source camera payload merge into an OFFLINE Arch/CachyOS rootfs.

Hash-pinned composition only; no default promotion. Existing files are never
overwritten. A failed loader check retains files and a failed build receipt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
from stage_camera_plugins import elf_check, regular, require, sha

METADATA = 'usr/share/doc/mipad2-camera-source/manifest.json'
LEDGER = 'var/lib/mipad2-camera-source/install-receipt.json'
ABI_PACKAGES = {'gstreamer':'1.28.7', 'gst-plugins-base-libs':'1.28.7',
                'gst-plugins-bad-libs':'1.28.7', 'gst-plugins-good':'1.28.7',
                'ffmpeg':'9.0.1'}


def contained(root, name):
    rel = PurePosixPath(name)
    require(not rel.is_absolute() and '..' not in rel.parts and rel.as_posix() == name,
            'Noncanonical relative path')
    p = root/name
    require(not p.is_symlink() and all(not a.is_symlink() for a in p.parents if a != root.parent),
            'Symlinked payload/destination path')
    require(p.is_relative_to(root), 'Path escapes root')
    return p


def plan(package, pin):
    require(re.fullmatch(r'[0-9a-f]{64}', pin or ''), 'Explicit candidate manifest SHA required')
    package = Path(package)
    require(not package.is_symlink(), 'Symlinked candidate root')
    package = package.resolve()
    p = contained(package, METADATA)
    regular(p, 2*1024**2)
    require(sha(p) == pin, 'Candidate manifest hash mismatch')
    m = json.loads(p.read_text())
    require(m.get('schema') == 1 and m.get('state') == 'camera-candidate-staged-host-only'
            and m.get('source_plugin_count') == 4, 'Incomplete camera composition')
    require(all(m.get(k) is True for k in ['app_included','launcher_included','private_settings'])
            and all(m.get(k) is False for k in ['system_library_replacement','sdk_libraries_deployed',
                                              'stable_desktop_changed','dbus_activatable']),
            'Candidate isolation contract mismatch')
    commit = m.get('source_commit', '')
    require(re.fullmatch(r'[0-9a-f]{40}', commit), 'Missing source commit')
    prefix = 'usr/local/lib/mipad2-camera-source-'+commit[:12]
    require(m.get('prefix') == '/'+prefix, 'Compiled private prefix mismatch')
    desktop = 'usr/share/applications/org.gnome.Snapshot.MiPad2Source'+commit[:12]+'.desktop'
    require(m.get('desktop_file') == desktop, 'Unexpected desktop path')
    files = m.get('files', {})
    require(isinstance(files, dict) and len(files)>20 and METADATA not in files, 'Incomplete file manifest')
    allowed_plugin = re.compile(r'usr/local/lib/(?:mipad2-gst-functional|mipad2-gst-aac-source)/[0-9a-f]{64}/plugin/(libgstencoding|libgstvideofilter|libgstva|libgstlibav)\.so')
    actual = set()
    for path in package.rglob('*'):
        require(not path.is_symlink(), 'Symlinked payload')
        if path.is_file():actual.add(path.relative_to(package).as_posix())
        else:require(path.is_dir(), 'Special payload file')
    require(actual == set(files)|{METADATA}, 'Unexpected/missing payload member')
    planned=[];elf=[];plugin_names=[]
    for name, value in files.items():
        source = contained(package, name)
        allowed = (name.startswith(prefix+'/') or allowed_plugin.fullmatch(name) is not None
                   or name == desktop or name == 'usr/share/doc/mipad2-gst-functional/manifest.json')
        require(allowed, 'Payload outside private candidate paths')
        regular(source, 64*1024**2)
        require(value.get('mode') in ['0o644','0o755'] and type(value.get('bytes')) is int
                and source.stat().st_size == value['bytes'] and sha(source) == value.get('sha256'),
                'Payload hash/size/mode mismatch')
        planned.append((source,name,int(value['mode'],8)))
        if name == prefix+'/bin/snapshot' or allowed_plugin.fullmatch(name):
            elf_check(source);elf.append('/'+name)
            if name.endswith('.so'):plugin_names.append(source.name)
    require(sorted(plugin_names)==sorted(['libgstencoding.so','libgstvideofilter.so','libgstva.so','libgstlibav.so'])
            and len(elf)==5, 'Wrong application/plugin ELF set')
    binary = contained(package, prefix+'/bin/snapshot')
    require(sha(binary)==m.get('application_sha256'), 'Application hash mismatch')
    wrapper=prefix+'/bin/mipad2-camera-candidate'
    required=[wrapper,prefix+'/bin/candidate-profile.json',
              prefix+'/share/glib-2.0/schemas/gschemas.compiled',
              prefix+'/share/glib-2.0/schemas/org.gnome.Snapshot.gschema.xml',
              prefix+'/share/glib-2.0/schemas/90_mipad2_candidate.gschema.override',
              prefix+'/share/snapshot/resources.gresource']
    require(all(name in files for name in required), 'Required private runtime resources missing')
    require(files[prefix+'/bin/snapshot']['mode']=='0o755' and files[wrapper]['mode']=='0o755'
            and sha(package/wrapper)==m.get('launcher_recipe_sha256'), 'Launcher/executable mismatch')
    config=json.loads((package/required[1]).read_text())
    plugin_dirs=sorted({str(PurePosixPath('/'+name).parent) for name in files if allowed_plugin.fullmatch(name)})
    require(config.get('prefix')=='/'+prefix and config.get('source_commit')==commit
            and config.get('plugin_directories')==plugin_dirs
            and config.get('diagnostic_actions') is False and config.get('background_capture') is False,
            'Private production profile mismatch')
    text=contained(package,desktop).read_text()
    require('DBusActivatable=false\n' in text
            and 'Exec=/'+prefix+'/bin/mipad2-camera-candidate\n' in text, 'Desktop bypasses wrapper')
    planned.append((p,METADATA,0o644))
    return m,planned,elf


def installed_versions(root):
    versions={}
    database=contained(root,'var/lib/pacman/local')
    for file in database.glob('*/desc'):
        contained(root,file.relative_to(root).as_posix())
        regular(file,1024**2)
        fields=file.read_text().splitlines()
        def value(key):
            return fields[fields.index('%'+key+'%')+1] if '%'+key+'%' in fields else None
        name=value('NAME')
        if name in ABI_PACKAGES:
            require(name not in versions,'Duplicate ABI package record')
            version=value('VERSION');require(isinstance(version,str),'Version missing')
            versions[name]=version.split(':')[-1].rsplit('-',1)[0]
    require(versions==ABI_PACKAGES,'Rootfs GStreamer/FFmpeg ABI package versions mismatch')
    return versions


def verify_loader(root, elfs):
    env={k:v for k,v in os.environ.items() if not k.startswith(('GST_','MIPAD2_'))
         and k not in ['LD_LIBRARY_PATH','LD_PRELOAD']}
    env.update(LC_ALL='C',LANG='C')
    checks=[]
    for binary in elfs:
        # ldd relocation probing needs no /proc, /sys, /dev bind mounts or
        # application startup. Keep this gate in a minimal plain chroot.
        q=subprocess.run(['chroot',str(root),'/usr/bin/ldd','-r',binary],
                         env=env,capture_output=True,text=True,timeout=60)
        log=root/Path(LEDGER).parent/('loader-'+str(len(checks))+'.log')
        with log.open('x') as stream:stream.write(q.stdout+q.stderr)
        require(q.returncode==0 and 'not found' not in q.stdout+q.stderr
                and 'undefined symbol' not in q.stdout+q.stderr, 'Rootfs native loader check failed: '+binary)
        checks.append(dict(binary=binary,exit_code=0))
    return checks


def install(package, rootfs, pin, dry_run=False):
    m,planned,elfs=plan(package,pin)
    root=Path(rootfs)
    require(not root.is_symlink(),'Symlinked rootfs')
    root=root.resolve();package=Path(package).resolve()
    require(root != Path('/') and root.is_dir() and (root/'usr/lib').is_dir()
            and (root/'etc').is_dir(), 'Offline rootfs directory required; live / forbidden')
    require(root!=package and root not in package.parents and package not in root.parents,
            'Nested package/rootfs')
    versions=installed_versions(root)
    destinations=[contained(root,name) for _,name,_ in planned]
    receipt_path=contained(root,LEDGER)
    require(not receipt_path.exists() and all(not p.exists() for p in destinations), 'Existing candidate destination')
    r=dict(schema=1,state='camera-rootfs-install-planned',manifest_sha256=pin,
           source_commit=m['source_commit'],files=len(planned),runtime_abi_versions=versions,
           stable_default_changed=False,system_packages_changed=False,
           default_promotion=False,image_boot_qualified=False,loader_checks=[])
    if dry_run:return r
    require(os.geteuid()==0,'Root required for offline rootfs install')
    require(shutil.which('chroot') is not None,'chroot required')
    require(shutil.disk_usage(root).free>sum(p.stat().st_size for p,_,_ in planned)+64*1024**2,
            'Rootfs free-space reserve insufficient')
    receipt_path.parent.mkdir(parents=True,exist_ok=True)
    def save():
        receipt_path.write_text(json.dumps(r,indent=2)+'\n');receipt_path.chmod(0o644)
    r['state']='installing-camera-candidate';save()
    try:
        expected={name:value['sha256'] for name,value in m['files'].items()}|{METADATA:pin}
        for (source,name,mode),destination in zip(planned,destinations):
            data=source.read_bytes()
            require(hashlib.sha256(data).hexdigest()==expected[name],'Source changed after validation')
            destination.parent.mkdir(parents=True,exist_ok=True)
            with destination.open('xb') as stream:stream.write(data)
            destination.chmod(mode)
            require(sha(destination)==expected[name],'Copy hash mismatch')
        r['loader_checks']=verify_loader(root,elfs)
        require(len(r['loader_checks'])==5,'Incomplete loader checks')
        r['state']='camera-candidate-installed-rootfs-loader-pass';save();return r
    except BaseException as error:
        r.update(state='failed-retained-do-not-publish-image',error_type=type(error).__name__);save();raise


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('package',type=Path)
    p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--rootfs',type=Path)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--validate-only',action='store_true')
    a=p.parse_args()
    if a.validate_only:
        require(a.rootfs is None and not a.dry_run,'Validation-only does not accept rootfs/dry-run')
        m,planned,elf=plan(a.package,a.manifest_sha256)
        print(json.dumps(dict(state='source-camera-payload-validated',files=len(planned),elf_files=len(elf),source_commit=m['source_commit'])))
    else:
        require(a.rootfs is not None,'Explicit offline rootfs required')
        print(json.dumps(install(a.package,a.rootfs,a.manifest_sha256,a.dry_run),indent=2))

#!/usr/bin/env python3
"""Validate an externally pinned integrated6.14/7.2 ALPM package before image mutation."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
from package_integrated_kernel import PKGBASE,PKGBASE_72,file_pin,require,sha,identity


def check(package,pin):
    package=Path(package);file_pin(package,pin)
    proc=subprocess.Popen(['zstd','-dc',str(package)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    files={};seen=set();total=0
    try:
        with tarfile.open(fileobj=proc.stdout,mode='r|') as t:
            for row in t:
                p=PurePosixPath(row.name)
                require(row.name not in seen and not p.is_absolute() and '..' not in p.parts
                        and p.as_posix()==row.name,'Unsafe/duplicate package path');seen.add(row.name)
                require(row.isfile() or row.isdir(),'Package links/special entries forbidden')
                if row.isdir():continue
                require(0<=row.size<128*1024**2 and not row.mode&0o7000,'Package file bound/mode')
                total+=row.size;require(total<384*1024**2,'Expanded package bound')
                files[row.name]=t.extractfile(row).read()
        proc.stdout.close();err=proc.stderr.read();require(proc.wait()==0,'zstd package read failed')
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
        if proc.stdout is not None:proc.stdout.close()
        if proc.stderr is not None:proc.stderr.close()
    metadata={'.PKGINFO','.BUILDINFO','.MTREE'}
    require(metadata<=set(files) and '.INSTALL' not in files,'ALPM metadata missing or install script present')
    info={}
    for line in files['.PKGINFO'].decode().splitlines():
        if ' = ' in line:
            key,value=line.split(' = ',1);info.setdefault(key,[]).append(value)
    pkgbase=info.get('pkgbase',[''])[0]
    require(pkgbase in [PKGBASE,PKGBASE_72],'Unsupported package base')
    for key,value in [('pkgname',pkgbase),('pkgbase',pkgbase),('arch','x86_64')]:
        require(info.get(key)==[value],'Unexpected ALPM identity/architecture')
    require(len(info.get('pkgver',[]))==1,'Ambiguous package version')
    match=re.fullmatch(r'(6\.14\.0|7\.2\.0)\.r([0-9]+)-1',info['pkgver'][0]);require(match is not None,'Unsupported integrated package version')
    release=match[1]+'-mipad2-integrated-r'+match[2]
    require(identity(release)[0]==pkgbase,'Package base/kernel family mismatch')
    boot='var/lib/mipad2-kernel/'+release
    manifest_path=boot+'/manifest.json';require(manifest_path in files,'Original build manifest missing')
    m=json.loads(files[manifest_path]);require(m.get('kernelrelease')==release and m.get('all_module_signatures_cryptographically_verified') is True,'Original release/signature evidence missing')
    originals=m.get('files_sha256',{});prefix='usr/lib/modules/'+release
    additions={prefix+'/vmlinuz',prefix+'/pkgbase','etc/mkinitcpio.d/'+pkgbase+'.preset','usr/share/doc/'+pkgbase+'/module-signing.x509'}
    require(set(files)==set(originals)|{manifest_path}|metadata|additions,'Unexpected/missing package payload')
    for name,digest in originals.items():
        relative=name[len(prefix)+1:] if name.startswith(prefix+'/') else ''
        allowed=(name in [boot+'/'+n for n in ['vmlinuz','config','System.map']]
                 or (relative.startswith('kernel/') and relative.endswith('.ko.zst'))
                 or re.fullmatch(r'modules\.[a-z0-9_.]+',relative) is not None)
        require(allowed and sha(files[name])==digest,'Original kernel/module path or hash changed')
    require(files[prefix+'/vmlinuz']==files[boot+'/vmlinuz'] and files[prefix+'/pkgbase']==(pkgbase+'\n').encode(),'Kernel alias/package base mismatch')
    preset=files['etc/mkinitcpio.d/'+pkgbase+'.preset'].decode()
    require('ALL_kver="/usr/lib/modules/'+release+'/vmlinuz"' in preset
            and 'default_image="/boot/initramfs-'+pkgbase+'.img"' in preset,'Preset points at a different kernel')
    count=sum(n.endswith('.ko.zst') for n in files)
    require(type(m.get('modules')) is int and count==m['modules']>0,'Module count mismatch')
    return dict(state='integrated-kernel-package-preflight-pass',kernelrelease=release,pkgbase=pkgbase,
                package_sha256=pin,source_commit=m.get('source_commit'),original_files_verified=len(originals)+1,
                modules=count,install_script_absent=True,original_payload_hashes_preserved=True,
                new_cryptographic_signature_validation=False,image_build_or_install_performed=False)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path);p.add_argument('--sha256',required=True)
    a=p.parse_args();print(json.dumps(check(a.package,a.sha256),indent=2))

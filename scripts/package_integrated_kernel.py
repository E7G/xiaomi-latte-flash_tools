#!/usr/bin/env python3
"""Repackage a pinned, completed Linux6.14 or Linux7.2 bundle using real makepkg; no rebuild/install.

The public module certificate is separately pinned; every module CMS signature
is independently verified again. Kernel/module bytes are never stripped/changed.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile


PKGBASE='linux-latte-integrated'
PKGBASE_72='linux-latte-integrated-7-2'
MODERN_FLAVORS=('daily3','adc1','adc2','lpat9')
MODERN_FLAVOR_PATTERN='|'.join(MODERN_FLAVORS)
MODERN_VERSION_PATTERN=r'7\.2\.(?:0|[1-9][0-9]*)'
LEGACY_PATTERN=r'(?:6\.14\.0|7\.2\.0)-mipad2-integrated-r[0-9]+'
MODERN_PATTERN=MODERN_VERSION_PATTERN+'-mipad2-integrated-(?:'+MODERN_FLAVOR_PATTERN+')'
RELEASE_PATTERN=r'(?:'+LEGACY_PATTERN+'|'+MODERN_PATTERN+')'


def modern(release):
    return re.fullmatch(MODERN_PATTERN,release) is not None


def identity(release):
    require(re.fullmatch(RELEASE_PATTERN,release),'Only integrated6.14/7.2 supported')
    if modern(release):
        family,flavor=release.split('-mipad2-integrated-')
        # Each candidate flavor owns its package/presets, never replacing daily
        # or the existing stable6.14/legacy7.2 package.
        return PKGBASE_72+'-'+flavor,family+'.'+flavor
    family=release.split('-mipad2-integrated-r',1)[0]
    return (PKGBASE_72 if family=='7.2.0' else PKGBASE,
            family+'.r'+release.rsplit('r',1)[1])


def release_from_version(version):
    match=re.fullmatch(r'(6\.14\.0|7\.2\.0)\.r([0-9]+)',version)
    if match:return match[1]+'-mipad2-integrated-r'+match[2]
    match=re.fullmatch(r'('+MODERN_VERSION_PATTERN+r')\.('+MODERN_FLAVOR_PATTERN+')',version)
    require(match is not None,'Invalid package version')
    return match[1]+'-mipad2-integrated-'+match[2]


def boot_files(release):
    return ['vmlinuz','config','System.map']+(['Module.symvers','module-signing-public.x509'] if modern(release) else [])


def module_count(manifest):
    is_modern=modern(manifest['kernelrelease'])
    field='module_count' if is_modern else 'modules'
    require(('modules' not in manifest if is_modern else 'module_count' not in manifest),'Ambiguous module count fields')
    count=manifest.get(field)
    require(type(count) is int and 0<count<256,'Module set mismatch')
    if is_modern:
        require(manifest.get('signature_negative_control_passed') is True,'Missing original signature negative control')
        require(re.fullmatch('[0-9a-f]{64}',manifest.get('module_certificate_sha256','')),'Missing public certificate digest')
    return count


def bundle_name(name,directory):
    if directory and name in ['.','./']:return None
    if name.startswith('./'):name=name[2:]
    if directory and name.endswith('/'):name=name[:-1]
    p=PurePosixPath(name)
    require(name and name!='.' and not p.is_absolute() and '..' not in p.parts and p.as_posix()==name
            and re.fullmatch(r'[A-Za-z0-9_./+-]+',name),'Unsafe/duplicate bundle path')
    return name



def require(v,m):
    if not v:raise ValueError(m)


def sha(data):return hashlib.sha256(data).hexdigest()


def file_pin(path,pin):
    path=Path(path)
    require(re.fullmatch(r'[0-9a-f]{64}',pin or ''),'Explicit SHA256 required')
    require(path.is_file() and not path.is_symlink(),'Regular pinned input required')
    data=path.read_bytes();require(sha(data)==pin,'Pinned input hash mismatch');return data


def load_bundle(bundle,pin):
    file_pin(bundle,pin)
    files={};total=0;modern_layout=False
    proc=subprocess.Popen(['zstd','-dc',str(bundle)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=proc.stdout,mode='r|') as tar:
            seen=set()
            for row in tar:
                name=bundle_name(row.name,row.isdir())
                modern_layout|=row.name.startswith('./') or (row.isdir() and row.name.endswith('/'))
                if name is None:continue
                require(name not in seen and len(seen)<1024,'Unsafe/duplicate bundle path')
                seen.add(name)
                require(row.isfile() or row.isdir(),'Bundle links/special files forbidden')
                if row.isdir():continue
                require(0<=row.size<128*1024**2 and row.mode in [0o644,0o755],'Bundle file bound/mode')
                total+=row.size;require(total<256*1024**2,'Bundle expanded bound')
                files[name]=(tar.extractfile(row).read(),row.mode)
        proc.stdout.close();err=proc.stderr.read();require(proc.wait()==0,'zstd failed')
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
        if proc.stdout is not None:proc.stdout.close()
        if proc.stderr is not None:proc.stderr.close()
    manifests=[n for n in files if re.fullmatch(r'var/lib/mipad2-kernel/'+RELEASE_PATTERN+r'/manifest\.json',n)]
    require(len(manifests)==1,'One supported integrated manifest required')
    m=json.loads(files[manifests[0]][0]);release=m.get('kernelrelease','')
    identity(release)
    require(not modern_layout or modern(release),"Legacy bundle paths must remain canonical")
    require(re.fullmatch(r'[0-9a-f]{40}',m.get('source_commit','')),'Source commit missing')
    require(m.get('all_module_signatures_cryptographically_verified') is True,'Original signature evidence missing')
    expected=m.get('files_sha256',{})
    require(set(files)==set(expected)|set(manifests),'Unexpected/missing bundle payload')
    for name,digest in expected.items():
        prefix='usr/lib/modules/'+release+'/'
        relative=name[len(prefix):] if name.startswith(prefix) else ''
        allowed=(name in ['var/lib/mipad2-kernel/'+release+'/'+n for n in boot_files(release)]
                 or (relative.startswith('kernel/') and relative.endswith('.ko.zst'))
                 or re.fullmatch(r'modules\.[a-z0-9_.]+',relative) is not None)
        require(allowed and sha(files[name][0])==digest,'Bundle manifest path/hash mismatch')
    image=files['var/lib/mipad2-kernel/'+release+'/vmlinuz'][0]
    require(len(image)>0x210 and image[0x202:0x206]==b'HdrS','Not an x86 bzImage')
    offset=struct.unpack_from('<H',image,0x20e)[0]+0x200
    require(offset<len(image) and image[offset:].split(b'\0',1)[0].startswith((release+' ').encode()),'Kernel release banner mismatch')
    modules=[name for name in files if name.endswith('.ko.zst')]
    require(len(modules)==module_count(m),'Module set mismatch')
    return m,files


def verify_modules(manifest,files,cert,pin):
    cert_data=file_pin(cert,pin)
    if modern(manifest['kernelrelease']):
        require(sha(cert_data)==manifest['module_certificate_sha256'],'Pinned/embedded certificate mismatch')
        embedded='var/lib/mipad2-kernel/'+manifest['kernelrelease']+'/module-signing-public.x509'
        require(files[embedded][0]==cert_data,'Embedded public certificate differs')
    with tempfile.TemporaryDirectory(prefix='mipad2-package-cms-') as directory:
        temp=Path(directory);pem=temp/'cert.pem'
        subprocess.run(['openssl','x509','-inform','DER','-in',str(cert),'-out',str(pem)],check=True,capture_output=True)
        serial=subprocess.check_output(['openssl','x509','-in',str(pem),'-noout','-serial'],text=True).strip().split('=',1)[1].lower()
        declared_serial=manifest.get('signature_certificate_serial')
        # Initial 7.2 bundle omitted this redundant metadata field. An explicit
        # pinned certificate and actual detached CMS validation remain mandatory.
        require(serial==declared_serial or (declared_serial is None and
                (manifest['kernelrelease'].startswith('7.2.0-mipad2-integrated-r') or modern(manifest['kernelrelease']))),
                'Module signing certificate mismatch')
        checked=0
        for name,(data,_) in files.items():
            if not name.endswith('.ko.zst'):continue
            compressed=temp/'module.ko.zst';compressed.write_bytes(data)
            vermagic=subprocess.check_output(['modinfo','-F','vermagic',str(compressed)],text=True,timeout=30).split()[0]
            require(vermagic==manifest['kernelrelease'],'Module release mismatch')
            raw=subprocess.check_output(['zstd','-dc',str(compressed)],timeout=30)
            magic=b'~Module signature appended~\n';require(raw.endswith(magic),'Unsigned module')
            end=len(raw)-len(magic)-12;info=raw[end:end+12]
            require(len(info)==12 and info[2]==2 and not any(info[3:8]),'Unsupported module signature descriptor')
            length=struct.unpack('>I',info[8:12])[0];require(0<length<end,'Invalid module signature size')
            (temp/'signature.der').write_bytes(raw[end-length:end]);(temp/'unsigned.ko').write_bytes(raw[:end-length])
            command=['openssl','cms','-verify','-inform','DER','-in',str(temp/'signature.der'),
                     '-content',str(temp/'unsigned.ko'),'-certfile',str(pem),'-nointern',
                     '-noverify','-binary','-out','/dev/null']
            subprocess.run(command,check=True,capture_output=True,timeout=30)
            if checked==0:
                payload=raw[:end-length];require(payload,'Empty signed module')
                (temp/'unsigned.ko').write_bytes(bytes([payload[0]^1])+payload[1:])
                require(subprocess.run(command,capture_output=True,timeout=30).returncode!=0,
                        'Corrupted module unexpectedly verified')
                (temp/'unsigned.ko').write_bytes(payload)
            checked+=1
    return checked


def recipe(version,payload_sha):
    release=release_from_version(version)
    pkgbase,_=identity(release)
    family=release.split('-mipad2-integrated-',1)[0]
    require(re.fullmatch(r'[0-9a-f]{64}',payload_sha),'Payload digest required')
    return f'''# Binary repack of a completed verified build; NOT a new kernel compile.
pkgname={pkgbase}
pkgbase={pkgbase}
pkgver={version}
pkgrel=1
pkgdesc="Xiaomi Mi Pad 2 Linux{family} integrated kernel (verified binary repack)"
arch=(x86_64)
url="https://github.com/E7G/linux_latte"
license=(GPL-2.0-only)
depends=(coreutils kmod mkinitcpio)
options=(!strip !debug !lto)
source=(payload.tar)
sha256sums=({payload_sha})
package() {{
  cp -a "$srcdir/payload/." "$pkgdir/"
}}
'''


def build(bundle,bundle_sha256,cert,cert_sha256,output,epoch):
    output=Path(output)
    require(not output.is_symlink() and not output.exists(),'New output directory required')
    require(not Path(bundle).is_symlink() and not Path(cert).is_symlink(),'Symlinked pinned input')
    output=output.resolve();bundle=Path(bundle).resolve();cert=Path(cert).resolve()
    require(output!=bundle.parent and output not in bundle.parents and bundle.parent not in output.parents,'Output must be separate from bundle directory')
    require(type(epoch) is int and 0<epoch<2**40,'Explicit reproducible packaging epoch required')
    require(os.geteuid()==0,'Root needed only to run makepkg as existing nobody account')
    for name in ['makepkg','pacman','bsdtar','zstd','modinfo','openssl','runuser','fakeroot']:
        require(shutil.which(name) is not None,'Missing packaging tool: '+name)
    nobody=pwd.getpwnam('nobody');require(nobody.pw_uid!=0,'Unprivileged packaging account required')
    m,files=load_bundle(bundle,bundle_sha256);checked=verify_modules(m,files,cert,cert_sha256)
    release=m['kernelrelease'];pkgbase,version=identity(release);prefix='usr/lib/modules/'+release;boot='var/lib/mipad2-kernel/'+release
    payload=dict(files)
    payload[prefix+'/vmlinuz']=(files[boot+'/vmlinuz'][0],0o644)
    payload[prefix+'/pkgbase']=((pkgbase+'\n').encode(),0o644)
    payload['usr/share/doc/'+pkgbase+'/module-signing.x509']=(cert.read_bytes(),0o644)
    preset=f'''ALL_config="/etc/mkinitcpio.conf"
ALL_kver="/usr/lib/modules/{release}/vmlinuz"
PRESETS=('default' 'fallback')
default_image="/boot/initramfs-{pkgbase}.img"
fallback_image="/boot/initramfs-{pkgbase}-fallback.img"
fallback_options="-S autodetect"
'''
    payload['etc/mkinitcpio.d/'+pkgbase+'.preset']=(preset.encode(),0o644)
    output.mkdir(parents=True,mode=0o755)
    # A restrictive caller umask must not prevent the unprivileged packaging
    # account from traversing the newly created public output directory. Never
    # chmod an existing directory or any signing input; logs retain their umask.
    output.chmod(0o755)
    work=output/'makepkg';work.mkdir(mode=0o755)
    work.chmod(0o755)
    payload_tar=work/'payload.tar'
    with tarfile.open(payload_tar,'w',format=tarfile.PAX_FORMAT) as t:
        for name,(data,mode) in sorted(payload.items()):
            info=tarfile.TarInfo('payload/'+name);info.size=len(data);info.mode=mode;info.mtime=epoch;info.uid=info.gid=0;t.addfile(info,io.BytesIO(data))
    pkgbuild=recipe(version,sha(payload_tar.read_bytes()));(work/'PKGBUILD').write_text(pkgbuild)
    config='''CARCH=x86_64
CHOST=x86_64-pc-linux-gnu
BUILDENV=(!distcc !color !ccache !check !sign)
OPTIONS=(!strip docs !libtool !staticlibs emptydirs !zipman !purge !debug !lto)
INTEGRITY_CHECK=(sha256)
COMPRESSZST=(zstd -c -T2 -6 -)
PKGEXT=.pkg.tar.zst
SRCEXT=.src.tar.gz
PACKAGER="MiPad2 binary repack <mipad2@localhost>"
'''
    (work/'makepkg.conf').write_text(config)
    home=work/'home';home.mkdir()
    for p in [work,*work.rglob('*')]:os.chown(p,nobody.pw_uid,nobody.pw_gid)
    r=dict(schema=1,state='packaging',kernelrelease=release,source_commit=m['source_commit'],
           bundle_sha256=bundle_sha256,module_cert_sha256=cert_sha256,crypto_verified_modules=checked,signature_corruption_negative_control_passed=checked>0,
           recipe_sha256=sha(Path(__file__).read_bytes()),pkgbuild_sha256=sha(pkgbuild.encode()),
           package_base=pkgbase,package_version=version+'-1',packaging_epoch=epoch,
           kernel_recompiled=False,kernel_payload_changed=False,installed=False,boot_image_qualified=False)
    def save():(output/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
    save()
    try:
        env=dict(PATH=os.environ['PATH'],HOME=str(home),USER='nobody',LOGNAME='nobody',LC_ALL='C',LANG='C',SOURCE_DATE_EPOCH=str(epoch))
        with (output/'makepkg.log').open('xb') as log:
            q=subprocess.run(['runuser','-u','nobody','--','makepkg','--nodeps','--nocheck','--noconfirm','--config',str(work/'makepkg.conf'),'--log'],cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        require(q.returncode==0,'makepkg failed; retain output and inspect log')
        package=work/(pkgbase+'-'+version+'-1-x86_64.pkg.tar.zst');require(package.is_file(),'Package not created')
        listed=subprocess.check_output(['bsdtar','-tf',str(package)],text=True).splitlines()
        require(all(n in listed for n in ['.PKGINFO','.BUILDINFO','.MTREE']),'Missing real ALPM metadata')
        for name,(data,_) in payload.items():
            require(subprocess.check_output(['bsdtar','-xOf',str(package),name])==data,'Package changed payload: '+name)
        info=subprocess.check_output(['pacman','-Qip',str(package)],text=True,env=dict(os.environ,LC_ALL='C'))
        (output/'pacman-query.log').write_text(info)
        require(pkgbase in info and version+'-1' in info,'Native package query failed')
        require(file_pin(bundle,bundle_sha256) and sha(cert.read_bytes())==cert_sha256,'Original inputs changed')
        r.update(state='arch-package-built-native-query-pass',package=str(package),package_sha256=sha(package.read_bytes()),
                 package_bytes=package.stat().st_size,original_bundle_files_preserved=len(files),
                 payload_files_verified=len(payload),standard_alpm_metadata_generated_by_makepkg=True,
                 host_or_tablet_install_performed=False,local_package_pgp_signed=False)
        save();return r
    except BaseException as error:
        r.update(state='failed-retained',error_type=type(error).__name__);save();raise


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['bundle','cert','output']:p.add_argument('--'+key,required=True,type=Path)
    for key in ['bundle-sha256','cert-sha256']:p.add_argument('--'+key,required=True)
    p.add_argument('--epoch',type=int,required=True)
    print(json.dumps(build(**vars(p.parse_args())),indent=2))

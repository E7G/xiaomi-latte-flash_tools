#!/usr/bin/env python3
"""Bind a CI kernel artifact to explicit SHA256/source pins before image mutation.

This checks transport, ALPM identity and source/release provenance. It is not a
new module-CMS, PE-signature, image-boot or hardware qualification.
"""
import argparse,hashlib,json,re,subprocess,tarfile
from pathlib import Path,PurePosixPath
from package_integrated_kernel import require
from stage_kernel_support import PAYLOAD

BASES={'linux-latte-cachyos':r'6\.14\.0-mipad2-cachyos',
       'linux-latte-integrated':r'6\.14\.0-mipad2-integrated-r[0-9]+',
       'linux-latte-integrated-7-2':r'7\.2\.0-mipad2-integrated-r[0-9]+'}
FIELDS={'schema','filename','sha256','pkgbase','pkgver','kernelrelease','source_commit','package_format'}

def strict_json(data):
    def unique(pairs):
        out={}
        for k,v in pairs:
            require(k not in out,'Duplicate JSON field');out[k]=v
        return out
    return json.loads(data,object_pairs_hook=unique)

def digest(path):
    require(path.is_file() and not path.is_symlink(),'Regular artifact required')
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def inspect(package,pin,source_commit):
    package=Path(package)
    require(re.fullmatch(r'[a-f0-9]{64}',pin or ''),'Explicit SHA256 required')
    require(re.fullmatch(r'[a-f0-9]{40}',source_commit or ''),'Explicit full source commit required')
    before=package.stat()
    require(digest(package)==pin,'Artifact digest mismatch')
    files={};modes={};seen=set();total=0
    proc=subprocess.Popen(['zstd','-dc',str(package)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=proc.stdout,mode='r|') as archive:
            for entry in archive:
                p=PurePosixPath(entry.name);name=p.as_posix()
                require(not p.is_absolute() and '..' not in p.parts and name not in seen
                        and entry.name.rstrip('/')==name and re.fullmatch(r'[A-Za-z0-9_./+@ -]+',name),'Unsafe/duplicate artifact path')
                seen.add(name)
                require(entry.isdir() or entry.isfile(),'Artifact links/special files forbidden')
                if entry.isdir():continue
                require(0<=entry.size<128*1024**2 and not entry.mode&0o7000,'Artifact entry bound/mode')
                total+=entry.size;require(total<384*1024**2,'Artifact expanded bound')
                require(not name.endswith(('MOK.key','signing_key.pem','.p12')),'Private signing material forbidden')
                files[name]=archive.extractfile(entry).read();modes[name]=entry.mode&0o777
        proc.stdout.close();error=proc.stderr.read();require(proc.wait()==0,'Artifact decompression failed')
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
        proc.stdout.close();proc.stderr.close()
    after=package.stat();require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'Artifact changed while reading')
    require('.PKGINFO' in files and '.INSTALL' not in files,'ALPM metadata required; install scripts forbidden')
    info={}
    for line in files['.PKGINFO'].decode().splitlines():
        if ' = ' in line:
            k,v=line.split(' = ',1);info.setdefault(k,[]).append(v)
    for key in ['pkgname','pkgbase','pkgver','arch']:require(len(info.get(key,[]))==1,'Ambiguous ALPM identity')
    base=info['pkgbase'][0];version=info['pkgver'][0]
    require(base in BASES and info['pkgname']==[base] and info['arch']==['x86_64'],'Unsupported ALPM identity')
    require(package.name==base+'-'+version+'-x86_64.pkg.tar.zst','Artifact filename/ALPM identity mismatch')
    kernels=[n for n in files if re.fullmatch(r'usr/lib/modules/[^/]+/vmlinuz',n)]
    require(len(kernels)==1,'Exactly one packaged kernel required')
    release=kernels[0].split('/')[3];require(re.fullmatch(BASES[base],release),'Kernel family/package base mismatch')
    prefix='usr/lib/modules/'+release
    require(files.get(prefix+'/pkgbase')==(base+'\n').encode(),'Module package base mismatch')
    image=files[kernels[0]];require(len(image)>0x210 and image[0x202:0x206]==b'HdrS','Not an x86 bzImage')
    import struct
    offset=struct.unpack_from('<H',image,0x20e)[0]+0x200
    require(offset<len(image) and image[offset:].split(b'\0',1)[0].startswith((release+' ').encode()),'Kernel release banner mismatch')
    manifest_path='var/lib/mipad2-kernel/'+release+'/manifest.json'
    if manifest_path in files:
        from preflight_integrated_kernel_package import check
        proof=check(package,pin);require(proof['source_commit']==source_commit,'Source pin mismatch')
        kind='verified-binary-repack'
    else:
        doc='usr/share/doc/'+base+'/'
        require(files.get(doc+'source-commit')==(source_commit+'\n').encode(),'Source pin mismatch')
        require(files.get(doc+'kernel-release')==(release+'\n').encode(),'Source release provenance mismatch')
        require(prefix+'/config' in files,'Source-build resolved config missing')
        support='usr/share/doc/linux-latte-cachyos/support-payload.json'
        require(support in files,'Pinned source support manifest missing')
        plan=strict_json(files[support]);require(isinstance(plan,dict) and type(plan.get('schema')) is int and plan['schema']==1 and isinstance(plan.get('files'),dict),'Invalid support manifest')
        require(set(plan['files'])=={destination for _,destination,_ in PAYLOAD},'Incomplete source support payload')
        for _,name,mode in PAYLOAD:
            row=plan['files'][name]
            require(name in files and isinstance(row,dict) and hashlib.sha256(files[name]).hexdigest()==row.get('sha256'),'Source support payload mismatch')
            require(modes[name]==mode and row.get('mode')==oct(mode),'Source support payload mode mismatch')
        require(version.endswith('.g'+source_commit[:12]+'-1'),'Source package version/commit mismatch')
        kind='source-ci'
    return dict(schema=1,filename=package.name,sha256=pin,pkgbase=base,pkgver=version,kernelrelease=release,source_commit=source_commit,package_format=kind)

def verify(manifest,package,expected_source_commit,expected_sha256):
    manifest=Path(manifest);require(manifest.is_file() and not manifest.is_symlink(),'Regular artifact manifest required')
    record=strict_json(manifest.read_bytes())
    require(isinstance(record,dict) and set(record)==FIELDS and type(record.get('schema')) is int and record['schema']==1,'Unsupported artifact manifest')
    require(record['source_commit']==expected_source_commit and record['sha256']==expected_sha256,'Trusted job pin/manifest mismatch')
    filename=record['filename'];require(isinstance(filename,str) and PurePosixPath(filename).name==filename and '/' not in filename and '\\' not in filename,'Unsafe manifest filename')
    package=Path(package) if package else manifest.parent/filename
    require(package.name==filename,'Manifest filename mismatch')
    require(inspect(package,expected_sha256,expected_source_commit)==record,'Artifact metadata mismatch')
    return dict(record,package=str(package.resolve()),state='kernel-artifact-handoff-verified',new_cryptographic_validation=False,image_or_device_touched=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);commands=p.add_subparsers(dest='command',required=True)
    c=commands.add_parser('create');c.add_argument('--package',type=Path,required=True);c.add_argument('--source-commit',required=True);c.add_argument('--output',type=Path,required=True)
    c=commands.add_parser('verify');c.add_argument('--manifest',type=Path,required=True);c.add_argument('--package',type=Path);c.add_argument('--expected-source-commit',required=True);c.add_argument('--expected-sha256',required=True);c.add_argument('--require-format',choices=['source-ci','verified-binary-repack']);c.add_argument('--github-output',type=Path)
    a=p.parse_args()
    if a.command=='create':
        require(not a.output.exists() and not a.output.is_symlink(),'New artifact manifest output required')
        result=inspect(a.package,digest(a.package),a.source_commit);a.output.write_text(json.dumps(result,indent=2)+'\n')
    else:
        result=verify(a.manifest,a.package,a.expected_source_commit,a.expected_sha256)
        require(not a.require_format or result['package_format']==a.require_format,'Artifact format not suitable for this consumer')
        if a.github_output:
            with a.github_output.open('a') as output:
                output.write('sha256='+result['sha256']+'\nsource_commit='+result['source_commit']+'\n')
    print(json.dumps(result,indent=2))

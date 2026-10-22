"""Actual artifact resolver and shell-prefix tests; no NBD/image/device access.

Small source-CI archives are synthetic. A separate delivery receipt exercises
the completed real 7.2 build's packaging tail and independent binary package.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import resolve_kernel_artifact as resolver
from stage_kernel_support import PAYLOAD, MANIFEST


@unittest.skipUnless(shutil.which('zstd'), 'zstd required')
class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mipad2-artifact-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.commit = 'a' * 40
        self.base = 'linux-latte-integrated-7-2'
        self.release = '7.2.0-mipad2-integrated-r1'
        self.version = self.release.replace('-', '_') + '.r20261023000000.g' + self.commit[:12] + '-1'
        image = bytearray(1024)
        image[0x202:0x206] = b'HdrS'
        struct.pack_into('<H', image, 0x20e, 0x80)
        banner = (self.release + ' (fixture)\0').encode()
        image[0x280:0x280+len(banner)] = banner
        prefix = 'usr/lib/modules/' + self.release
        doc = 'usr/share/doc/' + self.base
        self.files = {
            '.PKGINFO': ('pkgname = '+self.base+'\npkgbase = '+self.base+'\npkgver = '+self.version+'\narch = x86_64\n').encode(),
            prefix+'/vmlinuz': bytes(image), prefix+'/pkgbase': (self.base+'\n').encode(),
            prefix+'/config': b'CONFIG_LOCALVERSION="-mipad2-integrated"\n',
            doc+'/source-commit': (self.commit+'\n').encode(),
            doc+'/kernel-release': (self.release+'\n').encode(),
        }
        for name, destination, _ in PAYLOAD:
            self.files[destination] = ('fixture '+name).encode()
        self.files[MANIFEST] = json.dumps(dict(schema=1, files={
            dest: dict(sha256=hashlib.sha256(self.files[dest]).hexdigest(), mode=oct(mode))
            for _, dest, mode in PAYLOAD})).encode()
        self.package = self.root / (self.base+'-'+self.version+'-x86_64.pkg.tar.zst')
        self.manifest = self.root/'kernel-artifact.json'

    def pack(self, extra=()):
        archive = io.BytesIO()
        modes = {dest: mode for _, dest, mode in PAYLOAD}
        with tarfile.open(fileobj=archive, mode='w') as tar:
            for name, data in [*self.files.items(), *extra]:
                entry = tarfile.TarInfo(name); entry.size = len(data); entry.mode = modes.get(name, 0o644)
                tar.addfile(entry, io.BytesIO(data))
        self.package.write_bytes(subprocess.check_output(['zstd','-q','-c'], input=archive.getvalue()))
        self.pin = hashlib.sha256(self.package.read_bytes()).hexdigest()

    def record(self):
        self.pack()
        record = resolver.inspect(self.package, self.pin, self.commit)
        self.manifest.write_text(json.dumps(record))
        return record

    def test_valid_complete_source_ci(self):
        self.record()
        result = resolver.verify(self.manifest, None, self.commit, self.pin)
        self.assertEqual(result['package_format'], 'source-ci')
        self.assertEqual(result['kernelrelease'], self.release)
        self.assertFalse(result['image_or_device_touched'])

    def test_wrong_digest(self):
        self.pack()
        with self.assertRaisesRegex(ValueError, 'digest'):
            resolver.inspect(self.package, '0'*64, self.commit)

    def test_wrong_source(self):
        self.pack()
        with self.assertRaisesRegex(ValueError, 'Source pin'):
            resolver.inspect(self.package, self.pin, 'b'*40)

    def test_missing_full_source_pin(self):
        self.pack()
        with self.assertRaisesRegex(ValueError, 'full source'):
            resolver.inspect(self.package, self.pin, self.commit[:12])

    def test_package_filename_is_not_authority(self):
        self.pack(); renamed=self.package.with_name('wrong.pkg.tar.zst'); self.package.rename(renamed)
        with self.assertRaisesRegex(ValueError, 'filename'):
            resolver.inspect(renamed, self.pin, self.commit)

    def test_source_commit_version_binding(self):
        self.files['.PKGINFO']=self.files['.PKGINFO'].replace(b'.gaaaaaaaaaaaa', b'.gbbbbbbbbbbbb')
        self.package=self.package.with_name(self.package.name.replace('.gaaaaaaaaaaaa','.gbbbbbbbbbbbb'))
        self.pack()
        with self.assertRaisesRegex(ValueError, 'version/commit'):
            resolver.inspect(self.package, self.pin, self.commit)

    def test_wrong_family(self):
        key='usr/lib/modules/'+self.release+'/pkgbase'; self.files[key]=b'linux-latte-integrated\n'
        self.pack()
        with self.assertRaisesRegex(ValueError, 'package base'):
            resolver.inspect(self.package, self.pin, self.commit)

    def test_corrupt_bzimage(self):
        self.files['usr/lib/modules/'+self.release+'/vmlinuz']=b'not a kernel'
        self.pack()
        with self.assertRaisesRegex(ValueError, 'bzImage'):
            resolver.inspect(self.package, self.pin, self.commit)

    def test_missing_source_config(self):
        del self.files['usr/lib/modules/'+self.release+'/config'];self.pack()
        with self.assertRaisesRegex(ValueError, 'config'):
            resolver.inspect(self.package, self.pin, self.commit)

    def test_mutated_support_bytes(self):
        self.files[PAYLOAD[-1][1]]=b'changed';self.pack()
        with self.assertRaisesRegex(ValueError, 'support payload mismatch'):
            resolver.inspect(self.package, self.pin, self.commit)

    def test_empty_support_manifest(self):
        self.files[MANIFEST]=b'{"schema":1,"files":{}}';self.pack()
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            resolver.inspect(self.package, self.pin, self.commit)

    def test_install_script_rejected(self):
        self.files['.INSTALL']=b'echo unexpected';self.pack()
        with self.assertRaisesRegex(ValueError, 'install scripts'):
            resolver.inspect(self.package, self.pin, self.commit)

    def test_duplicate_archive_entry(self):
        self.pack([('.PKGINFO', self.files['.PKGINFO'])])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            resolver.inspect(self.package, self.pin, self.commit)

    def test_traversal_entry(self):
        self.pack([('../outside', b'x')])
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            resolver.inspect(self.package, self.pin, self.commit)

    def test_private_key_entry(self):
        self.pack([('usr/share/MOK.key', b'fixture')])
        with self.assertRaisesRegex(ValueError, 'Private'):
            resolver.inspect(self.package, self.pin, self.commit)

    def test_duplicate_manifest_json(self):
        self.record();self.manifest.write_text('{"schema":1,"schema":1}')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'):
            resolver.verify(self.manifest,None,self.commit,self.pin)

    def test_manifest_wrong_job_pin(self):
        self.record()
        with self.assertRaisesRegex(ValueError, 'job pin'):
            resolver.verify(self.manifest,None,self.commit,'0'*64)

    def test_manifest_altered_identity(self):
        row=self.record();row['pkgbase']='linux-latte-integrated';self.manifest.write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError, 'metadata mismatch'):
            resolver.verify(self.manifest,None,self.commit,self.pin)

    def test_manifest_unsafe_filename(self):
        row=self.record();row['filename']='../'+row['filename'];self.manifest.write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError, 'Unsafe manifest'):
            resolver.verify(self.manifest,None,self.commit,self.pin)

    def test_symlink_package(self):
        self.record();target=self.root/'target';self.package.rename(target);self.package.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'Regular artifact'):
            resolver.verify(self.manifest,None,self.commit,self.pin)

    def test_symlink_manifest(self):
        self.record();target=self.root/'target';self.manifest.rename(target);self.manifest.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'Regular artifact manifest'):
            resolver.verify(self.manifest,None,self.commit,self.pin)

    def test_support_manifest_mode_mismatch(self):
        row=json.loads(self.files[MANIFEST]);row['files'][PAYLOAD[0][1]]['mode']='0o755'
        self.files[MANIFEST]=json.dumps(row).encode();self.pack()
        with self.assertRaisesRegex(ValueError, 'mode mismatch'):
            resolver.inspect(self.package,self.pin,self.commit)

    def test_unsupported_future_release(self):
        prefix='usr/lib/modules/'+self.release
        for name in list(self.files):
            if name.startswith(prefix):
                self.files[name.replace(self.release,'7.3.0-mipad2-integrated-r1')]=self.files.pop(name)
        self.pack()
        with self.assertRaisesRegex(ValueError, 'family'):
            resolver.inspect(self.package,self.pin,self.commit)

    def test_workflow_pins_both_consumers_before_nbd(self):
        # Inspect the actual YAML, not a hand-rewritten workflow fixture.
        import yaml
        workflow=yaml.safe_load((REPO/'.github/workflows/build-dnx.yml').read_text())
        jobs=workflow['jobs'];steps=jobs['dnx']['steps']
        self.assertEqual(jobs['dnx']['needs'],'kernel')
        self.assertEqual(jobs['kernel']['outputs']['sha256'],'${{ steps.kernel-artifact.outputs.sha256 }}')
        guard=next(i for i,x in enumerate(steps) if x.get('name')=='Verify downloaded kernel before loading NBD')
        nbd=next(i for i,x in enumerate(steps) if x.get('name')=='Prepare NBD devices')
        build=next(x for x in steps if x.get('name')=='Build rootfs and one-click package')
        self.assertLess(guard,nbd)
        for step in [steps[guard],build]:
            self.assertEqual(step['env']['EXPECTED_KERNEL_SHA256'],'${{ needs.kernel.outputs.sha256 }}')
            self.assertEqual(step['env']['EXPECTED_KERNEL_SOURCE_COMMIT'],'${{ needs.kernel.outputs.source_commit }}')
        verify=next(x for x in jobs['kernel']['steps'] if x.get('id')=='kernel-artifact')
        self.assertNotIn('if',verify)  # cached archives are revalidated too
        upload=next(x for x in jobs['kernel']['steps'] if x.get('name')=='Upload kernel package for DNX job')
        self.assertIn('kernel-output/kernel-artifact.json',upload['with']['path'])

    def prepare_shell(self):
        self.record();scripts=self.root/'scripts';scripts.mkdir();out=self.root/'kernel-output';out.mkdir()
        for name in ['resolve_kernel_artifact.py','package_integrated_kernel.py','preflight_integrated_kernel_package.py','stage_kernel_support.py','build_dnx_package.sh']:
            shutil.copyfile(REPO/'scripts'/name,scripts/name)
        shutil.copyfile(self.package,out/self.package.name);shutil.copyfile(self.manifest,out/self.manifest.name)
        prefix=(REPO/'build_rootfs.sh').read_text().split('if [[ ! -d /sys/module/nbd ]]; then',1)[0]
        (self.root/'build_rootfs.sh').write_text(prefix+'\nprintf validated > rootfs-validated\nexit 91\n')
        env={k:v for k,v in os.environ.items() if not k.startswith(('KERNEL_','EXPECTED_KERNEL_','CAMERA_CANDIDATE_'))}
        env.update(EXPECTED_KERNEL_SOURCE_COMMIT=self.commit,EXPECTED_KERNEL_SHA256=self.pin,PYTHONDONTWRITEBYTECODE='1')
        return env

    def dnx(self,env):
        return subprocess.run(['bash','scripts/build_dnx_package.sh'],cwd=self.root,env=env,capture_output=True,text=True,timeout=20)

    def test_actual_dnx_and_rootfs_prefix_reach_validated_boundary(self):
        result=self.dnx(self.prepare_shell())
        self.assertEqual(result.returncode,91,result.stderr)
        self.assertTrue((self.root/'rootfs-validated').exists())
        self.assertEqual((self.root/'device_files'/self.package.name).read_bytes(),self.package.read_bytes())

    def test_dnx_fails_before_copy_without_trusted_pin(self):
        env=self.prepare_shell();del env['EXPECTED_KERNEL_SHA256'];result=self.dnx(env)
        self.assertNotEqual(result.returncode,91)
        self.assertFalse((self.root/'device_files').exists())
        self.assertFalse((self.root/'rootfs-validated').exists())

    def test_dnx_does_not_guess_first_archive(self):
        env=self.prepare_shell();(self.root/'kernel-output/linux-latte-cachyos-unrelated.pkg.tar.zst').write_bytes(b'decoy')
        result=self.dnx(env);self.assertEqual(result.returncode,91,result.stderr)

    def test_dnx_rejects_tamper_before_copy(self):
        env=self.prepare_shell();(self.root/'kernel-output'/self.package.name).write_bytes(b'changed')
        result=self.dnx(env);self.assertNotEqual(result.returncode,91)
        self.assertFalse((self.root/'device_files').exists())

    def test_rootfs_rejects_changed_copy_before_nbd(self):
        env=self.prepare_shell();env.update(KERNEL_PACKAGE=str(self.package),KERNEL_ARTIFACT_MANIFEST=str(self.manifest))
        self.package.write_bytes(b'changed')
        result=subprocess.run(['bash','build_rootfs.sh'],cwd=self.root,env=env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,91);self.assertFalse((self.root/'rootfs-validated').exists())

    def test_rootfs_rejects_conflicting_base_before_nbd(self):
        env=self.prepare_shell();env.update(KERNEL_PACKAGE=str(self.package),KERNEL_ARTIFACT_MANIFEST=str(self.manifest),KERNEL_PKGBASE='linux-latte-integrated')
        result=subprocess.run(['bash','build_rootfs.sh'],cwd=self.root,env=env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,91);self.assertFalse((self.root/'rootfs-validated').exists())


if __name__ == '__main__':
    unittest.main()

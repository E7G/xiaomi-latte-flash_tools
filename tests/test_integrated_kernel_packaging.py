import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'scripts'))
import package_integrated_kernel as packager
import preflight_integrated_kernel_package as preflight


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.archive=self.root/'bundle.tar.zst'
        self.release='6.14.0-mipad2-integrated-r26';boot='var/lib/mipad2-kernel/'+self.release
        image=bytearray(2048);image[0x202:0x206]=b'HdrS';struct.pack_into('<H',image,0x20e,0x100)
        banner=(self.release+' fixture\0').encode();image[0x300:0x300+len(banner)]=banner
        self.files={boot+'/vmlinuz':bytes(image),boot+'/config':b'config',boot+'/System.map':b'map',
                    'usr/lib/modules/'+self.release+'/kernel/test.ko.zst':b'module-fixture'}
        self.manifest=dict(kernelrelease=self.release,source_commit='a'*40,modules=1,
                           all_module_signatures_cryptographically_verified=True)
        self.boot=boot;self.write()

    def write(self, extra=None):
        self.manifest['files_sha256']={k:hashlib.sha256(v).hexdigest() for k,v in self.files.items()}
        raw=io.BytesIO()
        with tarfile.open(fileobj=raw,mode='w') as t:
            rows=list(self.files.items())+[(self.boot+'/manifest.json',json.dumps(self.manifest).encode())]
            if extra:rows.extend(extra)
            for name,data in rows:
                info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;t.addfile(info,io.BytesIO(data))
        q=subprocess.run(['zstd','-q','-c'],input=raw.getvalue(),capture_output=True,check=True)
        self.archive.write_bytes(q.stdout);self.pin=packager.sha(q.stdout)

    def test_actual_reader_checks_fixture_bytes_not_signatures(self):
        m,files=packager.load_bundle(self.archive,self.pin)
        self.assertEqual(m['kernelrelease'],self.release)
        self.assertEqual(len(files),5)
        # This intentionally unsigned fixture never passes verify_modules/build.

    def test_bad_external_pin(self):
        self.assertRaises(ValueError,packager.load_bundle,self.archive,'0'*64)

    def test_traversal_even_with_matching_archive_hash(self):
        self.write([('../escape',b'no')]);self.assertRaises(ValueError,packager.load_bundle,self.archive,self.pin)

    def test_duplicate_archive_entry(self):
        self.write([(next(iter(self.files)),b'duplicate')]);self.assertRaises(ValueError,packager.load_bundle,self.archive,self.pin)

    def test_private_key_or_extra_file_cannot_ship(self):
        self.files['var/lib/mipad2-kernel/'+self.release+'/MOK.key']=b'forbidden'
        self.write();self.assertRaises(ValueError,packager.load_bundle,self.archive,self.pin)

    def test_wrong_image_release(self):
        data=bytearray(self.files[self.boot+'/vmlinuz']);data[0x300:0x303]=b'bad'
        self.files[self.boot+'/vmlinuz']=bytes(data);self.write()
        self.assertRaises(ValueError,packager.load_bundle,self.archive,self.pin)

    def test_original_signature_claim_required_but_not_sufficient(self):
        self.manifest['all_module_signatures_cryptographically_verified']=False;self.write()
        self.assertRaises(ValueError,packager.load_bundle,self.archive,self.pin)

    def test_618_recipe_not_supported(self):
        self.assertRaises(ValueError,packager.recipe,'6.18.0.r26','a'*64)

    def test_no_stripping_signed_payload(self):
        recipe=packager.recipe('6.14.0.r26','a'*64)
        self.assertIn('options=(!strip !debug !lto)',recipe)
        self.assertNotIn('build()',recipe)
        self.assertNotIn('.INSTALL',recipe)

    def test_existing_output_not_overwritten(self):
        out=self.root/'out';out.mkdir();(out/'keep').write_text('keep')
        self.assertRaises(ValueError,packager.build,self.archive,self.pin,self.root/'cert','b'*64,out,1)
        self.assertEqual((out/'keep').read_text(),'keep')


class Bundle72Tests(BundleTests):
    def setUp(self):
        super().setUp()
        old=self.release
        self.release='7.2.0-mipad2-integrated-r1'
        self.boot='var/lib/mipad2-kernel/'+self.release
        self.files={k.replace(old,self.release):v.replace(old.encode(),self.release.encode()) for k,v in self.files.items()}
        self.manifest['kernelrelease']=self.release
        self.write()

    def test_separate_72_identity_and_recipe(self):
        self.assertEqual(packager.identity(self.release),('linux-latte-integrated-7-2','7.2.0.r1'))
        recipe=packager.recipe('7.2.0.r1','a'*64)
        self.assertIn('pkgbase=linux-latte-integrated-7-2',recipe)
        self.assertIn('pkgname=linux-latte-integrated-7-2',recipe)
        self.assertIn('Linux7.2.0',recipe)
        for bad in ['7.2.12-mipad2-integrated-r1','7.3.0-mipad2-integrated-r1','7.2.0-mipad2-integrated-r1/../r2']:
            self.assertRaises(ValueError,packager.identity,bad)


class KernelInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.bin=self.root/'bin';self.bin.mkdir();(self.root/'boot/EFI').mkdir(parents=True)
        self.source=(REPO/'device_files/mipad2-kernel-install').read_text()
        self.script=self.root/'installer'
        self.script.write_text(self.source.replace('/usr/local/sbin/mipad2-kernel-preflight',str(self.bin/'preflight'))
                               .replace('/etc/mipad2-secureboot/MOK.key',str(self.root/'key'))
                               .replace('/boot/',str(self.root/'boot')+'/')
                               .replace('/usr/lib/modules/',str(self.root/'usr/lib/modules')+'/')
                               .replace('/usr/bin/sbsign',str(self.bin/'sign'))
                               .replace('/usr/bin/sbverify',str(self.bin/'verify')))
        self.stub('preflight','exit "${PREFLIGHT_CODE:-0}"')
        self.stub('pacman','''case "$1" in
  -Ql) cat "$TEST_ROOT/$2.owned" ;;
  -Qq) test -f "$TEST_ROOT/$2.owned" && echo "$2" ;;
  -Q) echo "$2 6.14.0.r26-1" ;;
  *) exit 1 ;;
esac''')
        self.stub('sign','''if [ "${SIGN_FAIL:-0}" = 1 ]; then exit 1; fi
while [ "$1" != --output ]; do shift; done
cp "$3" "$2"''')
        self.stub('verify','test -s "$3"')
        self.env=dict(os.environ,TEST_ROOT=str(self.root),PATH=str(self.bin)+':'+os.environ['PATH'])

    def stub(self,name,body):
        p=self.bin/name;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o755)

    def package(self,base,release='6.14.0-mipad2-integrated-r26',count=1):
        lines=[]
        for i in range(count):
            directory=self.root/'usr/lib/modules'/(release+('-extra' if i else ''));directory.mkdir(parents=True,exist_ok=True)
            image=directory/'vmlinuz';image.write_text('kernel '+base)
            lines.append(base+' '+str(image))
        (self.root/(base+'.owned')).write_text('\n'.join(lines)+'\n')

    def run_installer(self,args=(),stdin='',**env):
        return subprocess.run(['bash',str(self.script),*args],input=stdin,capture_output=True,text=True,env=self.env|env,timeout=15)

    def test_integrated_explicit_base(self):
        self.package('linux-latte-integrated');q=self.run_installer(['linux-latte-integrated'])
        self.assertEqual(q.returncode,0,q.stderr)
        self.assertEqual((self.root/'boot/vmlinuz-linux-latte-integrated').read_text(),'kernel linux-latte-integrated')

    def test_legacy_base_still_supported(self):
        self.package('linux-latte-cachyos');q=self.run_installer(['linux-latte-cachyos'])
        self.assertEqual(q.returncode,0,q.stderr)

    def test_hook_stdin_multiple_packages(self):
        for base in ['linux-latte-cachyos','linux-latte-integrated']:self.package(base)
        q=self.run_installer(stdin='linux-latte-cachyos\nlinux-latte-integrated\nlinux-latte-integrated\n')
        self.assertEqual(q.returncode,0,q.stderr)
        self.assertTrue((self.root/'boot/vmlinuz-linux-latte-cachyos').exists())
        self.assertTrue((self.root/'boot/vmlinuz-linux-latte-integrated').exists())

    def test_ambiguous_manual_autodetect_refuses(self):
        for base in ['linux-latte-cachyos','linux-latte-integrated']:self.package(base)
        q=self.run_installer();self.assertNotEqual(q.returncode,0)
        self.assertIn('Specify exactly',q.stderr)

    def test_single_manual_autodetect(self):
        self.package('linux-latte-integrated');q=self.run_installer();self.assertEqual(q.returncode,0,q.stderr)

    def test_unsupported_base_refuses(self):
        q=self.run_installer(['../../escape']);self.assertNotEqual(q.returncode,0)
        self.assertFalse((self.root/'escape').exists())

    def test_integrated_618_rejected(self):
        self.package('linux-latte-integrated','6.18.0-mipad2-integrated-r26')
        q=self.run_installer(['linux-latte-integrated']);self.assertNotEqual(q.returncode,0)
        self.assertFalse((self.root/'boot/vmlinuz-linux-latte-integrated').exists())

    def test_two_owned_kernel_images_refuse(self):
        self.package('linux-latte-integrated',count=2)
        self.assertNotEqual(self.run_installer(['linux-latte-integrated']).returncode,0)

    def test_preflight_failure_preserves_boot_image(self):
        self.package('linux-latte-integrated');image=self.root/'boot/vmlinuz-linux-latte-integrated';image.write_text('old')
        q=self.run_installer(['linux-latte-integrated'],PREFLIGHT_CODE='1');self.assertNotEqual(q.returncode,0)
        self.assertEqual(image.read_text(),'old')

    def test_signer_failure_preserves_boot_image(self):
        self.package('linux-latte-integrated');image=self.root/'boot/vmlinuz-linux-latte-integrated';image.write_text('old')
        (self.root/'key').write_text('fixture');(self.root/'boot/EFI/MOK.crt').write_text('fixture')
        q=self.run_installer(['linux-latte-integrated'],SIGN_FAIL='1');self.assertNotEqual(q.returncode,0)
        self.assertEqual(image.read_text(),'old');self.assertFalse(image.with_suffix('.new').exists())

    def test_signer_and_verifier_path_with_fixture_keys(self):
        self.package('linux-latte-integrated')
        (self.root/'key').write_text('fixture');(self.root/'boot/EFI/MOK.crt').write_text('fixture')
        q=self.run_installer(['linux-latte-integrated']);self.assertEqual(q.returncode,0,q.stderr)
        self.assertEqual((self.root/'boot/vmlinuz-linux-latte-integrated').read_text(),'kernel linux-latte-integrated')

    def test_hook_targets_and_bash_syntax(self):
        for name in ['kernel.hook','kernel-preflight.hook']:
            text=(REPO/'device_files'/name).read_text();self.assertIn('Target = linux-latte-integrated',text)
        self.assertIn('NeedsTargets',(REPO/'device_files/kernel.hook').read_text())
        self.assertEqual(subprocess.run(['bash','-n',str(REPO/'device_files/mipad2-kernel-install')]).returncode,0)


class Kernel72InstallTests(KernelInstallTests):
    def test_candidate_installs_without_replacing_stable_image(self):
        self.package('linux-latte-integrated')
        self.package('linux-latte-integrated-7-2','7.2.0-mipad2-integrated-r1')
        old=self.root/'boot/vmlinuz-linux-latte-integrated';old.write_text('stable sentinel')
        q=self.run_installer(['linux-latte-integrated-7-2'])
        self.assertEqual(q.returncode,0,q.stderr)
        self.assertEqual(old.read_text(),'stable sentinel')
        self.assertEqual((self.root/'boot/vmlinuz-linux-latte-integrated-7-2').read_text(),'kernel linux-latte-integrated-7-2')

    def test_candidate_wrong_family_rejected_before_boot_write(self):
        self.package('linux-latte-integrated-7-2','6.14.0-mipad2-integrated-r27')
        q=self.run_installer(['linux-latte-integrated-7-2'])
        self.assertNotEqual(q.returncode,0)
        self.assertFalse((self.root/'boot/vmlinuz-linux-latte-integrated-7-2').exists())

    def test_72_cannot_replace_614_package_identity(self):
        self.package('linux-latte-integrated','7.2.0-mipad2-integrated-r1')
        q=self.run_installer(['linux-latte-integrated'])
        self.assertNotEqual(q.returncode,0)
        self.assertFalse((self.root/'boot/vmlinuz-linux-latte-integrated').exists())

    def test_new_hook_targets(self):
        for name in ['kernel.hook','kernel-preflight.hook']:
            self.assertIn('Target = linux-latte-integrated-7-2',(REPO/'device_files'/name).read_text())


class RootfsKernelBaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        text=(REPO/'build_rootfs.sh').read_text();start=text.index('\tmapfile -t installed_releases')
        end=text.index('\n\tdeclare -n desktop',start);self.block=text[start:end]
        (self.root/'boot').mkdir();(self.root/'usr/lib/modules').mkdir(parents=True)

    def run_block(self,release='6.14.0-mipad2-integrated-r26',metadata='linux-latte-integrated',explicit=''):
        directory=self.root/'usr/lib/modules'/release;directory.mkdir();(directory/'vmlinuz').write_text('fixture')
        if metadata is not None:(directory/'pkgbase').write_text(metadata+'\n')
        script='set -e\nmount_dir='+str(self.root)+'\nKERNEL_PKGBASE='+explicit+'\n'+self.block+'\nprintf "BASE=%s\\n" "$KERNEL_PKGBASE"\n'
        return subprocess.run(['bash','-c',script],capture_output=True,text=True)

    def test_72_base_from_package_metadata(self):
        q=self.run_block(release='7.2.0-mipad2-integrated-r1',metadata='linux-latte-integrated-7-2')
        self.assertEqual(q.returncode,0,q.stderr)
        self.assertIn('BASE=linux-latte-integrated-7-2',q.stdout)
        self.assertTrue((self.root/'boot/vmlinuz-linux-latte-integrated-7-2').exists())

    def test_72_base_rejects_614_release(self):
        q=self.run_block(metadata='linux-latte-integrated-7-2')
        self.assertNotEqual(q.returncode,0)
        self.assertEqual(list((self.root/'boot').iterdir()),[])

    def test_integrated_base_derived_from_installed_package(self):
        q=self.run_block();self.assertEqual(q.returncode,0,q.stderr)
        self.assertIn('BASE=linux-latte-integrated',q.stdout)
        self.assertEqual((self.root/'boot/vmlinuz-linux-latte-integrated').read_text(),'fixture')

    def test_legacy_missing_metadata_retains_legacy_fallback(self):
        q=self.run_block(metadata=None);self.assertEqual(q.returncode,0,q.stderr)
        self.assertIn('BASE=linux-latte-cachyos',q.stdout)

    def test_explicit_base_mismatch_rejected(self):
        q=self.run_block(explicit='linux-latte-cachyos');self.assertNotEqual(q.returncode,0)
        self.assertEqual(list((self.root/'boot').iterdir()),[])

    def test_integrated_wrong_kernel_line_rejected(self):
        q=self.run_block(release='6.18.0-mipad2-integrated-r26');self.assertNotEqual(q.returncode,0)

    def test_two_kernel_directories_rejected(self):
        (self.root/'usr/lib/modules/other').mkdir()
        q=self.run_block();self.assertNotEqual(q.returncode,0)
        self.assertEqual(list((self.root/'boot').iterdir()),[])

    def test_pin_without_package_fails_before_nbd(self):
        env=dict(os.environ,KERNEL_PACKAGE='',KERNEL_PACKAGE_SHA256='a'*64,CAMERA_CANDIDATE_PACKAGE='',CAMERA_CANDIDATE_MANIFEST_SHA256='')
        q=subprocess.run(['bash',str(REPO/'build_rootfs.sh')],env=env,cwd=self.root,capture_output=True,text=True)
        self.assertNotEqual(q.returncode,0);self.assertIn('requires explicit KERNEL_PACKAGE',q.stderr)
        self.assertFalse((self.root/'images').exists())

    def test_integrated_pin_validation_precedes_nbd(self):
        text=(REPO/'build_rootfs.sh').read_text()
        self.assertLess(text.index('preflight_integrated_kernel_package.py'),text.index('modprobe nbd'))


class PackagePreflightTests(unittest.TestCase):
    # Separate reader fixtures: none is signed, none is an install/boot proof.
    setUp=BundleTests.setUp
    write=BundleTests.write
    def make_package(self,extra=None):
        m=dict(self.manifest,files_sha256={k:packager.sha(v) for k,v in self.files.items()})
        prefix='usr/lib/modules/'+self.release
        fields=dict(self.files)
        fields[self.boot+'/manifest.json']=json.dumps(m).encode()
        fields[prefix+'/vmlinuz']=self.files[self.boot+'/vmlinuz']
        fields[prefix+'/pkgbase']=b'linux-latte-integrated\n'
        fields['usr/share/doc/linux-latte-integrated/module-signing.x509']=b'certificate-fixture'
        fields['etc/mkinitcpio.d/linux-latte-integrated.preset']=('ALL_kver="/'+prefix+'/vmlinuz"\ndefault_image="/boot/initramfs-linux-latte-integrated.img"\n').encode()
        fields['.PKGINFO']=b'pkgname = linux-latte-integrated\npkgbase = linux-latte-integrated\narch = x86_64\npkgver = 6.14.0.r26-1\n'
        fields['.BUILDINFO']=b'fixture';fields['.MTREE']=b'fixture'
        if extra:fields.update(extra)
        raw=io.BytesIO()
        with tarfile.open(fileobj=raw,mode='w') as t:
            for name,data in fields.items():
                row=tarfile.TarInfo(name);row.size=len(data);row.mode=0o644;t.addfile(row,io.BytesIO(data))
        compressed=subprocess.check_output(['zstd','-q','-c'],input=raw.getvalue());path=self.root/'package.pkg.tar.zst';path.write_bytes(compressed)
        return path,packager.sha(compressed)

    def test_read_only_package_preflight_does_not_infer_crypto_or_boot(self):
        p,pin=self.make_package();r=preflight.check(p,pin)
        self.assertEqual(r['modules'],1);self.assertFalse(r['new_cryptographic_signature_validation'])
        self.assertFalse(r['image_build_or_install_performed'])

    def test_install_script_in_package_rejected(self):
        p,pin=self.make_package({'.INSTALL':b'forbidden'});self.assertRaises(ValueError,preflight.check,p,pin)

    def test_extra_global_payload_rejected(self):
        p,pin=self.make_package({'etc/shadow':b'forbidden'});self.assertRaises(ValueError,preflight.check,p,pin)

    def test_bad_package_external_pin(self):
        p,pin=self.make_package();self.assertRaises(ValueError,preflight.check,p,'0'*64)




class SourceBuild72GateTests(unittest.TestCase):
    def test_source_family_and_revision_matrix(self):
        import tempfile
        text=(REPO/'scripts/build_kernel_package.sh').read_text()
        a=text.index('# Accept only the two explicitly integrated kernel families')
        b=text.index('python "${repo_root}/scripts/stage_kernel_support.py"',a)
        block=text[a:b]
        cases=[(6,14,0,'1',True),(7,2,0,'1',True),(7,2,0,'2',True),
               (7,2,12,'1',False),(7,3,0,'1',False),(6,18,0,'1',False),
               (7,2,0,'0',False),(7,2,0,'1; echo unsafe',False)]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for major,minor,sub,revision,ok in cases:
                (root/'Makefile').write_text(f'VERSION = {major}\nPATCHLEVEL = {minor}\nSUBLEVEL = {sub}\n')
                q=subprocess.run(['bash','-c','set -eu; pkgbase=linux-latte-cachyos;\n'+block+'\nprintf "%s|%s|%s\\n" "$pkgbase" "$localversion_suffix" "$expected_localversion"'],cwd=root,capture_output=True,text=True,env=dict(os.environ,KERNEL_INTEGRATED_REVISION=revision))
                self.assertEqual(q.returncode==0,ok,(major,minor,sub,revision,q.stderr))
                if ok and major==7:
                    self.assertIn('linux-latte-integrated-7-2|-r'+revision,q.stdout)
                    self.assertIn('CONFIG_LOCALVERSION="-mipad2-integrated"',q.stdout)
                if ok and major==6:self.assertIn('linux-latte-cachyos||',q.stdout)

    def test_default_revision_matches_r2_candidate_workflow(self):
        text=(REPO/'scripts/build_kernel_package.sh').read_text()
        a=text.index('# Accept only the two explicitly integrated kernel families')
        b=text.index('python "${repo_root}/scripts/stage_kernel_support.py"',a)
        env=dict(os.environ);env.pop('KERNEL_INTEGRATED_REVISION',None)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'Makefile').write_text('VERSION = 7\nPATCHLEVEL = 2\nSUBLEVEL = 0\n')
            q=subprocess.run(['bash','-c','set -eu; pkgbase=linux-latte-cachyos;\n'+text[a:b]+'\nprintf "%s" "$localversion_suffix"'],cwd=root,env=env,capture_output=True,text=True)
            self.assertEqual(q.returncode,0,q.stderr);self.assertEqual(q.stdout,'-r2')
        import yaml
        workflow=yaml.safe_load((REPO/'.github/workflows/build-dnx.yml').read_text())
        self.assertEqual(workflow['env']['KERNEL_INTEGRATED_REVISION'],'2')

    def test_manual_workflow_and_variable_expansion(self):
        text=(REPO/'.github/workflows/build-dnx.yml').read_text()
        self.assertIn('workflow_dispatch:',text)
        self.assertNotIn('  push:',text)
        self.assertIn('KERNEL_REF: codex/mipad2-7.2-integrated',text)
        self.assertIn('grep -q "usr/share/doc/${pkgbase}/source-commit"',text)
        self.assertNotIn("grep -q 'usr/share/doc/${pkgbase}/source-commit'",text)

if __name__ == '__main__':unittest.main()

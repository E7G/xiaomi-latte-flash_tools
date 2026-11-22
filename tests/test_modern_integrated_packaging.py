"""Parser/identity regression tests; native makepkg/CMS qualification is separate."""
from pathlib import Path
import sys,unittest,io,tarfile,json,subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import package_integrated_kernel as p
from test_integrated_kernel_packaging import BundleTests


class ModernTests(unittest.TestCase):
    def prefixed(self,f):
        f.write()
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w') as archive:
            for name,value in [*f.files.items(),(f.boot+'/manifest.json',json.dumps(f.manifest).encode())]:
                row=tarfile.TarInfo('./'+name);row.size=len(value);row.mode=0o644
                archive.addfile(row,io.BytesIO(value))
        compressed=subprocess.check_output(['zstd','-q','-c'],input=data.getvalue())
        f.archive.write_bytes(compressed);f.pin=p.sha(compressed)

    def fixture(self,modern=True):
        f=BundleTests('test_actual_reader_checks_fixture_bytes_not_signatures');f.setUp()
        self.addCleanup(f.doCleanups)
        if modern:
            old=f.release;f.release='7.2.15-mipad2-integrated-adc2'
            f.boot='var/lib/mipad2-kernel/'+f.release
            f.files={k.replace(old,f.release):v.replace(old.encode(),f.release.encode()) for k,v in f.files.items()}
            f.files[f.boot+'/Module.symvers']=b'symbols'
            f.files[f.boot+'/module-signing-public.x509']=b'public-fixture'
            f.manifest['kernelrelease']=f.release;del f.manifest['modules']
            f.manifest.update(module_count=1,signature_negative_control_passed=True,module_certificate_sha256=p.sha(b'public-fixture'))
        return f

    def test_identity_version_recipe_roundtrip(self):
        bases=set()
        for flavor in ['daily3','adc1','adc2','lpat9','lpat30','lpat31']:
            release='7.2.15-mipad2-integrated-'+flavor
            base,version=p.identity(release);bases.add(base)
            self.assertEqual(p.release_from_version(version),release)
            self.assertIn('pkgbase='+base,p.recipe(version,'a'*64))
        self.assertEqual(len(bases),6)
        self.assertNotIn(p.PKGBASE_72,bases)

    def test_unsupported_versions(self):
        for v in ['7.3.0.adc2','7.2.015.adc2','7.2.15.adc3','7.2.15.r1']:
            self.assertRaises(ValueError,p.release_from_version,v)

    def test_modern_bundle_with_declared_prefix(self):
        f=self.fixture();self.prefixed(f)
        m,files=p.load_bundle(f.archive,f.pin);self.assertEqual(p.module_count(m),1)

    def test_normalized_duplicate_rejected(self):
        f=self.fixture();f.write([('./'+next(iter(f.files)),b'alias')])
        self.assertRaises(ValueError,p.load_bundle,f.archive,f.pin)

    def test_double_prefix_rejected(self):
        self.assertRaises(ValueError,p.bundle_name,'././usr/file',False)

    def test_legacy_prefix_stays_rejected(self):
        f=self.fixture(False);self.prefixed(f)
        self.assertRaises(ValueError,p.load_bundle,f.archive,f.pin)

    def test_private_key_rejected_even_in_manifest(self):
        f=self.fixture();f.files[f.boot+'/signing_key.pem']=b'not-allowed';f.write()
        self.assertRaises(ValueError,p.load_bundle,f.archive,f.pin)

    def test_count_ambiguity_rejected(self):
        f=self.fixture();f.manifest['modules']=1;f.write()
        self.assertRaises(ValueError,p.load_bundle,f.archive,f.pin)

    def test_bool_count_rejected(self):
        f=self.fixture();f.manifest['module_count']=True;f.write()
        self.assertRaises(ValueError,p.load_bundle,f.archive,f.pin)

    def test_missing_negative_control_rejected(self):
        f=self.fixture();f.manifest.pop('signature_negative_control_passed');f.write()
        self.assertRaises(ValueError,p.load_bundle,f.archive,f.pin)

    def test_missing_certificate_pin_rejected(self):
        f=self.fixture();f.manifest.pop('module_certificate_sha256');f.write()
        self.assertRaises(ValueError,p.load_bundle,f.archive,f.pin)

    def test_wrong_count_rejected(self):
        f=self.fixture();f.manifest['module_count']=2;f.write()
        self.assertRaises(ValueError,p.load_bundle,f.archive,f.pin)


if __name__=='__main__':unittest.main()

"""Isolated fake-root install/selection tests; no real ESP, ALPM install or image."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_integrated_kernel_packaging import KernelInstallTests,RootfsKernelBaseTests
import resolve_kernel_artifact as resolver


class ModernInstallerTests(KernelInstallTests):
    def test_all_flavors_install_only_their_own_image(self):
        self.package('linux-latte-integrated')
        old=self.root/'boot/vmlinuz-linux-latte-integrated';old.write_text('stable sentinel')
        for flavor in ['daily3','adc1','adc2','lpat9','lpat30','lpat31']:
            base='linux-latte-integrated-7-2-'+flavor
            self.package(base,'7.2.15-mipad2-integrated-'+flavor)
            q=self.run_installer([base]);self.assertEqual(q.returncode,0,q.stderr)
            self.assertEqual((self.root/'boot'/('vmlinuz-'+base)).read_text(),'kernel '+base)
            self.assertEqual(old.read_text(),'stable sentinel')

    def test_cross_flavor_rejected_before_boot_write(self):
        base='linux-latte-integrated-7-2-adc2'
        self.package(base,'7.2.15-mipad2-integrated-adc1')
        self.assertNotEqual(self.run_installer([base]).returncode,0)
        self.assertFalse((self.root/'boot'/('vmlinuz-'+base)).exists())

    def test_modern_failure_preserves_existing_image(self):
        base='linux-latte-integrated-7-2-adc2';self.package(base,'7.2.15-mipad2-integrated-adc2')
        image=self.root/'boot'/('vmlinuz-'+base);image.write_text('old sentinel')
        q=self.run_installer([base],PREFLIGHT_CODE='1')
        self.assertNotEqual(q.returncode,0);self.assertEqual(image.read_text(),'old sentinel')

    def test_hook_targets_each_flavor_explicitly(self):
        for name in ['kernel.hook','kernel-preflight.hook']:
            text=(Path(__file__).resolve().parents[1]/'device_files'/name).read_text()
            for flavor in ['daily3','adc1','adc2','lpat9','lpat30','lpat31']:
                self.assertIn('Target = linux-latte-integrated-7-2-'+flavor,text)


class ModernRootfsTests(RootfsKernelBaseTests):
    def test_all_flavors_select_distinct_boot_images(self):
        # Each fixture has exactly one release, as a real rootfs build requires.
        for flavor in ['daily3','adc1','adc2','lpat9','lpat30','lpat31']:
            with self.subTest(flavor=flavor):
                fixture=RootfsKernelBaseTests('test_integrated_base_derived_from_installed_package');fixture.setUp()
                try:
                    base='linux-latte-integrated-7-2-'+flavor
                    q=fixture.run_block(release='7.2.15-mipad2-integrated-'+flavor,metadata=base)
                    self.assertEqual(q.returncode,0,q.stderr)
                    self.assertTrue((fixture.root/'boot'/('vmlinuz-'+base)).exists())
                finally:fixture.doCleanups()

    def test_cross_flavor_is_not_a_valid_rootfs(self):
        q=self.run_block(release='7.2.15-mipad2-integrated-adc1',metadata='linux-latte-integrated-7-2-adc2')
        self.assertNotEqual(q.returncode,0);self.assertEqual(list((self.root/'boot').iterdir()),[])

    def test_new_lpat_flavors_cannot_use_another_installed_flavor(self):
        for source, target in [('lpat9','lpat30'), ('lpat30','lpat31')]:
            with self.subTest(source=source, target=target):
                q=self.run_block(release='7.2.15-mipad2-integrated-'+source,
                                 metadata='linux-latte-integrated-7-2-'+target)
                self.assertNotEqual(q.returncode,0)
                self.assertEqual(list((self.root/'boot').iterdir()),[])

    def test_unsupported_flavor_rejected(self):
        q=self.run_block(release='7.2.15-mipad2-integrated-lpat32',metadata='linux-latte-integrated-7-2-lpat32')
        self.assertNotEqual(q.returncode,0)


class ModernResolverIdentityTests(unittest.TestCase):
    def test_only_matching_flavor_release_patterns(self):
        import re
        for flavor in ['daily3','adc1','adc2','lpat9','lpat30','lpat31']:
            pattern=resolver.BASES['linux-latte-integrated-7-2-'+flavor]
            self.assertIsNotNone(re.fullmatch(pattern,'7.2.15-mipad2-integrated-'+flavor))
            self.assertIsNone(re.fullmatch(pattern,'7.3.0-mipad2-integrated-'+flavor))
            self.assertIsNone(re.fullmatch(pattern,'7.2.015-mipad2-integrated-'+flavor))


if __name__=='__main__':unittest.main()

# SPDX-License-Identifier: GPL-2.0
"""Exercise the real nobody-user access boundary under restrictive root umask.

No kernel, package signing key, package build, pacman transaction or boot file is
used. Bundle/signature readers are fixture stubs; runuser/test and chmod/chown
are real. The makepkg boundary is stopped after checking config readability.
"""
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import package_integrated_kernel as packager


@unittest.skipUnless(os.geteuid() == 0 and shutil.which('runuser'), 'Real root-to-nobody boundary needs root/runuser')
class RestrictiveUmask(unittest.TestCase):
    def test_generated_config_readable_by_packaging_user_under_private_umask(self):
        nobody = pwd.getpwnam('nobody')
        self.assertNotEqual(nobody.pw_uid, 0)
        real_run = subprocess.run
        with tempfile.TemporaryDirectory(prefix='mipad2-package-umask-test-', dir='/var/tmp') as directory:
            parent = Path(directory)
            parent.chmod(0o755)
            bundle_dir = parent / 'inputs'
            bundle_dir.mkdir(mode=0o755)
            bundle = bundle_dir / 'fixture.bundle'
            cert = bundle_dir / 'public-fixture.cert'
            bundle.write_bytes(b'not-a-real-bundle')
            cert.write_bytes(b'not-a-real-certificate')
            output = parent / 'output'
            release = '7.2.0-mipad2-integrated-r8'
            boot = 'var/lib/mipad2-kernel/' + release
            files = {boot + '/' + n: (b'fixture-' + n.encode(), 0o644)
                     for n in ['vmlinuz', 'config', 'System.map']}
            manifest = dict(kernelrelease=release, source_commit='a' * 40)
            observations = []

            def stop_before_makepkg(args, **kwargs):
                self.assertEqual(args[:4], ['runuser', '-u', 'nobody', '--'])
                self.assertEqual(args[4], 'makepkg')
                conf = Path(args[args.index('--config') + 1])
                probe = real_run(['runuser', '-u', 'nobody', '--', 'test', '-r', str(conf)],
                                 capture_output=True, text=True, timeout=10)
                observations.append(dict(config_readable=probe.returncode == 0,
                                         root_mode=output.stat().st_mode & 0o777,
                                         work_uid=conf.parent.stat().st_uid,
                                         config_uid=conf.stat().st_uid))
                # No actual makepkg or installation. Retain ordinary failure path.
                return subprocess.CompletedProcess(args, 17)

            old = os.umask(0o077)
            try:
                with patch.object(packager, 'load_bundle', return_value=(manifest, files)), \
                     patch.object(packager, 'verify_modules', return_value=1), \
                     patch.object(packager.shutil, 'which', return_value='/fixture/available'), \
                     patch.object(packager.subprocess, 'run', side_effect=stop_before_makepkg):
                    with self.assertRaisesRegex(ValueError, 'makepkg failed'):
                        packager.build(bundle, 'a' * 64, cert, 'b' * 64, output, 1)
            finally:
                os.umask(old)
            self.assertEqual(len(observations), 1)
            self.assertTrue(observations[0]['config_readable'], observations)
            self.assertEqual(observations[0]['work_uid'], nobody.pw_uid)
            self.assertEqual(observations[0]['config_uid'], nobody.pw_uid)
            self.assertEqual((output / 'makepkg.log').stat().st_mode & 0o777, 0o600)
            self.assertEqual(bundle.read_bytes(), b'not-a-real-bundle')
            self.assertEqual(cert.read_bytes(), b'not-a-real-certificate')


if __name__ == '__main__':
    unittest.main()

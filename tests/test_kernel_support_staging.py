"""Exercise the actual payload stager; no pacman, build, mount or device writes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/stage_kernel_support.py'
spec = importlib.util.spec_from_file_location('stage_kernel_support', SCRIPT)
stager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stager)


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mipad2-support-staging-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.package = self.root / 'package'
        for name, _, _ in stager.PAYLOAD:
            path = self.source / 'fix_file' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('tracked ' + name + '\n').encode())

    def test_actual_copy_and_manifest(self):
        manifest = stager.stage(self.source, self.package)
        self.assertEqual(len(manifest['files']), len(stager.PAYLOAD))
        for name, destination, mode in stager.PAYLOAD:
            src, dst = self.source / 'fix_file' / name, self.package / destination
            self.assertEqual(src.read_bytes(), dst.read_bytes())
            self.assertEqual(dst.stat().st_mode & 0o777, mode)
        self.assertEqual(json.loads((self.package / stager.MANIFEST).read_text()), manifest)
        self.assertIn('usr/lib/systemd/system-sleep/mipad2-usb-serial', manifest['files'])

    def test_dry_run_does_not_write(self):
        stager.stage(self.source, self.package, True)
        self.assertFalse(self.package.exists())

    def test_missing_last_source_fails_before_first_copy(self):
        (self.source / 'fix_file' / stager.PAYLOAD[-1][0]).unlink()
        with self.assertRaises(FileNotFoundError):
            stager.stage(self.source, self.package)
        self.assertFalse(self.package.exists())

    def test_generated_src_tree_is_not_required(self):
        self.assertFalse(list(self.source.glob('fix_file/packages/*/src')))
        stager.stage(self.source, self.package)

    def test_source_symlink_rejected(self):
        path = self.source / 'fix_file' / stager.PAYLOAD[0][0]
        external = self.root / 'external'
        external.write_text('external')
        path.unlink()
        path.symlink_to(external)
        with self.assertRaises(ValueError):
            stager.stage(self.source, self.package)
        self.assertFalse(self.package.exists())

    def test_destination_parent_symlink_rejected(self):
        external = self.root / 'external'
        external.mkdir()
        self.package.mkdir()
        (self.package / 'usr').symlink_to(external)
        with self.assertRaises(ValueError):
            stager.stage(self.source, self.package)
        self.assertFalse(list(external.iterdir()))

    def test_staging_inside_source_rejected(self):
        with self.assertRaises(ValueError):
            stager.stage(self.source, self.source / 'package')

    def test_path_traversal_rejected(self):
        for name in ('../outside', '/absolute'):
            with self.assertRaises(ValueError):
                stager.contained(self.root, name)


if __name__ == '__main__':
    unittest.main()

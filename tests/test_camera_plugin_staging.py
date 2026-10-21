"""Host staging contracts, not camera/device acceptance."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('stager', Path(__file__).resolve().parents[1] / 'scripts/stage_camera_plugins.py')
stager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stager)


@unittest.skipUnless(shutil.which('cc') and shutil.which('readelf'), 'C compiler and readelf required')
class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / 'build'
        self.plugins = self.build / 'plugins'
        self.plugins.mkdir(parents=True)
        self.output = self.root / 'package'
        source = self.root / 'fixture.c'
        source.write_text('#include <stdio.h>\nint test(void) { return puts("fixture"); }\n')
        binary = self.root / 'fixture.so'
        subprocess.run(['cc', '-shared', '-fPIC', str(source), '-o', str(binary)],
                       check=True, capture_output=True)
        components = []
        for component, name in stager.EXPECTED.items():
            destination = self.plugins / name
            shutil.copyfile(binary, destination)
            components.append(dict(name=component, plugin='plugins/' + name, compiled=True,
                                   build_rpath_removed=True, binary_sha256=stager.sha(destination),
                                   bytes=destination.stat().st_size,
                                   needed_libraries=stager.elf_check(destination)))
        self.receipt = dict(schema=1, state='plugins-built-host-only', upstream_version='1.28.7',
                            recipe_sha256='f' * 64, build_abi={key: '1.28.7' for key in stager.ABI},
                            components=components)
        self.pin()

    def pin(self):
        self.path = self.build / 'receipt.json'
        self.path.write_text(json.dumps(self.receipt))
        self.receipt_sha = stager.sha(self.path)

    def run_stage(self, **kwargs):
        return stager.stage(self.build, self.output, self.receipt_sha, **kwargs)

    def test_exact_payload_and_no_app_or_default_promotion(self):
        manifest = self.run_stage()
        self.assertEqual(len(manifest['files']), 3)
        self.assertFalse(manifest['app_included'])
        self.assertFalse(manifest['aac_included'])
        self.assertFalse(manifest['launcher_included'])
        self.assertFalse(manifest['image_qualified'])
        for name, value in manifest['files'].items():
            self.assertEqual(stager.sha(self.output / name), value['sha256'])
        self.assertEqual(len([p for p in self.output.rglob('*') if p.is_file()]), 4)

    def test_dry_run_never_creates_output(self):
        self.assertEqual(len(self.run_stage(dry_run=True)['files']), 3)
        self.assertFalse(self.output.exists())

    def test_receipt_must_be_explicit_and_hash_pinned(self):
        for pin in ['', 'f' * 40, 'Z' * 64, '0' * 64]:
            self.assertRaises(ValueError, stager.stage, self.build, self.output, pin)
        self.assertFalse(self.output.exists())

    def test_wrong_state_or_abi_rejected_before_write(self):
        original = json.loads(json.dumps(self.receipt))
        for changes in [dict(state='sources-prepared'), dict(upstream_version='1.28.4'),
                        dict(build_abi={key: '1.28.4' for key in stager.ABI})]:
            self.receipt = dict(original, **changes)
            self.pin()
            self.assertRaises(ValueError, self.run_stage)
            self.assertFalse(self.output.exists())

    def test_tampered_plugin_rejected_before_write(self):
        (self.plugins / 'libgstva.so').write_bytes(b'tampered')
        self.assertRaises(ValueError, self.run_stage)
        self.assertFalse(self.output.exists())

    def test_plugin_traversal_or_missing_component_rejected(self):
        self.receipt['components'][0]['plugin'] = '../outside.so'
        self.pin()
        self.assertRaises(ValueError, self.run_stage)
        self.receipt['components'] = self.receipt['components'][1:]
        self.pin()
        self.assertRaises(ValueError, self.run_stage)
        self.assertFalse(self.output.exists())

    def test_symlinked_input_rejected(self):
        p = self.plugins / 'libgstva.so'
        real = p.with_suffix('.real')
        p.rename(real)
        p.symlink_to(real)
        self.assertRaises(ValueError, self.run_stage)
        self.assertFalse(self.output.exists())

    def test_existing_or_nested_output_not_touched(self):
        self.assertRaises(ValueError, stager.stage, self.build, self.build / 'package', self.receipt_sha)
        self.output.mkdir()
        sentinel = self.output / 'keep'
        sentinel.write_text('unchanged')
        self.assertRaises(ValueError, self.run_stage)
        self.assertEqual(sentinel.read_text(), 'unchanged')

    def test_real_rpath_rejected_even_with_matching_claimed_hash(self):
        source = self.root / 'rpath.c'
        source.write_text('#include <stdio.h>\nint test(void) { return puts("fixture"); }\n')
        p = self.plugins / 'libgstencoding.so'
        subprocess.run(['cc', '-shared', '-fPIC', str(source), '-o', str(p), '-Wl,-rpath=/private/build'],
                       check=True, capture_output=True)
        c = self.receipt['components'][0]
        c.update(binary_sha256=stager.sha(p), bytes=p.stat().st_size)
        self.pin()
        self.assertRaises(ValueError, self.run_stage)
        self.assertFalse(self.output.exists())

    def aac_fixture(self):
        root = self.root / 'aac'
        plugins = root / 'plugins'
        plugins.mkdir(parents=True)
        for label, soname in [('codec', 'libavcodec.so.63'), ('util', 'libavutil.so.61')]:
            source = self.root / (label + '.c')
            source.write_text('int fixture_' + label + '(void) { return 1; }\n')
            subprocess.run(['cc', '-shared', '-fPIC', str(source), '-o', str(self.root / ('lib'+label+'.so')),
                            '-Wl,-soname,' + soname], check=True, capture_output=True)
        source = self.root / 'aac.c'
        source.write_text('extern int fixture_codec(void); extern int fixture_util(void);\nint test(void) { return fixture_codec()+fixture_util(); }\n')
        plugin = plugins / 'libgstlibav.so'
        subprocess.run(['cc', '-shared', '-fPIC', str(source), '-o', str(plugin),
                        '-L'+str(self.root), '-lcodec', '-lutil'], check=True, capture_output=True)
        receipt = dict(schema=1, state='aac-plugin-built-host-only', upstream_version='1.28.7',
                       gstreamer_build_abi={key: '1.28.7' for key in stager.ABI},
                       ffmpeg_build_abi=stager.AAC_ABI, recipe_sha256='e'*64,
                       plugin='plugins/libgstlibav.so', build_rpath_removed=True,
                       sdk_libraries_deployed=False, binary_sha256=stager.sha(plugin),
                       bytes=plugin.stat().st_size, needed_libraries=stager.elf_check(plugin))
        (root/'receipt.json').write_text(json.dumps(receipt))
        return root, receipt

    def test_optional_aac_adds_only_one_source_plugin(self):
        root, receipt = self.aac_fixture()
        result = stager.stage(self.build, self.output, self.receipt_sha,
                              aac_root=root, aac_receipt_sha256=stager.sha(root/'receipt.json'))
        self.assertEqual(len(result['files']), 4)
        self.assertTrue(result['aac_included'])
        self.assertFalse(result['app_included'])
        self.assertFalse(result['sdk_libraries_deployed'])
        self.assertEqual(len([p for p in self.output.rglob('*') if p.is_file()]), 5)

    def test_aac_options_must_be_paired(self):
        self.assertRaises(ValueError, stager.stage, self.build, self.output, self.receipt_sha, aac_root=self.root)
        self.assertRaises(ValueError, stager.stage, self.build, self.output, self.receipt_sha, aac_receipt_sha256='0'*64)
        self.assertFalse(self.output.exists())

    def test_wrong_aac_receipt_or_abi_before_write(self):
        root, receipt = self.aac_fixture()
        self.assertRaises(ValueError, stager.stage, self.build, self.output, self.receipt_sha,
                          aac_root=root, aac_receipt_sha256='0'*64)
        receipt['ffmpeg_build_abi'] = dict(receipt['ffmpeg_build_abi'], libavcodec='62.28.102')
        (root/'receipt.json').write_text(json.dumps(receipt))
        self.assertRaises(ValueError, stager.stage, self.build, self.output, self.receipt_sha,
                          aac_root=root, aac_receipt_sha256=stager.sha(root/'receipt.json'))
        self.assertFalse(self.output.exists())

    def test_tampered_aac_rejected_before_any_output(self):
        root, receipt = self.aac_fixture()
        (root/'plugins/libgstlibav.so').write_bytes(b'tampered')
        self.assertRaises(ValueError, stager.stage, self.build, self.output, self.receipt_sha,
                          aac_root=root, aac_receipt_sha256=stager.sha(root/'receipt.json'))
        self.assertFalse(self.output.exists())

    def test_symlinked_aac_root_rejected(self):
        root, receipt = self.aac_fixture()
        link = self.root/'linked-aac'
        link.symlink_to(root, target_is_directory=True)
        self.assertRaises(ValueError, stager.stage, self.build, self.output, self.receipt_sha,
                          aac_root=link, aac_receipt_sha256=stager.sha(root/'receipt.json'))
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
import stage_camera_app as app
import camera_candidate_launcher as launcher


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base/'build'
        self.root.mkdir()
        self.out = self.base/'out'
        self.commit = 'a'*40
        self.prefix = '/usr/local/lib/mipad2-camera-source-'+self.commit[:12]
        self.receipt = dict(schema=1, state='source-application-built-staged-host-only',
                            source_commit=self.commit, prefix=self.prefix,
                            recipe_sha256='b'*64, cargo_locked=True, cargo_offline=True,
                            cargo_profile='release', rpath_absent=True,
                            gstreamer_build_abi={key:'1.28.7' for key in app.ABI}, files={})
        schema = '''<schemalist><schema id="org.gnome.Snapshot" path="/org/gnome/Snapshot/">
        <key name="enable-hardware-encoding" type="b"><default>false</default></key>
        <key name="enable-audio-recording" type="b"><default>false</default></key>
        <key name="play-shutter-sound" type="b"><default>true</default></key>
        <key name="is-maximized" type="b"><default>false</default></key>
        <key name="countdown" type="i"><default>0</default></key></schema></schemalist>'''
        self.add('bin/snapshot', 'fake-elf')
        self.add('share/glib-2.0/schemas/org.gnome.Snapshot.gschema.xml', schema)
        self.add('share/glib-2.0/schemas/gschemas.compiled', 'old')
        for i in range(10):
            self.add('share/locale/'+str(i), 'fixture')
        self.receipt['application_sha256'] = self.receipt['files'][self.prefix.lstrip('/')+'/bin/snapshot']['sha256']
        self.save()
        self.plugin_files = {f'usr/local/lib/mipad2-gst-functional/{"c"*64}/plugin/{n}.so': {} for n in range(4)}
        self.plan = dict(files=self.plugin_files, aac_included=True)
        self.elf = patch.object(app, 'elf_check', return_value=['libc.so.6'])
        self.elf.start()
        self.addCleanup(self.elf.stop)
        self.stage = patch.object(app, 'stage', side_effect=self.fake_stage)
        self.stage.start()
        self.addCleanup(self.stage.stop)

    def add(self, relative, text):
        name = self.prefix.lstrip('/')+'/'+relative
        p = self.root/'package'/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        self.receipt['files'][name] = dict(sha256=app.sha(p), bytes=p.stat().st_size, mode='0o644')

    def save(self):
        (self.root/'receipt.json').write_text(json.dumps(self.receipt))
        self.pin = app.sha(self.root/'receipt.json')

    def fake_stage(self, root, output, pin, dry, aac, aac_pin):
        if not dry:
            output.mkdir()
            for n in self.plugin_files:
                p = output/n
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'plugin')
        return self.plan

    def compose(self, **kwargs):
        return app.compose(self.root, self.out, self.pin, self.base/'plugins', 'c'*64,
                           self.base/'aac', 'd'*64, **kwargs)

    def rejected(self):
        self.assertRaises(ValueError, self.compose, dry_run=True)
        self.assertFalse(self.out.exists())

    def test_dry_run_never_writes_or_implies_device_pass(self):
        r = self.compose(dry_run=True)
        self.assertFalse(self.out.exists())
        self.assertFalse(r['device_tested'])
        self.assertFalse(r['image_qualified'])
        self.assertFalse(r['stable_desktop_changed'])

    def test_receipt_pin_mismatch(self):
        self.pin = '0'*64
        self.rejected()

    def test_missing_or_incomplete_abi(self):
        self.receipt['gstreamer_build_abi'].pop('gstreamer-1.0')
        self.save()
        self.rejected()

    def test_unlocked_build_rejected(self):
        self.receipt['cargo_locked'] = False
        self.save()
        self.rejected()

    def test_prefix_must_match_compiled_commit(self):
        self.receipt['prefix'] += '-other'
        self.save()
        self.rejected()

    def test_hash_mismatch(self):
        (self.root/'package'/self.prefix.lstrip('/')/'bin/snapshot').write_text('changed')
        self.rejected()

    def test_extra_payload_rejected(self):
        (self.root/'package/extra').write_text('extra')
        self.rejected()

    def test_payload_symlink_rejected(self):
        (self.root/'package/link').symlink_to('/etc/passwd')
        self.rejected()

    def test_non_private_manifest_path_rejected(self):
        self.receipt['files']['usr/bin/snapshot'] = self.receipt['files'].pop(self.prefix.lstrip('/')+'/bin/snapshot')
        self.save()
        self.rejected()

    def test_existing_output_untouched(self):
        self.out.mkdir()
        sentinel = self.out/'keep'
        sentinel.write_text('keep')
        self.assertRaises(ValueError, self.compose)
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_source_aac_required(self):
        self.plan['aac_included'] = False
        self.rejected()

    @unittest.skipUnless(shutil.which('glib-compile-schemas'), 'GLib tools required')
    def test_actual_staging_defaults_and_no_global_service(self):
        r = self.compose()
        self.assertEqual(r['state'], 'camera-candidate-staged-host-only')
        self.assertFalse((self.out/'usr/share/dbus-1/services/org.gnome.Snapshot.service').exists())
        self.assertFalse((self.out/'usr/share/applications/org.gnome.Snapshot.desktop').exists())
        desktop = (self.out/r['desktop_file']).read_text()
        self.assertIn('DBusActivatable=false', desktop)
        schemas = self.out/self.prefix.lstrip('/')/'share/glib-2.0/schemas'
        self.assertIn('play-shutter-sound=false', (schemas/'90_mipad2_candidate.gschema.override').read_text())
        self.assertNotEqual((schemas/'gschemas.compiled').read_bytes(), b'old')
        for n, entry in r['files'].items():
            self.assertEqual(app.sha(self.out/n), entry['sha256'])

    def test_async_profile_is_explicit_and_default_stays_off(self):
        self.assertFalse(self.compose(dry_run=True)['raw_async'])
        self.assertTrue(self.compose(dry_run=True, raw_async=True)['raw_async'])
        self.assertFalse(self.out.exists())

    def test_invalid_async_profile_rejected_before_output(self):
        for value in [1, 0, 'true', '1', None, [], {}]:
            with self.subTest(value=value):
                self.assertRaises(ValueError, self.compose, raw_async=value)
                self.assertFalse(self.out.exists())

    def test_async_candidate_serialized_and_hash_pinned(self):
        r = self.compose(raw_async=True)
        config = self.out/self.prefix.lstrip('/')/'bin/candidate-profile.json'
        self.assertIs(json.loads(config.read_text())['raw_async'], True)
        self.assertEqual(json.loads(config.read_text())['profile_name'],
                         'mipad2-camera-source-'+self.commit[:12]+'-raw-async')
        self.assertEqual(r['files'][config.relative_to(self.out).as_posix()]['sha256'], app.sha(config))
        self.assertFalse(r['device_tested'])
        self.assertFalse(r['image_qualified'])
        self.assertFalse(r['stable_desktop_changed'])

    def test_async_launcher_changes_only_source_scheduling_switch(self):
        cfg = dict(prefix=self.prefix, plugin_directories=['/one','/two'])
        inherited = dict(MIPAD2_CAPTURE_RAW_ASYNC='1', MIPAD2_CAPTURE_DECOUPLE='1',
                         MIPAD2_DIAGNOSTIC_ACTIONS='1', LD_PRELOAD='/tmp/trace.so')
        off = launcher.environment(inherited, cfg, self.base/'config', self.base/'cache')
        on = launcher.environment(inherited, dict(cfg, raw_async=True), self.base/'config', self.base/'cache')
        self.assertEqual(off['MIPAD2_CAPTURE_RAW_ASYNC'], '0')
        self.assertEqual(on['MIPAD2_CAPTURE_RAW_ASYNC'], '1')
        self.assertEqual({k for k in off if off[k] != on[k]}, {'MIPAD2_CAPTURE_RAW_ASYNC'})
        for key in ['MIPAD2_CAPTURE_RAW_DIRECT', 'MIPAD2_CAPTURE_COPY', 'MIPAD2_CAPTURE_ALLOCATION_GUARD']:
            self.assertEqual(on[key], '1')
        for key in ['MIPAD2_CAPTURE_DECOUPLE', 'MIPAD2_CAPTURE_DECOUPLE_SMALL']:
            self.assertEqual(on[key], '0')
        self.assertNotIn('MIPAD2_DIAGNOSTIC_ACTIONS', on)
        self.assertNotIn('LD_PRELOAD', on)

    def test_launcher_rejects_nonboolean_async_setting(self):
        for value in [1, 0, 'true', '1', None, [], {}]:
            with self.subTest(value=value):
                self.assertRaises(ValueError, launcher.environment, {},
                                  dict(prefix=self.prefix, plugin_directories=[], raw_async=value),
                                  self.base/'config', self.base/'cache')

    def test_launcher_removes_diagnostic_and_library_injection(self):
        inherited = dict(MIPAD2_DIAGNOSTIC_ACTIONS='1', MIPAD2_DIAGNOSTIC_BACKGROUND_CAPTURE='1',
                         MIPAD2_ENCODE_INPUT_ONE='1', MIPAD2_PACING_FILE='/tmp/old',
                         GST_TRACERS='latency', GST_DEBUG_DUMP_DOT_DIR='/tmp',
                         GST_PLUGIN_PATH_1_0='/tmp/rejected', LD_PRELOAD='/tmp/profiler.so',
                         LD_LIBRARY_PATH='/tmp/sdk', WAYLAND_DISPLAY='wayland-1',
                         DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1000/bus')
        env = launcher.environment(inherited, dict(prefix=self.prefix, plugin_directories=['/one','/two']),
                                   self.base/'config', self.base/'cache')
        for name in ['MIPAD2_DIAGNOSTIC_ACTIONS', 'MIPAD2_DIAGNOSTIC_BACKGROUND_CAPTURE',
                     'MIPAD2_ENCODE_INPUT_ONE', 'MIPAD2_PACING_FILE', 'GST_TRACERS',
                     'GST_DEBUG_DUMP_DOT_DIR', 'LD_PRELOAD', 'LD_LIBRARY_PATH']:
            self.assertNotIn(name, env)
        self.assertEqual(env['GST_PLUGIN_PATH_1_0'], '/one:/two')
        self.assertEqual(env['MIPAD2_CAPTURE_COPY'], '1')
        self.assertEqual(env['MIPAD2_CAPTURE_RAW_ASYNC'], '0')
        self.assertEqual(env['WAYLAND_DISPLAY'], 'wayland-1')
        self.assertEqual(env['GSETTINGS_BACKEND'], 'keyfile')


if __name__ == '__main__':
    unittest.main()

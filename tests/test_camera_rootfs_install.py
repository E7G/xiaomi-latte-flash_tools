import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'scripts'))
import install_camera_candidate as installer


class RootfsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.package=self.base/'payload';self.package.mkdir()
        self.root=self.base/'rootfs'
        for path in ['usr/lib','etc','var/lib/pacman/local']:(self.root/path).mkdir(parents=True,exist_ok=True)
        for name,version in installer.ABI_PACKAGES.items():
            path=self.root/'var/lib/pacman/local'/(name+'-'+version+'-1')/'desc';path.parent.mkdir()
            path.write_text('%NAME%\n'+name+'\n\n%VERSION%\n'+version+'-1\n')
        self.commit='a'*40;self.prefix='usr/local/lib/mipad2-camera-source-'+self.commit[:12]
        self.desktop='usr/share/applications/org.gnome.Snapshot.MiPad2Source'+self.commit[:12]+'.desktop'
        self.manifest=dict(schema=1,state='camera-candidate-staged-host-only',source_plugin_count=4,
                           app_included=True,launcher_included=True,private_settings=True,
                           system_library_replacement=False,sdk_libraries_deployed=False,
                           stable_desktop_changed=False,dbus_activatable=False,
                           source_commit=self.commit,prefix='/'+self.prefix,desktop_file=self.desktop,files={})
        self.add(self.prefix+'/bin/snapshot','elf',0o755)
        self.add(self.prefix+'/bin/mipad2-camera-candidate','wrapper',0o755)
        self.add(self.desktop,'[Desktop Entry]\nDBusActivatable=false\nExec=/'+self.prefix+'/bin/mipad2-camera-candidate\n')
        for i in range(20):self.add(self.prefix+'/share/locale/'+str(i),'translation')
        for name in ['libgstencoding.so','libgstvideofilter.so','libgstva.so','libgstlibav.so']:
            family='mipad2-gst-aac-source' if name=='libgstlibav.so' else 'mipad2-gst-functional'
            self.add('usr/local/lib/'+family+'/'+'b'*64+'/plugin/'+name,'elf',0o755)
        directories=sorted({'/'+str(Path(name).parent) for name in self.manifest['files'] if name.endswith('.so')})
        self.add(self.prefix+'/bin/candidate-profile.json',json.dumps(dict(prefix='/'+self.prefix,source_commit=self.commit,plugin_directories=directories,diagnostic_actions=False,background_capture=False)))
        for suffix in ['gschemas.compiled','org.gnome.Snapshot.gschema.xml','90_mipad2_candidate.gschema.override']:
            self.add(self.prefix+'/share/glib-2.0/schemas/'+suffix,'fixture')
        self.add(self.prefix+'/share/snapshot/resources.gresource','fixture')
        self.manifest['launcher_recipe_sha256']=self.manifest['files'][self.prefix+'/bin/mipad2-camera-candidate']['sha256']
        self.manifest['application_sha256']=self.manifest['files'][self.prefix+'/bin/snapshot']['sha256']
        self.save()
        self.elf=patch.object(installer,'elf_check',return_value=['libc.so.6']);self.elf.start();self.addCleanup(self.elf.stop)

    def add(self,name,text,mode=0o644):
        p=self.package/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);p.chmod(mode)
        self.manifest['files'][name]=dict(sha256=installer.sha(p),bytes=p.stat().st_size,mode=oct(mode))

    def save(self):
        p=self.package/installer.METADATA;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(self.manifest));self.pin=installer.sha(p)

    def install(self,dry=True):return installer.install(self.package,self.root,self.pin,dry)

    def rejected(self):
        self.assertRaises(ValueError,self.install)
        self.assertFalse((self.root/installer.LEDGER).exists())

    def test_dry_run_has_no_writes_or_image_claim(self):
        result=self.install()
        self.assertEqual(result['state'],'camera-rootfs-install-planned')
        self.assertEqual(result['runtime_abi_versions'],installer.ABI_PACKAGES)
        self.assertFalse(result['image_boot_qualified'])
        self.assertFalse((self.root/self.prefix).exists())

    def test_wrong_pin_before_rootfs_write(self):
        self.pin='0'*64;self.rejected()

    def test_extra_source_rejected(self):
        (self.package/'extra').write_text('extra');self.rejected()

    def test_source_symlink_rejected(self):
        (self.package/'link').symlink_to('/etc/passwd');self.rejected()

    def test_hash_changed(self):
        (self.package/self.prefix/'bin/snapshot').write_text('different');self.rejected()

    def test_global_library_payload_rejected(self):
        self.add('usr/lib/libgstreamer-1.0.so.0','forbidden');self.save();self.rejected()

    def test_four_exact_plugin_names_required(self):
        name=next(k for k in self.manifest['files'] if k.endswith('libgstlibav.so'))
        del self.manifest['files'][name];(self.package/name).unlink();self.save();self.rejected()

    def test_required_resources_cannot_be_replaced_with_extra_locales(self):
        name=self.prefix+'/share/snapshot/resources.gresource'
        del self.manifest['files'][name];(self.package/name).unlink();self.save();self.rejected()

    def test_background_capture_profile_rejected(self):
        name=self.prefix+'/bin/candidate-profile.json'
        cfg=json.loads((self.package/name).read_text());cfg['background_capture']=True
        self.add(name,json.dumps(cfg));self.save();self.rejected()

    def test_wrong_runtime_version(self):
        desc=next((self.root/'var/lib/pacman/local').glob('gstreamer-*/desc'))
        desc.write_text('%NAME%\ngstreamer\n\n%VERSION%\n1.28.6-1\n');self.rejected()

    def test_existing_destination_untouched(self):
        p=self.root/self.desktop;p.parent.mkdir(parents=True);p.write_text('keep')
        self.rejected();self.assertEqual(p.read_text(),'keep')

    def test_symlink_destination_parent_does_not_write_outside(self):
        outside=self.base/'outside';outside.mkdir();(self.root/'usr/share').symlink_to(outside)
        self.rejected();self.assertEqual(list(outside.iterdir()),[])

    def test_live_root_forbidden(self):
        self.assertRaises(ValueError,installer.install,self.package,Path('/'),self.pin,True)

    def test_nested_roots_forbidden(self):
        self.assertRaises(ValueError,installer.install,self.package,self.package,self.pin,True)

    def test_copy_and_ledger_with_mocked_loader_not_native_proof(self):
        checks=[dict(binary=str(i),exit_code=0) for i in range(5)]
        with patch.object(installer.os,'geteuid',return_value=0),patch.object(installer.shutil,'which',return_value='/usr/sbin/chroot'),patch.object(installer,'verify_loader',return_value=checks):
            result=self.install(False)
        self.assertEqual(result['state'],'camera-candidate-installed-rootfs-loader-pass')
        self.assertFalse(result['default_promotion'])
        for name,row in self.manifest['files'].items():self.assertEqual(installer.sha(self.root/name),row['sha256'])
        self.assertEqual(installer.sha(self.root/installer.METADATA),self.pin)
        self.assertEqual(json.loads((self.root/installer.LEDGER).read_text()),result)

    def test_failed_loader_retains_failed_receipt_and_files(self):
        with patch.object(installer.os,'geteuid',return_value=0),patch.object(installer.shutil,'which',return_value='/usr/sbin/chroot'),patch.object(installer,'verify_loader',side_effect=ValueError('fixture ABI failure')):
            self.assertRaises(ValueError,self.install,False)
        self.assertEqual(json.loads((self.root/installer.LEDGER).read_text())['state'],'failed-retained-do-not-publish-image')
        self.assertTrue((self.root/self.prefix/'bin/snapshot').is_file())
        self.assertRaises(ValueError,self.install)

    def test_loader_uses_c_locale_and_rejects_zero_exit_undefined_symbol(self):
        (self.root/Path(installer.LEDGER).parent).mkdir(parents=True)
        q=type('Result',(),dict(returncode=0,stdout='undefined symbol: fixture',stderr=''))()
        with patch.object(installer.subprocess,'run',return_value=q) as run:
            self.assertRaises(ValueError,installer.verify_loader,self.root,['/private/app'])
        self.assertEqual(run.call_args.kwargs['env']['LC_ALL'],'C')
        self.assertTrue((self.root/Path(installer.LEDGER).parent/'loader-0.log').exists())

    def test_shell_optional_pair_fails_before_nbd_or_image_mutation(self):
        env=dict(os.environ,CAMERA_CANDIDATE_PACKAGE=str(self.package),CAMERA_CANDIDATE_MANIFEST_SHA256='')
        q=subprocess.run(['bash',str(REPO/'build_rootfs.sh')],cwd=self.base,env=env,capture_output=True,text=True)
        self.assertNotEqual(q.returncode,0)
        self.assertIn('must be supplied together',q.stderr)
        self.assertFalse((self.base/'images').exists())

    def test_shell_hook_order_and_syntax(self):
        text=(REPO/'build_rootfs.sh').read_text()
        self.assertLess(text.index('--validate-only'),text.index('modprobe nbd'))
        block=text[text.index('all() {'):]
        self.assertLess(block.index('--rootfs "$mount_dir"'),block.index('\tconfig_grub'))
        self.assertEqual(subprocess.run(['bash','-n',str(REPO/'build_rootfs.sh')],capture_output=True).returncode,0)


if __name__ == '__main__':unittest.main()

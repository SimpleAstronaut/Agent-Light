import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agent_light.config import save_atomic
from agent_light.integrations import dsh
from agent_light.desktop.resources import integration_root, plugin_root
from test_runtime import configuration


class IntegrationChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.config=self.root/'custom.json'
        self.cfg=configuration(self.root)
        save_atomic(self.config,self.cfg)
        self.launcher=self.root/'dsh-web.ps1'
        self.entry=self.root/'bin.js'
        self.entry.write_text('// synthetic host')
        self.node=self.root/'node.exe'
        self.node.write_bytes(b'fake-node')
        self.patches=[patch.object(dsh,'inspect_host',return_value={'compatible':True}),
                      patch.object(dsh,'default_path',return_value=self.root/'user/config.json')]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def preview(self):
        return dsh.preview_install(self.config,self.cfg,launcher=self.launcher,
                                   entry=self.entry,node=self.node)

    def test_clean_legacy_unicode_encoding_idempotence_and_uninstall(self):
        fixtures=Path(__file__).parent/'fixtures/dsh-launchers'
        for fixture,encoding,bom in (('clean','utf-8',b''),('legacy-unmarked','utf-16le',b'\xff\xfe')):
            with self.subTest(fixture=fixture):
                text=(fixtures/(fixture+'.ps1')).read_text(encoding='utf-8')
                self.launcher.write_bytes(bom+text.replace('\n','\r\n').encode(encoding))
                preview=self.preview()
                self.assertEqual(preview['kind'],fixture)
                self.assertIn('+',preview['diff'])
                result=dsh.install(preview,confirmed_stopped=True)
                self.assertEqual(result['status'],'installed')
                installed=dsh.decode_script(self.launcher.read_bytes())[0]
                self.assertEqual(installed.count(dsh.BEGIN),1)
                self.assertEqual(installed.count('$agentLightPatchPath ='),1)
                self.assertEqual(dsh.install(self.preview(),confirmed_stopped=True)['status'],'unchanged')
                # Preserve a user change outside the managed block.
                self.launcher.write_bytes(self.launcher.read_bytes()+('\r\n# user comment\r\n').encode(encoding))
                uninstall=dsh.preview_uninstall(self.config)
                dsh.uninstall(uninstall,confirmed_stopped=True)
                final=dsh.decode_script(self.launcher.read_bytes())[0]
                self.assertNotIn(dsh.BEGIN,final)
                self.assertIn('# user comment',final)
                self.assertTrue(Path(result['backup_path']).exists())
                self.assertTrue(Path(preview['overlay_path']).exists())

    def test_concurrent_changes_and_cross_config_ownership(self):
        self.launcher.write_bytes((dsh.TEMPLATES/'clean.ps1').read_bytes())
        preview=self.preview()
        self.launcher.write_bytes(self.launcher.read_bytes()+b'# concurrent edit\n')
        with self.assertRaisesRegex(ValueError,'INSTALLER_CONCURRENT_CHANGE'):
            dsh.install(preview,confirmed_stopped=True)
        self.launcher.write_bytes((dsh.TEMPLATES/'clean.ps1').read_bytes())
        dsh.install(self.preview(),confirmed_stopped=True)
        other=self.root/'other.json'
        save_atomic(other,self.cfg)
        self.assertNotEqual(integration_root(self.config),integration_root(other))
        with self.assertRaisesRegex(ValueError,'INTEGRATION_OWNED_BY_OTHER_CONFIG'):
            dsh.preview_install(other,self.cfg,launcher=self.launcher,entry=self.entry,node=self.node)
        self.launcher.write_bytes(self.launcher.read_bytes().replace(b'disabled: false',b'disabled: true'))
        # Changing the managed block is rejected, while unrelated content was accepted above.
        self.launcher.write_bytes(self.launcher.read_bytes().replace(b'$agentLightAlreadyIncluded = $false',b'$agentLightAlreadyIncluded = $true'))
        with self.assertRaisesRegex(ValueError,'INSTALLER_UNSUPPORTED'):
            dsh.preview_uninstall(self.config)

    def test_unknown_script_and_missing_resource_rejected(self):
        self.launcher.write_text('& dsh web @args',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'INSTALLER_UNSUPPORTED'):
            self.preview()
        incomplete=self.root/'incomplete'
        (incomplete/'dist').mkdir(parents=True)
        (incomplete/'dist/index.js').write_text('')
        with self.assertRaisesRegex(ValueError,'PLUGIN_BUILD_MISSING'):
            dsh.generate_dsh_overlay(self.cfg,incomplete)

    def test_write_failure_rolls_back_without_deleting_history(self):
        self.launcher.write_bytes((dsh.TEMPLATES/'clean.ps1').read_bytes())
        preview=self.preview()
        original=self.launcher.read_bytes()
        writer=dsh.atomic_bytes
        def fail_launcher(path,data,*args,**kwargs):
            if Path(path)==self.launcher:
                raise OSError('synthetic write failure')
            return writer(path,data,*args,**kwargs)
        with patch.object(dsh,'atomic_bytes',side_effect=fail_launcher):
            with self.assertRaises(OSError):
                dsh.install(preview,confirmed_stopped=True)
        self.assertEqual(self.launcher.read_bytes(),original)
        self.assertEqual(dsh.read_record(self.config)['status'],'detached')
        self.assertTrue((self.root/'user/backups').is_dir())

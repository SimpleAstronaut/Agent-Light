import tempfile
from unittest.mock import patch, PropertyMock
from agent_light.serial_link import SerialWorker
from pathlib import Path

from aiohttp.test_utils import AioHTTPTestCase
from agent_light.api import application
from agent_light.config import load, save_atomic
from test_runtime import configuration


class DisplayAPIChecks(AioHTTPTestCase):
    async def get_application(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cfg = configuration(root)
        self.path = root / 'custom-config.json'
        save_atomic(self.path, self.cfg)
        self.headers = {'Authorization': 'Bearer test-token'}
        return application(self.cfg, config_path=self.path)

    async def tearDownAsync(self):
        await super().tearDownAsync()
        self.tmp.cleanup()

    async def test_display_save_validation_and_external_edit(self):
        response = await self.client.patch('/v1/config/display', json={'brightness': 55}, headers=self.headers)
        self.assertEqual(response.status, 200)
        result = await response.json()
        self.assertTrue(result['configuration_saved'])
        self.assertTrue(result['backend_applied'])
        self.assertNotIn('device_confirmed', result)
        self.assertEqual(load(self.path)['brightness'], 55)
        self.assertEqual(load(self.path)['tokenFile'], self.cfg['tokenFile'])
        for payload in ({'brightness': True}, {'database': 'elsewhere'}, {}):
            response = await self.client.patch('/v1/config/display', json=payload, headers=self.headers)
            self.assertEqual(response.status, 422)
            self.assertIn('error', await response.json())
        self.path.write_text(self.path.read_text() + ' ')
        response = await self.client.patch('/v1/config/display', json={'brightness': 60}, headers=self.headers)
        self.assertEqual(response.status, 409)
        self.assertEqual((await response.json())['error']['code'], 'CONFIG_CHANGED_EXTERNALLY')
        response = await self.client.get('/v1/config/display', headers=self.headers)
        self.assertEqual((await response.json())['brightness'], 55)

    async def test_display_update_rejected_during_test(self):
        response = await self.client.post('/v1/display/test', json={}, headers=self.headers)
        self.assertEqual(response.status, 409)
        self.assertEqual((await response.json())['error']['code'], 'DEVICE_NOT_READY')
        with patch.object(SerialWorker, 'test_running', new_callable=PropertyMock, return_value=True):
            response = await self.client.patch('/v1/config/display', json={'brightness': 55}, headers=self.headers)
        self.assertEqual(response.status, 409)
        self.assertEqual((await response.json())['error']['code'], 'DISPLAY_TEST_RUNNING')
        self.assertEqual(load(self.path)['brightness'], 35)

    async def test_device_selection_identity_and_disconnect(self):
        rows=[dict(port='COM_TEST',description='Synthetic',manufacturer=None,vid=0x0483,
                   pid=0x5740,serial_number='SERIAL_TEST',matched=True)]
        with patch('agent_light.devices.scan_devices',return_value=rows), \
             patch.object(SerialWorker,'open',side_effect=OSError('DEVICE_NOT_FOUND')):
            response=await self.client.get('/v1/devices',headers=self.headers)
            self.assertEqual((await response.json())['devices'],rows)
            response=await self.client.post('/v1/device/connect',headers=self.headers,
                json={'mode':'manual','port':'COM_TEST','serial_number':'WRONG'})
            self.assertEqual(response.status,409)
            self.assertIsNone(load(self.path)['port'])
            response=await self.client.post('/v1/device/connect',headers=self.headers,
                json={'mode':'manual','port':'COM_TEST','serial_number':'SERIAL_TEST'})
            self.assertEqual(response.status,202)
            self.assertNotIn('connected',await response.json())
            self.assertEqual(load(self.path)['port'],'COM_TEST')
            response=await self.client.post('/v1/device/disconnect',headers=self.headers,json={})
            self.assertEqual(response.status,202)


class MissingConfigPathChecks(DisplayAPIChecks):
    async def get_application(self):
        await super().get_application()
        return application(self.cfg)

    # One focused check; do not inherit the write-path cases.
    test_display_save_validation_and_external_edit = None
    test_display_update_rejected_during_test = None
    test_device_selection_identity_and_disconnect = None

    async def test_write_requires_explicit_path(self):
        response = await self.client.patch('/v1/config/display', json={'brightness': 55}, headers=self.headers)
        self.assertEqual(response.status, 503)
        self.assertEqual((await response.json())['error']['code'], 'CONFIG_PATH_REQUIRED')

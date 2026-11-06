import tempfile
import unittest
from pathlib import Path
from aiohttp.test_utils import AioHTTPTestCase
from agent_light.api import application


class HTTPChecks(AioHTTPTestCase):
    async def get_application(self):
        self.tmp=tempfile.TemporaryDirectory()
        p=Path(self.tmp.name)
        (p/'token').write_text('test-token')
        return application(dict(tokenFile=str(p/'token'),database=str(p/'db'),brightness=35,
            completedHoldSeconds=300,vid=0x0483,pid=0x5740,port=None,serialNumber='no-such-device'))

    async def tearDownAsync(self):
        await super().tearDownAsync()
        self.tmp.cleanup()

    async def test_auth_strict_body_and_final_duplicate(self):
        self.assertEqual((await self.client.get('/v1/health')).status,401)
        headers={'Authorization':'Bearer test-token'}
        response=await self.client.get('/v1/health',headers=headers)
        self.assertEqual(response.status,200)
        self.assertEqual((await response.json())['sources']['codex'],'reserved')
        e=dict(schema_version=1,event_id='e',agent='dsh',producer_id='p',runtime_id='r',runtime_seq=1,
               producer_seq=1,type='runtime_ready',live_instances=[])
        response=await self.client.post('/v1/events',json=e,headers=headers)
        self.assertEqual((await response.json())['status'],'applied')
        response=await self.client.post('/v1/events',json=e,headers=headers)
        self.assertEqual((await response.json())['status'],'duplicate')
        response=await self.client.post('/v1/events',json=e|{'prompt':'CANARY'},headers=headers)
        self.assertEqual(response.status,422)
        response=await self.client.post('/v1/events',json=e|{'live_instances':['unknown']},headers=headers)
        self.assertEqual(response.status,409)


if __name__=='__main__':unittest.main()

import json
import tempfile
import time
import unittest
from pathlib import Path
from agent_light.core import Store, SourceError


class SourceManagementChecks(unittest.TestCase):
    def test_disable_persists_and_requires_new_runtime_barrier_and_heartbeat(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.db'
            store = Store(path)
            barrier = dict(schema_version=1, event_id='e1', agent='dsh', producer_id='p',
                runtime_id='r1', runtime_seq=1, producer_seq=1, type='runtime_ready', live_instances=[])
            heartbeat = dict(agent='dsh',producer_id='p',runtime_id='r1',runtime_seq=1,
                             health='healthy',persisted_seq=1,acked_seq=1)
            request = dict(agent='dsh',producer_id='p',expected_generation=0,confirm=True)
            try:
                store.apply(barrier)
                store.heartbeat(heartbeat)
                key = store.source_key(heartbeat)
                with self.assertRaisesRegex(SourceError, 'PRODUCER_STILL_REPORTING'):
                    store.manage_source(request, False)
                store.leases[key] = time.monotonic() - 16
                self.assertEqual(store.tick()[0], 'ERROR')
                store.manage_source(request, False)
                self.assertEqual(store.tick()[0], 'IDLE')
                self.assertEqual(store.apply(barrier)['status'], 'duplicate')
                with self.assertRaisesRegex(SourceError, 'PRODUCER_DISABLED'):
                    store.heartbeat(heartbeat)
                with self.assertRaisesRegex(SourceError, 'SOURCE_STATE_CHANGED'):
                    store.manage_source(request, True)
            finally:
                store.db.close()
            store = Store(path)
            try:
                self.assertEqual(store.management(key)['mode'], 'disabled')
                self.assertFalse(store.last_heartbeat_at)
                result = store.manage_source({**request,'expected_generation':1}, True)
                self.assertTrue(result['restart_required'])
                store.heartbeat(heartbeat)
                self.assertEqual(store.tick()[0], 'ERROR')
                store.apply({**barrier,'event_id':'e2','producer_seq':2,'runtime_id':'r2','runtime_seq':2})
                self.assertEqual(store.management(key)['mode'], 'activation_pending')
                store.heartbeat({**heartbeat,'runtime_id':'r2','runtime_seq':2})
                self.assertEqual(store.management(key)['mode'], 'enabled')
                self.assertEqual(store.tick()[0], 'IDLE')
                latest = store.last_heartbeat_at[key]
                store.heartbeat(heartbeat)
                self.assertEqual(store.last_heartbeat_at[key], latest)
            finally:
                store.db.close()

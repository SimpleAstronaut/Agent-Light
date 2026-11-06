import copy
import json
import tempfile
import unittest
from pathlib import Path
from agent_light.core import Store, Conflict
from agent_light.protocol import encode, decode


class CoreChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / 'test.db'))
        self.n = 0

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def event(self, kind, turn=1, **kw):
        self.n += 1
        e = dict(schema_version=1,event_id=f'e{self.n}',agent='dsh',channel='plugin',producer_id='p',
            runtime_id='r',runtime_seq=1,producer_seq=self.n,session_id='s',instance_id='i',instance_seq=1,
            turn_id=f't{turn}' if turn else None,turn_seq=turn,attention_id=None,type=kind,
            occurred_at='2026-11-06T00:00:00Z',reason_code=None)
        return e | kw

    def start(self):
        self.store.apply(self.event('session_start',0))
        self.n += 1
        ready=dict(schema_version=1,event_id=f'e{self.n}',agent='dsh',producer_id='p',
            runtime_id='r',runtime_seq=1,producer_seq=self.n,type='runtime_ready',live_instances=['i'])
        self.store.apply(ready)
        self.store.heartbeat(dict(agent='dsh',producer_id='p',runtime_id='r',runtime_seq=1,health='healthy',persisted_seq=self.n,acked_seq=self.n))
        return ready

    def state(self):
        return self.store.aggregate()[0]

    def test_wait_survives_cancel_and_new_turn_until_exact_resolve(self):
        self.start()
        self.store.apply(self.event('turn_start'))
        self.store.apply(self.event('attention_open',attention_id='question:a'))
        self.store.apply(self.event('turn_cancelled'))
        self.assertEqual(self.state(),'ATTENTION')
        self.store.apply(self.event('turn_start',2))
        self.store.apply(self.event('attention_resolve',attention_id='question:b'))
        self.assertEqual(self.state(),'ATTENTION')
        self.store.apply(self.event('attention_resolve',attention_id='question:a'))
        self.assertEqual(self.state(),'RUNNING')
        self.store.apply(self.event('attention_open',attention_id='question:a'))
        self.assertEqual(self.state(),'RUNNING')

    def test_dedupe_conflict_deadline_and_error_monotonic(self):
        self.start()
        self.store.apply(self.event('turn_start'))
        complete=self.event('turn_complete')
        self.store.apply(complete)
        deadline=next(iter(self.store.s['sessions'].values()))['deadline']
        self.assertEqual(self.store.apply(complete)['status'],'duplicate')
        self.assertEqual(next(iter(self.store.s['sessions'].values()))['deadline'],deadline)
        with self.assertRaises(Conflict):
            self.store.apply(complete | {'reason_code':'turn_failed'})
        self.store.apply(self.event('error'))
        self.store.apply(self.event('turn_complete'))
        self.assertEqual(self.state(),'ERROR')
        self.store.apply(self.event('turn_start',2))
        self.assertEqual(self.state(),'RUNNING')

    def test_source_isolation_runtime_handover_and_pending(self):
        pending=self.event('turn_start')
        self.assertEqual(self.store.apply(pending)['status'],'pending_identity')
        initial_ready=self.start()
        self.assertEqual(self.store.apply(pending)['status'],'applied')
        self.assertEqual(self.store.apply(initial_ready)['status'],'applied')
        self.store.apply(self.event('error',agent='codex')) # no Codex identity: pending, no session collision
        self.assertEqual(len(self.store.s['sessions']),1)
        self.n+=1
        ready=dict(schema_version=1,event_id=f'e{self.n}',agent='dsh',producer_id='p',runtime_id='r2',runtime_seq=2,
                   producer_seq=self.n,type='runtime_ready',live_instances=[])
        self.store.apply(ready)
        self.store.heartbeat(dict(agent='dsh',producer_id='p',runtime_id='r2',runtime_seq=2,health='healthy',persisted_seq=self.n,acked_seq=self.n))
        # Codex's pending source remains recovering; a DSH barrier must not clear its fault.
        self.assertEqual(self.state(),'ERROR')
        self.assertTrue(next(iter(self.store.s['sessions'].values()))['retired'])
        self.assertEqual(self.store.apply(self.event('error'))['status'],'stale')

    def test_payload_privacy_and_usb_vectors(self):
        from jsonschema import ValidationError
        with self.assertRaises(ValidationError):
            self.store.apply(self.event('turn_start',prompt='CANARY'))
        root=Path(__file__).resolve().parents[2]
        vectors=json.loads((root/'contracts/usb-vectors.json').read_text())['vectors']
        for v in vectors:
            raw=bytes.fromhex(v['raw'])
            if v['name'] in ('bad_crc_silent','truncated_silent','structural_length_silent'):
                with self.assertRaises(ValueError):decode(bytes.fromhex(v['wire']))
            elif raw[0]==1:
                kind,seq,payload=decode(bytes.fromhex(v['wire']))
                self.assertEqual(encode(kind,seq,payload).hex(),v['wire'])


if __name__=='__main__': unittest.main()

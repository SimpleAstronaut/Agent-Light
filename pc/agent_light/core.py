import json
import sqlite3
import time
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = json.loads(Path(__file__).with_name("event-schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
PRIORITY = {"IDLE": 0, "COMPLETED": 1, "RUNNING": 2, "ATTENTION": 3, "ERROR": 4}


class Conflict(Exception):
    pass


class Store:
    def __init__(self, path, hold=300, brightness=35):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("CREATE TABLE IF NOT EXISTS inbox(k TEXT PRIMARY KEY, body TEXT, status TEXT);"
                              "CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY, body TEXT);")
        row = self.db.execute("SELECT body FROM state WHERE id=1").fetchone()
        self.s = json.loads(row[0]) if row else dict(sources={}, sessions={}, desired="IDLE", revision=0)
        self.hold, self.brightness = hold, brightness
        self.leases = {k: time.monotonic() for k in self.s['sources']}

    def persist(self):
        self.db.execute("INSERT OR REPLACE INTO state VALUES(1,?)", (json.dumps(self.s),))

    def apply(self, e):
        VALIDATOR.validate(e)
        if len(json.dumps(e).encode()) > (65536 if e['type'] == 'runtime_ready' else 2048):
            raise ValueError("EVENT_TOO_LARGE")
        key = json.dumps([e['agent'], e['producer_id'], e['event_id']])
        body = json.dumps(e, sort_keys=True, separators=(',', ':'))
        old = self.db.execute("SELECT body,status FROM inbox WHERE k=?", (key,)).fetchone()
        if old:
            if old[0] != body:
                raise Conflict()
            if old[1] != 'pending_identity':
                return dict(event_id=e['event_id'], status='duplicate')
        # Roll back the in-memory snapshot together with SQLite on unexpected errors.
        snapshot = json.dumps(self.s)
        try:
            with self.db:
                status = self.reduce(e)
                self.aggregate()
                self.db.execute("INSERT OR REPLACE INTO inbox VALUES(?,?,?)", (key, body, status))
                self.persist()
        except Exception:
            self.s = json.loads(snapshot)
            raise
        return dict(event_id=e['event_id'], status=status)

    def source_key(self, e):
        return json.dumps([e['agent'], e['producer_id']])

    def reduce(self, e):
        sk = self.source_key(e)
        src = self.s['sources'].setdefault(sk, dict(runtime_seq=-1, runtime_id=None, ready_seq=-1,
                                                    ready_id=None, health='recovering', last_seq=0))
        self.leases.setdefault(sk, time.monotonic())
        r, t = e['runtime_seq'], e['type']
        if r < src['ready_seq'] or (r == src['ready_seq'] and src['ready_id'] != e['runtime_id']):
            return 'stale'
        if t == 'runtime_ready':
            live = [v for v in self.s['sessions'].values() if v['source'] == sk and v['runtime_id'] == e['runtime_id']]
            if not set(e['live_instances']).issubset({v['instance_id'] for v in live}):
                return 'pending_identity'
            # FIFO barrier cannot overtake pending records.
            for (pending,) in self.db.execute("SELECT body FROM inbox WHERE status='pending_identity'"):
                p = json.loads(pending)
                if self.source_key(p) == sk and p['producer_seq'] < e['producer_seq']:
                    return 'pending_identity'
            src.update(ready_seq=r, ready_id=e['runtime_id'])
            for v in self.s['sessions'].values():
                if v['source'] == sk and (v['runtime_id'] != e['runtime_id'] or v['instance_id'] not in e['live_instances']):
                    v['retired'] = True
            return 'applied'
        k = json.dumps([e['agent'], e['producer_id'], e['session_id']])
        v = self.s['sessions'].get(k)
        if t == 'session_start':
            if v and e['instance_seq'] <= v['instance_seq']:
                return 'stale'
            self.s['sessions'][k] = dict(source=sk, runtime_id=e['runtime_id'], instance_id=e['instance_id'],
                instance_seq=e['instance_seq'], turn_seq=0, turn_id=None, base='IDLE', waits={}, resolved=[],
                deadline=0, retired=False, closed=False)
            return 'applied'
        if not v or e['instance_seq'] > v['instance_seq']:
            return 'pending_identity'
        if e['instance_id'] != v['instance_id'] or e['runtime_id'] != v['runtime_id'] or v['retired'] or v['closed']:
            return 'stale'
        attention = json.dumps([e['attention_id'], e['turn_seq'], e['turn_id']])
        if t == 'attention_resolve':
            v['waits'].pop(attention, None)
            if attention not in v['resolved']:
                v['resolved'].append(attention)
            return 'applied'
        if t == 'session_end':
            v.update(waits={}, closed=True)
            if e['outcome'] == 'abnormal':
                v['base'] = 'ERROR'
            elif v['base'] != 'ERROR':
                v['base'] = 'IDLE'
            return 'applied'
        n = e['turn_seq']
        if t == 'turn_start' and n > v['turn_seq']:
            v.update(turn_seq=n, turn_id=e['turn_id'], base='RUNNING', deadline=0)
        elif t == 'attention_open':
            if n != v['turn_seq'] or (n and e['turn_id'] != v['turn_id']):
                return 'stale'
            if attention not in v['resolved']:
                v['waits'][attention] = True
        elif n != v['turn_seq'] or e['turn_id'] != v['turn_id']:
            return 'stale'
        elif t in ('error', 'turn_complete', 'turn_cancelled'):
            new = {'error': 'ERROR', 'turn_complete': 'COMPLETED', 'turn_cancelled': 'CANCELLED'}[t]
            ranks = {'IDLE': 0, 'RUNNING': 0, 'CANCELLED': 1, 'COMPLETED': 2, 'ERROR': 3}
            if ranks[new] > ranks[v['base']]:
                v['base'] = new
                if new == 'COMPLETED':
                    v['deadline'] = time.time() + self.hold
        return 'applied'

    def heartbeat(self, e):
        allowed = {'agent','producer_id','runtime_id','runtime_seq','health','persisted_seq','acked_seq'}
        if set(e) != allowed or e['agent'] not in ('dsh','codex') or e['health'] not in ('healthy','recovering','degraded'):
            raise ValueError('HEARTBEAT_SCHEMA')
        for k in ('producer_id','runtime_id'):
            if not isinstance(e[k], str) or not 1 <= len(e[k]) <= 128 or not e[k].isascii():
                raise ValueError('HEARTBEAT_ID')
        for k in ('runtime_seq','persisted_seq','acked_seq'):
            if type(e[k]) is not int or not 0 <= e[k] <= 9007199254740991:
                raise ValueError('HEARTBEAT_SEQ')
        sk = self.source_key(e)
        with self.db:
            src = self.s['sources'].setdefault(sk, dict(runtime_seq=-1, ready_seq=-1, ready_id=None))
            if e['runtime_seq'] < src['runtime_seq']:
                return
            if e['runtime_seq'] == src['runtime_seq'] and src.get('runtime_id') != e['runtime_id']:
                raise ValueError('RUNTIME_CONFLICT')
            src.update(runtime_seq=e['runtime_seq'], runtime_id=e['runtime_id'],
                       health=e['health'] if (e['runtime_seq']==src['ready_seq'] and e['runtime_id']==src['ready_id']) or e['health']=='degraded' else 'recovering',
                       persisted_seq=e['persisted_seq'], acked_seq=e['acked_seq'])
            self.leases[sk] = time.monotonic()
            self.aggregate()
            self.persist()

    def aggregate(self):
        states = ['IDLE']
        for sk, src in self.s['sources'].items():
            if src.get('health') != 'healthy' or time.monotonic() - self.leases.get(sk, 0) > 15:
                states.append('ERROR')
        for v in self.s['sessions'].values():
            if v['retired']:
                continue
            state = v['base']
            if state == 'CANCELLED' or (state == 'COMPLETED' and time.time() >= v['deadline']):
                state = 'IDLE'
            states.append('ERROR' if state == 'ERROR' else 'ATTENTION' if v['waits'] else state)
        desired = max(states, key=PRIORITY.get)
        if desired != self.s['desired']:
            self.s.update(desired=desired, revision=(self.s['revision'] + 1) & 0xffffffff)
        return self.s['desired'], self.s['revision']

    def tick(self):
        previous = self.s['revision']
        result = self.aggregate()
        if self.s['revision'] != previous:
            with self.db:
                self.persist()
        return result

    def clear(self):
        with self.db:
            for v in self.s['sessions'].values():
                if v['base'] in ('ERROR','COMPLETED'):
                    v['base'] = 'IDLE'
            self.aggregate()
            self.persist()

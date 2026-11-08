import asyncio
import copy
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from agent_light.core import Store
from agent_light.protocol import encode, decode
from agent_light.serial_link import SerialWorker
from agent_light.config import ConfigError
from test_runtime import configuration


class FakePort:
    port = 'COM_TEST'
    def __init__(self):
        self.buffer = bytearray()
        self.mode, self.state, self.revision, self.brightness = 1, 0, 0, 35
        self.closed = False
        self.sets = []

    def write(self, data):
        command, seq, payload = decode(data)
        if command == 1:
            self.revision, self.state, self.brightness = struct.unpack('<IBB', payload)
            self.mode = 2
            self.sets.append((time.monotonic(), self.state, self.revision))
            response = encode(0x81, seq, b'\x01\x00' + payload[:4] + b'\x01')
        else:
            response = encode(0x83, seq, struct.pack('<BBIBBBHIH', self.mode, self.state,
                self.revision, int(self.mode == 2), self.brightness, seq, 0x0100, 10, 0))
        self.buffer.extend(response)

    def read(self, count):
        data = bytes(self.buffer[:count])
        del self.buffer[:count]
        return data

    def close(self):
        self.closed = True


async def until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError('condition timed out')
        await asyncio.sleep(.02)


class SerialChecks(unittest.IsolatedAsyncioTestCase):
    async def test_ack_stages_restore_latest_and_disconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = configuration(Path(directory))
            store = Store(cfg['database'])
            link = SerialWorker(cfg, store)
            port = FakePort()
            with patch.object(link, 'open', return_value=port):
                task = asyncio.create_task(link.run())
                try:
                    await until(lambda: link.confirmed)
                    before = copy.deepcopy(store.s['sessions'])
                    test_id = link.start_test()
                    self.assertTrue(test_id)
                    with self.assertRaisesRegex(ConfigError, 'DISPLAY_TEST_RUNNING'):
                        link.start_test()
                    # Concurrent business changes must determine the eventual restoration.
                    store.s['sources']['["dsh", "p"]'] = dict(health='degraded')
                    await until(lambda: link.display_test['state'] == 'succeeded', 6)
                    results = link.display_test['stage_results']
                    self.assertEqual([r['stage'] for r in results], ['red','yellow','green','restoring'])
                    self.assertTrue(all(r['acked_at'] for r in results))
                    self.assertTrue(all(r['held_until'] for r in results[:3]))
                    stages = port.sets[-4:]
                    self.assertEqual([s[1] for s in stages], [2,1,4,3])
                    for a, b in zip(stages, stages[1:]):
                        self.assertGreaterEqual(b[0] - a[0], 1)
                    self.assertEqual(store.s['sessions'], before)
                    await until(lambda: link.confirmed)
                    link.start_test()
                    link.disconnect()
                    self.assertFalse(link.confirmed)
                    self.assertEqual(link.display_test['error'], 'DEVICE_DISCONNECTED')
                    await until(lambda: link.state == 'DISABLED')
                    self.assertTrue(port.closed)
                    self.assertIsNone(link.acked_revision)
                finally:
                    link.request_stop()
                    await task
                    store.db.close()

    async def test_unready_test_and_freshness(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = configuration(Path(directory))
            store = Store(cfg['database'])
            link = SerialWorker(cfg, store)
            with self.assertRaisesRegex(ConfigError, 'DEVICE_NOT_READY'):
                link.start_test()
            port = FakePort()
            with patch.object(link, 'open', return_value=port):
                task = asyncio.create_task(link.run())
                try:
                    await until(lambda: link.confirmed)
                    link._status_mono -= 3
                    self.assertFalse(link.confirmed)
                finally:
                    link.request_stop()
                    await task
                    store.db.close()

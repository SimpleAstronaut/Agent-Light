import asyncio
import json
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from agent_light.api import application
from agent_light.config import ConfigError, ConfigRepository, save_atomic, validate_config
from agent_light.core import Store
from agent_light.locking import ProcessLock
from agent_light.runtime import ServiceRuntime
from agent_light.serial_link import SerialWorker


def configuration(root):
    (root / 'token').write_text('test-token')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    return dict(endpoint=f'http://127.0.0.1:{port}', tokenFile=str(root / 'token'),
                database=str(root / 'state.db'), dataDir=str(root / 'outbox'),
                brightness=35, completedHoldSeconds=300, vid=0x0483, pid=0x5740,
                port=None, serialNumber='no-such-device')


class RuntimeChecks(unittest.TestCase):
    def test_thread_start_stop_and_fresh_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = configuration(root)
            path = root / 'custom.json'
            save_atomic(path, cfg)
            for _ in range(2):
                runtime = ServiceRuntime(cfg, config_path=path)
                runtime.start()
                deadline = time.monotonic() + 4
                while runtime.state == 'STARTING' and time.monotonic() < deadline:
                    time.sleep(.01)
                try:
                    self.assertTrue(runtime.is_running(), runtime.startup_error)
                    runtime.start()  # No replacement thread.
                finally:
                    runtime.request_stop()
                    runtime.request_stop()
                    self.assertTrue(runtime.wait_stopped(4))
                self.assertEqual(runtime.state, 'STOPPED')
                with self.assertRaisesRegex(RuntimeError, 'RUNTIME_NOT_REUSABLE'):
                    runtime.start()

    def test_bind_failure_releases_database_and_lock(self):
        with tempfile.TemporaryDirectory() as directory, socket.socket() as occupied:
            root = Path(directory)
            cfg = configuration(root)
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            cfg['endpoint'] = f'http://127.0.0.1:{occupied.getsockname()[1]}'
            runtime = ServiceRuntime(cfg, config_path=None)
            runtime.start()
            self.assertTrue(runtime.wait_stopped(4))
            self.assertEqual(runtime.startup_error, {'code': 'ENDPOINT_IN_USE'})
            ProcessLock(cfg['database'] + '.lock').close()
            Path(cfg['database']).unlink()  # Windows refuses deletion of an open SQLite handle.

    def test_stop_before_start_and_immediate_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = configuration(Path(directory))
            runtime = ServiceRuntime(cfg, config_path=None)
            runtime.request_stop()
            self.assertTrue(runtime.wait_stopped(0))
            runtime = ServiceRuntime(cfg, config_path=None)
            runtime.start()
            runtime.request_stop()
            self.assertTrue(runtime.wait_stopped(4))
            self.assertEqual(runtime.state, 'STOPPED')


class OwnershipChecks(unittest.IsolatedAsyncioTestCase):
    async def test_lock_conflict_does_not_construct_store(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = configuration(Path(directory))
            lock = ProcessLock(cfg['database'] + '.lock')
            runner = web.AppRunner(application(cfg))
            try:
                with patch('agent_light.api.Store') as constructor:
                    with self.assertRaisesRegex(RuntimeError, 'SERVICE_ALREADY_RUNNING'):
                        await runner.setup()
                    constructor.assert_not_called()
            finally:
                await runner.cleanup()
                lock.close()

    async def test_missing_token_releases_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = configuration(Path(directory))
            Path(cfg['tokenFile']).unlink()
            runner = web.AppRunner(application(cfg))
            with self.assertRaises(FileNotFoundError):
                await runner.setup()
            await runner.cleanup()
            ProcessLock(cfg['database'] + '.lock').close()

    async def test_late_open_is_closed_before_worker_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = configuration(Path(directory))
            store = Store(cfg['database'])
            link = SerialWorker(cfg, store)
            started, release = threading.Event(), threading.Event()
            class Port:
                closed = False
                def close(self):
                    self.closed = True
            port = Port()
            def slow_open(cfg):
                started.set()
                release.wait(3)
                return port
            with patch.object(link, 'open', slow_open):
                task = asyncio.create_task(link.run())
                try:
                    self.assertTrue(await asyncio.to_thread(started.wait, 2))
                    link.request_stop()
                    self.assertFalse(task.done())
                    release.set()
                    await asyncio.wait_for(task, 3)
                    self.assertTrue(port.closed)
                    self.assertIsNone(link.port)
                finally:
                    release.set()
                    link.request_stop()
                    await task
                    store.db.close()

    async def test_config_merge_cancel_external_edit_and_save_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = configuration(root)
            path = root / 'custom.json'
            save_atomic(path, cfg)
            repo = ConfigRepository(path, cfg)
            published = {}
            async def update(values):
                return await repo.update(values, allowed=('brightness', 'completedHoldSeconds'),
                                         publish=published.update)
            await asyncio.gather(update({'brightness': 50}), update({'completedHoldSeconds': 60}))
            self.assertEqual((published['brightness'], published['completedHoldSeconds']), (50, 60))
            with patch('agent_light.config.save_atomic', side_effect=OSError('disk full')):
                with self.assertRaisesRegex(ConfigError, 'CONFIG_SAVE_FAILED'):
                    await update({'brightness': 80})
            self.assertEqual(repo.cfg['brightness'], 50)
            original_save = save_atomic
            entered, release = threading.Event(), threading.Event()
            def slow_save(*args, **kwargs):
                entered.set()
                release.wait(3)
                return original_save(*args, **kwargs)
            with patch('agent_light.config.save_atomic', slow_save):
                request = asyncio.create_task(update({'brightness': 70}))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    request.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await request
                finally:
                    release.set()
                    await repo.close()
            self.assertEqual(json.loads(path.read_text())['brightness'], 70)
            self.assertEqual(published['brightness'], 70)
            repo.stopping = False
            path.write_text(path.read_text() + ' ')
            with self.assertRaisesRegex(ConfigError, 'CONFIG_CHANGED_EXTERNALLY'):
                await update({'brightness': 90})
            self.assertEqual(published['brightness'], 70)

    async def test_store_partial_initialization_closes_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.db'
            db = sqlite3.connect(path)
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY, body TEXT)')
            db.execute("INSERT INTO state VALUES(1, 'invalid-json')")
            db.commit()
            db.close()
            with self.assertRaises(ValueError):
                Store(path)
            path.unlink()


class ValidationChecks(unittest.TestCase):
    def test_reject_bool_and_non_loopback(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = configuration(Path(directory))
            for patch_values in ({'brightness': True}, {'completedHoldSeconds': False},
                                 {'brightness': 19}, {'completedHoldSeconds': -1},
                                 {'endpoint': 'http://0.0.0.0:17321'}):
                with self.subTest(patch=patch_values), self.assertRaises(ConfigError):
                    validate_config(cfg | patch_values)

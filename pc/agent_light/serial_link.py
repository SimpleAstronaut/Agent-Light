import asyncio
import copy
import struct
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import serial
from serial.tools import list_ports
from .protocol import encode, decode
from .config import ConfigError
from .core import utc_now

STATES = {'IDLE': 0, 'RUNNING': 1, 'ATTENTION': 2, 'ERROR': 3, 'COMPLETED': 4}


class SerialWorker:
    def __init__(self, cfg, store):
        self.cfg, self.store = cfg, store
        self.seq = 0
        self.port = None
        self.enabled = True
        self.state = 'DISCONNECTED'
        self.connection_generation = 0
        self.connected = False
        self.acked_revision = None
        self.diagnostic = 'DISCONNECTED'
        self.last_error = None
        self.selected_port = cfg.get('port')
        self.last_device_status = None
        self.last_status_at = None
        self._status_mono = 0
        self._sent = None
        self._target_pending = True
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._controls = asyncio.Queue(maxsize=8)
        self._reserved = 0
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='agent-light-serial')
        self.display_test = dict(test_id=None, state='idle', stage='none', started_at=None,
                                 finished_at=None, error=None, stage_results=[])
        self._stage_deadline = None
        self._stage_sent = False

    @property
    def test_running(self):
        return self.display_test['state'] == 'running'

    @property
    def confirmed(self):
        status = self.last_device_status or {}
        target = self._desired()
        return bool(self.connected and self.diagnostic == 'OK' and self._sent == target
            and not self._target_pending and self.acked_revision is not None
            and status.get('mode') == 'ACTIVE' and status.get('revision_valid')
            and status.get('display_revision') == self.acked_revision
            and status.get('applied_state') == self._sent[0]
            and status.get('brightness_pct') == self._sent[1]
            and time.monotonic() - self._status_mono <= 2.5)

    def snapshot(self):
        return dict(enabled=self.enabled, state=self.state, connection_generation=self.connection_generation,
            connected=self.connected, confirmed=self.confirmed, selected_port=self.selected_port,
            serial_number=self.cfg.get('serialNumber'), diagnostic=self.diagnostic, last_error=self.last_error,
            acked_revision=self.acked_revision, last_status_at=self.last_status_at,
            **(self.last_device_status or {}))

    def reserve_control(self):
        if self._controls.qsize() + self._reserved >= self._controls.maxsize:
            raise ConfigError('DEVICE_BUSY')
        self._reserved += 1
        released = False
        def release():
            nonlocal released
            if not released:
                released = True
                self._reserved -= 1
        return release

    def _invalidate(self, reason):
        self.connection_generation += 1
        self.connected = False
        self.acked_revision = None
        self.last_device_status = None
        self.last_status_at = None
        self._status_mono = 0
        self._sent = None
        self._target_pending = True
        self._fail_test(reason)

    def connect(self, cfg):
        self._invalidate('DEVICE_RECONFIGURED')
        self.enabled = True
        self.state, self.diagnostic = 'DISCONNECTING', 'DEVICE_RECONFIGURED'
        self._controls.put_nowait((self.connection_generation, dict(cfg)))
        self._wake.set()

    def disconnect(self):
        self._invalidate('DEVICE_DISCONNECTED')
        self.enabled = False
        self.state, self.diagnostic = 'DISCONNECTING', 'DEVICE_DISCONNECTED'
        self._controls.put_nowait((self.connection_generation, None))
        self._wake.set()

    def start_test(self):
        if self.test_running:
            raise ConfigError('DISPLAY_TEST_RUNNING')
        if not self.confirmed:
            raise ConfigError('DEVICE_NOT_READY')
        test_id = str(uuid.uuid4())
        self.display_test = dict(test_id=test_id, state='running', stage='red', started_at=utc_now(),
                                 finished_at=None, error=None, stage_results=[])
        self._stage_deadline = None
        self._stage_sent = False
        self._target_pending = True
        self._wake.set()
        return test_id

    def _fail_test(self, reason):
        if self.test_running:
            self.display_test.update(state='failed', error=reason, finished_at=utc_now())
            results = self.display_test['stage_results']
            if results and results[-1]['acked_at'] is None:
                results[-1]['error'] = reason
        self._stage_sent = False

    def _desired(self):
        if self.test_running and self.display_test['stage'] != 'restoring':
            return ({'red':'ATTENTION','yellow':'RUNNING','green':'COMPLETED'}[self.display_test['stage']], self.cfg['brightness'])
        return (self.store.s['desired'], self.cfg['brightness'])

    @staticmethod
    def transaction(port, seq, command, payload=b''):
        request_seq = seq
        request = encode(command, seq, payload)
        for _ in range(3):
            port.write(request)
            deadline, buf = time.monotonic() + .1, bytearray()
            while time.monotonic() < deadline:
                b = port.read(1)
                if not b:
                    continue
                buf.extend(b)
                if len(buf) > 40:
                    # Discard through delimiter, then resynchronize.
                    while b != b'\0' and time.monotonic() < deadline:
                        b = port.read(1)
                    buf.clear()
                    continue
                if b != b'\0':
                    continue
                try:
                    kind, seq, data = decode(bytes(buf))
                except ValueError:
                    buf.clear()
                    continue
                buf.clear()
                if seq != request_seq:
                    continue
                if kind == 0x82 and len(data) == 2 and data[0] == command:
                    raise OSError('DEVICE_NACK_' + str(data[1]))
                if command == 3 and kind == 0x83 and len(data) == 17:
                    return data
                expected = 7 if command == 1 else 6
                if kind == 0x81 and len(data) == expected and data[:2] == bytes([command, 0]):
                    if command == 1 and data[2:6] != payload[:4]:
                        continue
                    return data
        raise OSError('ACK_TIMEOUT')

    @staticmethod
    def open(cfg):
        ports = list(list_ports.comports())
        candidates = [p.device for p in ports
                      if p.vid == cfg['vid'] and p.pid == cfg['pid']
                      and (not cfg.get('serialNumber') or p.serial_number == cfg['serialNumber'])]
        name = cfg.get('port')
        if name and cfg.get('serialNumber') and not any(p.device == name and p.serial_number == cfg['serialNumber'] for p in ports):
            raise OSError('DEVICE_IDENTITY_MISMATCH')
        if not name:
            if len(candidates) != 1:
                raise OSError('DEVICE_NOT_UNIQUE' if candidates else 'DEVICE_NOT_FOUND')
            name = candidates[0]
        port = serial.Serial(name, 115200, timeout=.01, write_timeout=.1)
        try:
            port.reset_input_buffer()
            return port
        except BaseException:
            port.close()
            raise

    def request_stop(self):
        self._invalidate('SERVICE_STOPPING')
        self._stop.set()
        self._wake.set()

    async def _io(self, function, *args):
        future = asyncio.get_running_loop().run_in_executor(self._executor, function, *args)
        try:
            try:
                return await asyncio.wait_for(asyncio.shield(future), 2)
            except TimeoutError:
                self.diagnostic = self.last_error = 'SERIAL_IO_STALLED'
                return await asyncio.shield(future)
        except asyncio.CancelledError:
            result = await future
            if function == self.open:
                await self._io(result.close)
            raise

    async def _transaction(self, command, payload=b''):
        self.seq = (self.seq + 1) & 255
        return await self._io(self.transaction, self.port, self.seq, command, payload)

    async def _pause(self, seconds):
        try:
            await asyncio.wait_for(self._wake.wait(), seconds)
        except TimeoutError:
            pass
        self._wake.clear()

    async def _close_port(self):
        port, self.port = self.port, None
        if port is not None:
            await self._io(port.close)

    def _read_status(self, data):
        return dict(mode={0:'BOOT',1:'WAIT_SYNC',2:'ACTIVE',3:'LINK_LOST',4:'SUSPENDED'}.get(data[0],'UNKNOWN'),
                    applied_state={v:k for k,v in STATES.items()}.get(data[1],'NONE'),
                    display_revision=int.from_bytes(data[2:6],'little'), revision_valid=bool(data[6]),
                    brightness_pct=data[7], firmware_version=f'{data[10]}.{data[9]}',
                    uptime_s=int.from_bytes(data[11:15],'little'), crc_drop_count=int.from_bytes(data[15:17],'little'))

    async def run(self):
        delay, last_status = .5, 0
        try:
            while not self._stop.is_set():
                try:
                    while not self._controls.empty():
                        generation, cfg = self._controls.get_nowait()
                        if generation != self.connection_generation:
                            continue
                        await self._close_port()
                        if cfg is not None:
                            self.cfg.update(cfg)
                            self.selected_port = cfg.get('port')
                        self.state = 'DISCONNECTED' if self.enabled else 'DISABLED'
                    if self._stop.is_set():
                        break
                    if not self.enabled:
                        self.state = 'DISABLED'
                        await self._pause(5)
                        continue
                    generation = self.connection_generation
                    if self.port is None:
                        self.state = 'CONNECTING'
                        port = await self._io(self.open, dict(self.cfg))
                        if generation != self.connection_generation or self._stop.is_set():
                            await self._io(port.close)
                            continue
                        self.port = port
                        self.selected_port = getattr(port, 'port', self.cfg.get('port'))
                        status = await self._transaction(3)
                        if generation != self.connection_generation or self._stop.is_set():
                            continue
                        if status[6]:
                            with self.store.db:
                                self.store.s['revision'] = (int.from_bytes(status[2:6], 'little') + 1) & 0xffffffff
                                self.store.persist()
                        self._sent, delay, last_status = None, .5, 0
                    self.store.tick()
                    if self.test_running and self._stage_sent and self._stage_deadline is not None and time.monotonic() >= self._stage_deadline:
                        self.display_test['stage_results'][-1]['held_until'] = utc_now()
                        stages = ['red','yellow','green','restoring']
                        self.display_test['stage'] = stages[stages.index(self.display_test['stage']) + 1]
                        self._stage_sent, self._stage_deadline = False, None
                    desired = self._desired()
                    force_stage = self.test_running and not self._stage_sent
                    if desired != self._sent or force_stage:
                        self._target_pending = True
                        with self.store.db:
                            self.store.s['revision'] = (self.store.s['revision'] + 1) & 0xffffffff
                            revision = self.store.s['revision']
                            self.store.persist()
                        test_id = self.display_test['test_id'] if self.test_running else None
                        result = None
                        if test_id:
                            result = dict(stage=self.display_test['stage'], revision=revision, acked_at=None, held_until=None, error=None)
                            self.display_test['stage_results'].append(result)
                        await self._transaction(1, struct.pack('<IBB', revision, STATES[desired[0]], desired[1]))
                        if generation != self.connection_generation or self._stop.is_set():
                            continue
                        self.acked_revision, self._sent = revision, desired
                        self._target_pending = False
                        self.connected, self.diagnostic, self.state, self.last_error = True, 'OK', 'CONNECTED', None
                        # A fresh STATUS must be requested after this ACK.
                        self._status_mono = 0
                        last_status = 0
                        if result is not None and self.test_running and self.display_test['test_id'] == test_id:
                            result['acked_at'] = utc_now()
                            self._stage_sent = True
                            if self.display_test['stage'] == 'restoring':
                                self.display_test.update(state='succeeded', finished_at=utc_now())
                                self._target_pending = self._desired() != self._sent
                            else:
                                self._stage_deadline = time.monotonic() + 1
                    if self._stop.is_set() or generation != self.connection_generation:
                        continue
                    if time.monotonic() - last_status >= 1:
                        data = await self._transaction(3)
                        if generation != self.connection_generation or self._stop.is_set():
                            continue
                        status = self._read_status(data)
                        self.last_device_status = status
                        self.last_status_at = utc_now()
                        self._status_mono = last_status = time.monotonic()
                        if (status['mode'] != 'ACTIVE' or not status['revision_valid']
                                or status['display_revision'] != self.acked_revision
                                or status['applied_state'] != self._sent[0]
                                or status['brightness_pct'] != self._sent[1]):
                            self._sent = None
                            self._target_pending = True
                            if self.test_running:
                                raise OSError('DEVICE_NOT_READY')
                    await self._pause(.05)
                except (OSError, serial.SerialException) as exc:
                    reason = str(exc)
                    known = {'DEVICE_NOT_UNIQUE','DEVICE_NOT_FOUND','DEVICE_IDENTITY_MISMATCH','ACK_TIMEOUT','DEVICE_NOT_READY'}
                    self.last_error = reason if reason in known or reason.startswith('DEVICE_NACK_') else 'SERIAL_IO_FAILED'
                    self._invalidate(self.last_error)
                    self.state, self.diagnostic = 'RECONNECTING', 'RECONNECTING'
                    await self._close_port()
                    await self._pause(delay)
                    delay = min(5, delay * 2)
        finally:
            try:
                await self._close_port()
            finally:
                self.connected = False
                self.acked_revision = None
                self._executor.shutdown(wait=True)

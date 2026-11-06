import asyncio
import struct
import time
import serial
from serial.tools import list_ports
from .protocol import encode, decode

STATES = {'IDLE': 0, 'RUNNING': 1, 'ATTENTION': 2, 'ERROR': 3, 'COMPLETED': 4}


class SerialWorker:
    def __init__(self, cfg, store):
        self.cfg, self.store = cfg, store
        self.seq = 0
        self.port = None
        self.connected = False
        self.acked_revision = None
        self.diagnostic = 'DISCONNECTED'
        self.test_until = 0

    def transaction(self, command, payload=b''):
        self.seq = (self.seq + 1) & 255
        request = encode(command, self.seq, payload)
        for _ in range(3):
            self.port.write(request)
            deadline, buf = time.monotonic() + .1, bytearray()
            while time.monotonic() < deadline:
                b = self.port.read(1)
                if not b:
                    continue
                buf.extend(b)
                if len(buf) > 40:
                    # Discard through delimiter, then resynchronize.
                    while b != b'\0' and time.monotonic() < deadline:
                        b = self.port.read(1)
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
                if seq != self.seq:
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

    def open(self):
        cfg = self.cfg
        candidates = [p.device for p in list_ports.comports()
                      if p.vid == cfg['vid'] and p.pid == cfg['pid']
                      and (not cfg.get('serialNumber') or p.serial_number == cfg['serialNumber'])]
        name = cfg.get('port')
        if not name:
            if len(candidates) != 1:
                raise OSError('DEVICE_NOT_UNIQUE')
            name = candidates[0]
        self.port = serial.Serial(name, 115200, timeout=.01, write_timeout=.1)
        self.port.reset_input_buffer()
        status = self.transaction(3)
        return status

    async def run(self):
        delay, last_heartbeat, sent = .5, 0, None
        try:
            while True:
                try:
                    if self.port is None:
                        status = await asyncio.to_thread(self.open)
                        if status[6]:
                            device_revision = int.from_bytes(status[2:6], 'little')
                            with self.store.db:
                                self.store.s['revision'] = (device_revision + 1) & 0xffffffff
                                self.store.persist()
                        sent, delay = None, .5
                    state, revision = self.store.tick()
                    override = time.monotonic() < self.test_until
                    if override:
                        state = ('ATTENTION', 'RUNNING', 'COMPLETED')[min(2, int(3 - (self.test_until - time.monotonic())))]
                    desired = (state, self.cfg['brightness'])
                    if desired != sent:
                        # Every temporary display change also consumes a revision.
                        with self.store.db:
                            self.store.s['revision'] = (self.store.s['revision'] + 1) & 0xffffffff
                            revision = self.store.s['revision']
                            self.store.persist()
                        await asyncio.to_thread(self.transaction, 1, struct.pack('<IBB', revision, STATES[state], desired[1]))
                        self.acked_revision, sent = revision, desired
                        self.connected, self.diagnostic = True, 'OK'
                    if time.monotonic() - last_heartbeat >= 1:
                        # STATUS detects a USB reset/resume that invalidated the prior SET.
                        status = await asyncio.to_thread(self.transaction, 3)
                        if status[0] != 2 or not status[6] or int.from_bytes(status[2:6], 'little') != self.acked_revision:
                            sent = None
                        last_heartbeat = time.monotonic()
                    await asyncio.sleep(.05)
                except (OSError, serial.SerialException):
                    self.connected, self.diagnostic = False, 'RECONNECTING'
                    if self.port:
                        self.port.close()
                    self.port = None
                    await asyncio.sleep(delay)
                    delay = min(5, delay * 2)
        finally:
            if self.port:
                self.port.close()

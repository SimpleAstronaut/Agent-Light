import asyncio
from concurrent.futures import ThreadPoolExecutor
from serial.tools import list_ports
from .config import ConfigError


def scan_devices(cfg, include_all=False):
    result = []
    for port in list_ports.comports():
        matched = (port.vid == cfg['vid'] and port.pid == cfg['pid'] and
                   (not cfg.get('serialNumber') or port.serial_number == cfg['serialNumber']))
        if include_all or matched:
            result.append(dict(port=port.device, description=port.description, manufacturer=port.manufacturer,
                               vid=port.vid, pid=port.pid, serial_number=port.serial_number, matched=bool(matched)))
    return sorted(result, key=lambda p: (not p['matched'], p['port']))


class DeviceScanner:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='agent-light-scan')
        self.future = None
        self.stopping = False

    async def scan(self, cfg, include_all=False):
        if self.stopping:
            raise ConfigError('SERVICE_STOPPING')
        if self.future is None or self.future.done():
            self.future = asyncio.get_running_loop().run_in_executor(self.executor, scan_devices, dict(cfg), True)
        try:
            result = await asyncio.wait_for(asyncio.shield(self.future), 2)
        except TimeoutError:
            raise ConfigError('DEVICE_SCAN_TIMEOUT') from None
        except OSError:
            raise ConfigError('DEVICE_SCAN_FAILED') from None
        return result if include_all else [p for p in result if p['matched']]

    async def close(self):
        self.stopping = True
        if self.future is not None:
            await asyncio.gather(self.future, return_exceptions=True)
        self.executor.shutdown(wait=True)

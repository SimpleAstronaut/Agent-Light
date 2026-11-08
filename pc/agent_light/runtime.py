"""Qt-independent service lifecycle. Blocking waits are for CLI/tests only."""
import asyncio
import copy
import threading
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, DummyCookieJar, web

from .config import validate_config


class ServiceRuntime:
    def __init__(self, cfg, *, config_path):
        from pathlib import Path
        self.cfg = copy.deepcopy(cfg)
        self.config_path = Path(config_path).resolve() if config_path is not None else None
        self.state = 'NEW'
        self.startup_error = None
        self.shutdown_error = None
        self._mutex = threading.Lock()
        self._stop_requested = threading.Event()
        self._stopped = threading.Event()
        self._thread = None
        self._loop = self._stop = None

    def start(self):
        with self._mutex:
            if self.state in ('STARTING', 'RUNNING', 'STOPPING'):
                return self.state
            if self.state != 'NEW':
                raise RuntimeError('RUNTIME_NOT_REUSABLE')
            self.state = 'STARTING'
            self._thread = threading.Thread(target=self._run, name='agent-light-service')
            self._thread.start()
            return self.state

    def request_stop(self):
        with self._mutex:
            self._stop_requested.set()
            if self.state == 'NEW':
                self.state = 'STOPPED'
                self._stopped.set()
            elif self.state in ('STARTING', 'RUNNING'):
                self.state = 'STOPPING'
            if self._loop is not None:
                try:
                    self._loop.call_soon_threadsafe(self._stop.set)
                except RuntimeError:
                    pass  # The loop has already completed its finally chain.

    def is_running(self):
        return self.state == 'RUNNING'

    def is_stopped(self):
        return self._stopped.is_set() and (self._thread is None or not self._thread.is_alive())

    def wait_stopped(self, timeout=None):
        if not self._stopped.wait(timeout):
            if self._stop_requested.is_set():
                self.shutdown_error = {'code': 'SHUTDOWN_TIMEOUT'}
            return False
        # Completion includes thread termination, not just the final loop callback.
        if self._thread is not None:
            self._thread.join(timeout)
            return not self._thread.is_alive()
        return True

    def run_blocking(self):
        self.start()
        try:
            while not self.wait_stopped(.2):
                pass
        except KeyboardInterrupt:
            self.request_stop()
            while not self.wait_stopped(.2):
                pass
        if self.startup_error:
            raise RuntimeError(self.startup_error['code'])

    def _run(self):
        try:
            asyncio.run(self._serve())
        except Exception as exc:
            code = str(exc)
            known = {'SERVICE_ALREADY_RUNNING', 'LOOPBACK_ENDPOINT_REQUIRED',
                     'INVALID_DISPLAY_CONFIG', 'INVALID_REQUEST', 'TOKEN_MISSING', 'SERVICE_WORKER_FAILED'}
            if isinstance(exc, FileNotFoundError):
                code = 'RESOURCE_MISSING'
            elif code not in known:
                code = 'SERVICE_START_FAILED'
            self.startup_error = {'code': code}
        finally:
            with self._mutex:
                self._loop = self._stop = None
                self.state = 'FAILED' if self.startup_error else 'STOPPED'
            self._stopped.set()

    async def _serve(self):
        from .api import application, SERIAL_TASK
        validate_config(self.cfg)
        self._stop = asyncio.Event()
        self._loop = asyncio.get_running_loop()
        runner = web.AppRunner(application(self.cfg, config_path=self.config_path),
                               access_log=None, handle_signals=False, shutdown_timeout=2)
        try:
            if self._stop_requested.is_set():
                return
            await runner.setup()
            if self._stop_requested.is_set():
                return
            endpoint = self.cfg['endpoint'].rstrip('/')
            u = urlsplit(endpoint)
            site = web.TCPSite(runner, '127.0.0.1', u.port or 17321)
            try:
                await site.start()
            except OSError:
                self.startup_error = {'code': 'ENDPOINT_IN_USE'}
                return
            # Authenticate against this bound instance before reporting RUNNING.
            from pathlib import Path
            token = Path(self.cfg['tokenFile']).read_text().strip()
            async with ClientSession(trust_env=False, cookie_jar=DummyCookieJar(),
                                     timeout=ClientTimeout(total=2)) as client:
                async with client.get(endpoint + '/v1/health',
                                      headers={'Authorization': 'Bearer ' + token}) as response:
                    if response.status != 200 or (await response.json()).get('desktop_api') != 1:
                        raise RuntimeError('SERVICE_START_FAILED')
            with self._mutex:
                self.state = 'STOPPING' if self._stop_requested.is_set() else 'RUNNING'
            if not self._stop_requested.is_set():
                stop_waiter = asyncio.create_task(self._stop.wait())
                try:
                    done, pending = await asyncio.wait((stop_waiter,runner.app[SERIAL_TASK]),
                                                       return_when=asyncio.FIRST_COMPLETED)
                    if runner.app[SERIAL_TASK] in done and not self._stop_requested.is_set():
                        raise RuntimeError('SERVICE_WORKER_FAILED')
                finally:
                    stop_waiter.cancel()
                    await asyncio.gather(stop_waiter,return_exceptions=True)
        finally:
            with self._mutex:
                self.state = 'STOPPING'
            await runner.cleanup()

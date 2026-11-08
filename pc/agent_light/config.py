import json
import os
import secrets
import asyncio
import copy
import hashlib
import stat
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


class ConfigError(ValueError):
    pass


def validate_config(cfg):
    if not isinstance(cfg, dict):
        raise ConfigError('INVALID_REQUEST')
    for key in ('endpoint', 'tokenFile', 'database', 'dataDir'):
        if not isinstance(cfg.get(key), str) or not cfg[key]:
            raise ConfigError('INVALID_REQUEST')
    try:
        u = urlsplit(cfg['endpoint'])
        port = u.port
        if (u.scheme != 'http' or u.hostname != '127.0.0.1' or
                u.path not in ('', '/') or u.username is not None or
                u.password is not None or u.query or u.fragment or port == 0):
            raise ValueError()
    except ValueError:
        raise ConfigError('LOOPBACK_ENDPOINT_REQUIRED') from None
    if (type(cfg.get('brightness')) is not int or not 20 <= cfg['brightness'] <= 100 or
            type(cfg.get('completedHoldSeconds')) is not int or cfg['completedHoldSeconds'] < 0):
        raise ConfigError('INVALID_DISPLAY_CONFIG')
    return cfg


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).digest()


def save_atomic(path, cfg, *, expected_hash=None):
    """Replace only the configuration, preserving the existing file's permissions."""
    validate_config(cfg)
    path = Path(path).resolve()
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(cfg, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        if expected_hash is not None and _digest(path) != expected_hash:
            raise ConfigError('CONFIG_CHANGED_EXTERNALLY')
        if path.exists() and os.name == 'nt':
            # ReplaceFile preserves the target DACL; chmod cannot do that on Windows.
            import ctypes
            from ctypes import wintypes
            replace = ctypes.WinDLL('kernel32', use_last_error=True).ReplaceFileW
            replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
            replace.restype = wintypes.BOOL
            if not replace(str(path), temporary, None, 0, None, None):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            if path.exists():
                os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
            os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _display_patch(patch):
    if not isinstance(patch, dict) or not patch or set(patch) - {'brightness', 'completedHoldSeconds'}:
        raise ConfigError('INVALID_REQUEST')


def update_display_config(cfg_path, patch):
    _display_patch(patch)
    baseline = _digest(cfg_path)
    cfg = load(cfg_path)
    cfg.update(patch)
    save_atomic(cfg_path, cfg, expected_hash=baseline)
    return cfg


class ConfigRepository:
    """Service-loop-owned writer; accepted writes survive HTTP cancellation."""
    def __init__(self, config_path, cfg):
        self.path = Path(config_path).resolve() if config_path is not None else None
        self.cfg = copy.deepcopy(cfg)
        self.lock = asyncio.Lock()
        self._hash = _digest(self.path) if self.path is not None else None
        self._tasks = set()
        self.stopping = False

    async def update(self, patch, *, allowed, publish, check=None):
        if self.stopping:
            raise ConfigError('SERVICE_STOPPING')
        if self.path is None:
            raise ConfigError('CONFIG_PATH_REQUIRED')
        if not isinstance(patch, dict) or not patch or set(patch) - set(allowed):
            raise ConfigError('INVALID_REQUEST')
        async def commit():
            async with self.lock:
                release = check() if check else None
                try:
                    candidate = {**self.cfg, **patch}
                    validate_config(candidate)
                    try:
                        await asyncio.to_thread(save_atomic, self.path, candidate, expected_hash=self._hash)
                    except ConfigError:
                        raise
                    except OSError:
                        raise ConfigError('CONFIG_SAVE_FAILED') from None
                    self._hash = hashlib.sha256((json.dumps(candidate, ensure_ascii=False, indent=2) + '\n').encode('utf-8')).digest()
                    self.cfg = candidate
                    publish(candidate)
                    return copy.deepcopy(candidate)
                finally:
                    if callable(release):
                        release()
        task = asyncio.create_task(commit())
        self._tasks.add(task)
        def finished(t):
            self._tasks.discard(t)
            if not t.cancelled():
                t.exception()  # Observe failures even if the requesting client went away.
        task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def close(self):
        self.stopping = True
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)


def default_path():
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "AgentLight" / "config.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def initialize(path):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return load(path)
    if os.name == "nt":
        import subprocess
        import getpass
        subprocess.run(["icacls", str(path.parent), "/inheritance:r", "/grant:r",
                        f"{getpass.getuser()}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
                       check=True, capture_output=True)
    else:
        path.parent.chmod(0o700)
    token = path.parent / "token"
    with token.open("x", encoding="ascii") as stream:
        stream.write(secrets.token_urlsafe(32))
    token.chmod(0o600)
    cfg = dict(endpoint="http://127.0.0.1:17321", tokenFile=str(token),
               dataDir=str(path.parent / "dsh-outbox"), database=str(path.parent / "state.sqlite3"),
               brightness=35, completedHoldSeconds=300, port=None,
               vid=0x0483, pid=0x5740, serialNumber=None)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg

"""Serialize frozen-process DLL search changes around child creation."""
import os
import subprocess
import sys
import threading
from contextlib import contextmanager

_launch_lock = threading.Lock()


@contextmanager
def external_environment():
    with _launch_lock:
        env = dict(os.environ)
        env.pop('QT_PLUGIN_PATH', None)
        env.pop('QT_QPA_PLATFORM_PLUGIN_PATH', None)
        frozen = getattr(sys, '_MEIPASS', None)
        if frozen:
            env['PATH'] = os.pathsep.join(p for p in env.get('PATH', '').split(os.pathsep)
                                         if not os.path.normcase(p).startswith(os.path.normcase(frozen)))
        previous = None
        if os.name == 'nt' and frozen:
            import ctypes
            kernel = ctypes.windll.kernel32
            buffer = ctypes.create_unicode_buffer(32768)
            kernel.GetDllDirectoryW(len(buffer), buffer)
            previous = buffer.value
            kernel.SetDllDirectoryW(None)
        try:
            yield env
        finally:
            if previous is not None:
                kernel.SetDllDirectoryW(previous or None)


def run_readonly(argv, *, cwd, timeout=10):
    # Temporary files bound memory usage even when a detector misbehaves.
    import tempfile
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        with external_environment() as env:
            child = subprocess.Popen([str(a) for a in argv], cwd=str(cwd), env=env,
                                     stdout=out, stderr=err, creationflags=0x08000000 if os.name == 'nt' else 0)
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
            raise ValueError('DETECTION_TIMEOUT') from None
        if out.tell() > 65536 or err.tell() > 65536:
            raise ValueError('DETECTION_OUTPUT_LIMIT')
        out.seek(0)
        err.seek(0)
        return child.returncode, out.read(65536).decode('utf-8', errors='replace'), err.read(65536).decode('utf-8', errors='replace')

import os
import subprocess
import sys
from pathlib import Path


class StartupManager:
    KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'

    def __init__(self, config_path, *, executable=None, registry=None):
        self.executable = Path(executable or sys.executable).resolve()
        self.config_path = Path(config_path).resolve()
        self.available = os.name == 'nt' and (executable is not None or getattr(sys, 'frozen', False))
        self.registry = registry

    def command(self):
        return subprocess.list2cmdline([str(self.executable), '--minimized', '--config', str(self.config_path)])

    def _reg(self):
        if self.registry is None:
            import winreg
            return winreg
        return self.registry

    def enabled(self):
        if not self.available:
            return False
        reg = self._reg()
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, self.KEY) as key:
                return reg.QueryValueEx(key, 'AgentLight')[0] == self.command()
        except FileNotFoundError:
            return False

    def set_enabled(self, enabled):
        if not self.available:
            raise ValueError('INSTALL_DESKTOP_REQUIRED')
        reg = self._reg()
        with reg.CreateKey(reg.HKEY_CURRENT_USER, self.KEY) as key:
            if enabled:
                reg.SetValueEx(key, 'AgentLight', 0, reg.REG_SZ, self.command())
            else:
                try:
                    value = reg.QueryValueEx(key, 'AgentLight')[0]
                    if value == self.command():
                        reg.DeleteValue(key, 'AgentLight')
                except FileNotFoundError:
                    pass

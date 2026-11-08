import getpass
import hashlib
import json
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from .resources import canonical
from ..config import default_path


class DesktopInstance(QObject):
    activate = Signal(str)

    def __init__(self, config_path, parent=None):
        super().__init__(parent)
        self.config_path = str(Path(config_path).resolve())
        directory = default_path().parent
        directory.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256((getpass.getuser()+str(Path.home())).encode()).hexdigest()[:24]
        self.name = 'agent-light-desktop-' + digest
        self.lock = QLockFile(str(directory / (self.name + '.lock')))
        self.lock.setStaleLockTime(0)
        self.server = None
        self.sockets = set()
        self.mutex_handle = None

    def acquire(self):
        if not self.lock.tryLock(0):
            socket = QLocalSocket(self)
            socket.connectToServer(self.name)
            if not socket.waitForConnected(700):
                raise ValueError('INSTANCE_ACTIVATION_FAILED')
            socket.write(json.dumps({'action':'show_window','config_path':self.config_path}).encode()+b'\n')
            socket.waitForBytesWritten(700)
            socket.disconnectFromServer()
            return False
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self.server.listen(self.name):
            # Only after QLockFile established that no live owner remains.
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                self.lock.unlock()
                raise ValueError('INSTANCE_IPC_FAILED')
        self.server.newConnection.connect(self._connection)
        if __import__('os').name == 'nt':
            import ctypes
            from ctypes import wintypes
            create = ctypes.windll.kernel32.CreateMutexW
            create.argtypes = [wintypes.LPVOID,wintypes.BOOL,wintypes.LPCWSTR]
            create.restype = wintypes.HANDLE
            self.mutex_handle = create(None,False,r'Local\AgentLight.Desktop')
        return True

    def _connection(self):
        socket = self.server.nextPendingConnection()
        self.sockets.add(socket)
        buffer = bytearray()
        def read():
            buffer.extend(bytes(socket.readAll()))
            if len(buffer) > 4096:
                socket.disconnectFromServer()
                return
            if b'\n' not in buffer:
                return
            try:
                message = json.loads(bytes(buffer).split(b'\n')[0])
                if (set(message) == {'action','config_path'} and message['action']=='show_window'
                        and isinstance(message['config_path'],str) and Path(message['config_path']).is_absolute()):
                    self.activate.emit(message['config_path'])
            except (ValueError,TypeError):
                pass
            socket.disconnectFromServer()
        socket.readyRead.connect(read)
        def disconnected():
            self.sockets.discard(socket)
            socket.deleteLater()
        socket.disconnected.connect(disconnected)
        if socket.bytesAvailable():
            read()

    def close(self):
        for socket in tuple(self.sockets):
            socket.disconnectFromServer()
        if self.server:
            self.server.close()
        self.lock.unlock()
        if self.mutex_handle:
            import ctypes
            from ctypes import wintypes
            close = ctypes.windll.kernel32.CloseHandle
            close.argtypes = [wintypes.HANDLE]
            close(self.mutex_handle)
            self.mutex_handle = None

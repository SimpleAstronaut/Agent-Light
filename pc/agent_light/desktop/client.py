import json
from PySide6.QtCore import QObject, Signal, QTimer, QUrl, QByteArray
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkProxy


class ApiClient(QObject):
    response = Signal(str, object)
    failure = Signal(str, str)

    def __init__(self, endpoint, token, parent=None):
        super().__init__(parent)
        self.endpoint = endpoint.rstrip('/')
        self.token = token
        self.manager = QNetworkAccessManager(self)
        self.manager.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self.pending = {}
        self.sequence = 0
        self.closed = False

    def request(self, route, method='GET', payload=None, *, tag=None):
        tag = tag or route
        if self.closed or tag in self.pending:
            return False
        self.sequence += 1
        sequence = self.sequence
        request = QNetworkRequest(QUrl(self.endpoint + '/v1/' + route))
        request.setRawHeader(b'Authorization', ('Bearer ' + self.token).encode())
        request.setRawHeader(b'Content-Type', b'application/json')
        request.setTransferTimeout(2000)
        data = QByteArray(json.dumps(payload).encode()) if payload is not None else QByteArray()
        reply = self.manager.sendCustomRequest(request, method.encode(), data)
        self.pending[tag] = (sequence, reply)
        timer = QTimer(reply)
        timer.setSingleShot(True)
        timer.timeout.connect(reply.abort)
        timer.start(2000)
        def finished():
            timer.stop()
            current = self.pending.get(tag)
            if not current or current[0] != sequence:
                reply.deleteLater()
                return
            del self.pending[tag]
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            raw = bytes(reply.readAll())
            try:
                body = json.loads(raw) if len(raw) <= 4 * 1024 * 1024 else None
            except (ValueError, UnicodeError):
                body = None
            if not self.closed:
                if status is not None and 200 <= status < 300 and isinstance(body, dict):
                    self.response.emit(tag, body)
                else:
                    code = 'AUTH_FAILED' if status in (401,403) else 'SERVICE_UNAVAILABLE' if status is None else 'HTTP_ERROR'
                    candidate = body.get('error', {}).get('code') if isinstance(body, dict) else None
                    if isinstance(candidate, str) and candidate.isascii() and candidate.replace('_','').isalnum() and len(candidate) < 80:
                        code = candidate
                    self.failure.emit(tag, code)
            reply.deleteLater()
        reply.finished.connect(finished)
        return True

    def invalidate(self, tag):
        item = self.pending.pop(tag, None)
        if item:
            item[1].abort()

    def close(self):
        self.closed = True
        for _, reply in tuple(self.pending.values()):
            reply.abort()

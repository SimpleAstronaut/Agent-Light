from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool


class Signals(QObject):
    result = Signal(object)
    error = Signal(str)
    done = Signal()


class Job(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = Signals()

    def run(self):
        try:
            self.signals.result.emit(self.function())
        except Exception as error:
            code = str(error).split(':',1)[0]
            if not code.isascii() or not code.replace('_','').isalnum() or len(code)>80:
                code = 'OPERATION_FAILED'
            self.signals.error.emit(code)
        finally:
            self.signals.done.emit()


class Tasks(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.jobs = set()

    def submit(self, function, result, error):
        job = Job(function)
        self.jobs.add(job)
        job.signals.result.connect(result)
        job.signals.error.connect(error)
        job.signals.done.connect(lambda: self.jobs.discard(job))
        self.pool.start(job)

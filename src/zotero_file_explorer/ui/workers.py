from PySide6.QtCore import QObject, QRunnable, Signal


class Signals(QObject):
    finished = Signal(object, object)
    progress = Signal(str)


class Task(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = Signals()

    def run(self):
        try:
            self.signals.finished.emit(self.function(), None)
        except Exception as error:
            self.signals.finished.emit(None, error)

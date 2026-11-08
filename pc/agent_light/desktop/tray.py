from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PySide6.QtWidgets import QSystemTrayIcon, QMenu


def app_icon():
    pixmap = QPixmap(64,64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor('#173d36'))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4,4,56,56,14,14)
    for y,color in ((18,'#f27e70'),(32,'#eec86b'),(46,'#9fd5a6')):
        painter.setBrush(QColor(color))
        painter.drawEllipse(26,y-6,12,12)
    painter.end()
    return QIcon(pixmap)


class Tray(QObject):
    open_requested = Signal()
    settings_requested = Signal()
    test_requested = Signal()
    exit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.icon = QSystemTrayIcon(app_icon(),self)
        menu = QMenu()
        self.menu = menu
        for text, signal in (('打开主界面',self.open_requested),):
            menu.addAction(text,signal.emit)
        self.summary = menu.addAction('服务等待启动')
        self.summary.setEnabled(False)
        self.test_action = menu.addAction('三色测试',self.test_requested.emit)
        menu.addAction('设置',self.settings_requested.emit)
        menu.addSeparator()
        menu.addAction('退出 Agent Light',self.exit_requested.emit)
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(lambda reason: self.open_requested.emit()
            if reason in (QSystemTrayIcon.ActivationReason.Trigger,QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        if self.available():
            self.icon.show()

    def available(self):
        return QSystemTrayIcon.isSystemTrayAvailable()

    def update(self, summaries, test_enabled=False):
        text = ' · '.join(summaries[:3])
        self.summary.setText(text)
        self.icon.setToolTip('Agent Light\n'+'\n'.join(summaries[:3]))
        self.test_action.setEnabled(test_enabled)

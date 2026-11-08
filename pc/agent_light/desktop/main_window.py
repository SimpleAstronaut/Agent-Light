from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QStackedWidget, QLabel, QPushButton
from .agents import AGENTS
from .pages.status import StatusPage
from .pages.device import DevicePage
from .pages.settings import SettingsPage
from .pages.plugins import PluginsPage
from .models import explain

STYLE = '''
QWidget { font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 13px; color: #263c39; }
QMainWindow, QWidget#content { background: #f3f6f3; }
QTreeWidget#navigation { background: #173d36; color: #effaf3; border: 0; padding: 16px 6px; }
QTreeWidget#navigation::item { padding: 12px 6px; border-radius: 8px; }
QTreeWidget#navigation::item:selected { background: #326455; }
QTreeWidget#navigation::item:hover { background: #285448; }
QLabel#pageTitle { font-size: 25px; font-weight: 600; padding: 8px 0 16px; }
QFrame#card { background: white; border: 1px solid #dce4df; border-radius: 10px; padding: 12px; }
QLabel#cardValue { font-size: 18px; font-weight: 600; padding-top: 12px; }
QPushButton { background: white; border: 1px solid #becfc7; border-radius: 6px; padding: 8px 14px; }
QPushButton:hover { background: #e3eee7; }
QPushButton#primary { background: #235c48; color: white; border-color: #235c48; }
QPushButton:disabled { color: #9ca8a2; background: #ecf0eb; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit { background: white; border: 1px solid #cbd8cf; border-radius: 5px; padding: 6px; }
QTableWidget { background: white; border: 1px solid #dce4df; gridline-color: #edf1ed; }
QHeaderView::section { background: #e5ede6; border: 0; padding: 10px; }
QLabel#error { color: #8b3c28; background: #fff0e6; border-radius: 6px; padding: 10px; }
'''


class MainWindow(QMainWindow):
    close_requested = Signal()
    refresh_requested = Signal()

    def __init__(self):
        super().__init__()
        # Qt's offscreen backend on Windows has no system font database.
        # Load the existing system font for readable automated rendering as well.
        if not QFontDatabase.families() and __import__('os').name == 'nt':
            from pathlib import Path
            import os
            font = Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts/msyh.ttc'
            if font.is_file():
                QFontDatabase.addApplicationFont(str(font))
        self.setWindowTitle('Agent Light')
        self.resize(1060,720)
        self.setMinimumSize(800,560)
        self.setStyleSheet(STYLE)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0,0,0,0)
        self.navigation = QTreeWidget()
        self.navigation.setObjectName('navigation')
        self.navigation.setHeaderHidden(True)
        self.navigation.setIndentation(16)
        self.navigation.setMinimumWidth(210)
        self.navigation.setMaximumWidth(230)
        self.navigation_items = {}
        self.section_indices = {'status':0,'device':1,'integrations':2,'settings':3}
        for section, text in (('status','01  状态'),('device','02  设备'),('integrations','03  Agent 接入'),('settings','04  设置')):
            item = QTreeWidgetItem(self.navigation,[text])
            item.setData(0,Qt.ItemDataRole.UserRole,(section,None))
            self.navigation_items[(section,None)] = item
            if section == 'integrations':
                for agent in AGENTS:
                    child = QTreeWidgetItem(item,[agent.name+' · '+agent.status])
                    child.setData(0,Qt.ItemDataRole.UserRole,(section,agent.agent_id))
                    self.navigation_items[(section,agent.agent_id)] = child
                item.setExpanded(True)
        layout.addWidget(self.navigation)
        content = QWidget()
        content.setObjectName('content')
        column = QVBoxLayout(content)
        column.setContentsMargins(24,16,24,20)
        self.banner = QLabel('正在启动后台服务…')
        self.banner.setWordWrap(True)
        self.banner.setObjectName('error')
        column.addWidget(self.banner)
        self.stack = QStackedWidget()
        self.status_page = StatusPage()
        self.device_page = DevicePage()
        self.plugins_page = PluginsPage()
        self.settings_page = SettingsPage()
        for page in (self.status_page,self.device_page,self.plugins_page,self.settings_page):
            self.stack.addWidget(page)
        self.navigation.currentItemChanged.connect(self._navigation_changed)
        self.navigate('status')
        column.addWidget(self.stack,1)
        bottom = QHBoxLayout()
        self.endpoint_label = QLabel('本地运行 · 不采集聊天内容')
        self.endpoint_label.setWordWrap(True)
        bottom.addWidget(self.endpoint_label,1)
        refresh = QPushButton('刷新状态')
        refresh.clicked.connect(self.refresh_requested.emit)
        bottom.addWidget(refresh)
        column.addLayout(bottom)
        layout.addWidget(content,1)
        self.close_to_tray = False
        self.tray_available = False
        self.final_close = False

    def _navigation_changed(self, current, previous):
        if current is None:
            return
        section, agent_id = current.data(0,Qt.ItemDataRole.UserRole)
        if agent_id:
            self.plugins_page.select_agent(agent_id)
        self.stack.setCurrentIndex(self.section_indices[section])

    def navigate(self, section, agent_id=None):
        item = self.navigation_items.get((section,agent_id))
        if item is None:
            return False
        self.navigation.setCurrentItem(item)
        return True

    def error(self, code):
        self.banner.setText(explain(code))
        self.banner.show()

    def closeEvent(self, event):
        if self.final_close:
            event.accept()
        elif self.close_to_tray and self.tray_available:
            self.hide()
            self.close_requested.emit()
            event.ignore()
        else:
            self.close_requested.emit()
            event.ignore()

    def activate(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

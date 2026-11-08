from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QPlainTextEdit


class DshPage(QWidget):
    action = Signal(str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel('DSH 接入')
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        form = QFormLayout()
        self.paths = {}
        for key, label in (('entry','DSH lib/bin.js'),('node','该 DSH 的 Node'),('launcher','dsh-web.ps1')):
            row = QHBoxLayout()
            edit = QLineEdit()
            edit.setPlaceholderText('自动发现或浏览选择')
            browse = QPushButton('浏览…')
            browse.clicked.connect(lambda checked=False, k=key: self.browse(k))
            row.addWidget(edit,1)
            row.addWidget(browse)
            form.addRow(label,row)
            self.paths[key] = edit
        layout.addLayout(form)
        row = QHBoxLayout()
        self.buttons = []
        for action,label in (('detect','重新检测'),('generate','生成接入配置'),('install','安装 / 更新接入'),('uninstall','卸载接入'),('open','打开配置目录')):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False,a=action:self.action.emit(a))
            self.buttons.append(button)
            row.addWidget(button)
        layout.addLayout(row)
        self.summary = QLabel('未检测。配置已安装、宿主兼容、插件加载和当前上报分别判断。')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output,1)

    def browse(self, key):
        path,_ = QFileDialog.getOpenFileName(self, '选择 '+key)
        if path:
            self.paths[key].setText(path)

    def values(self):
        return {k:v.text().strip() for k,v in self.paths.items()}

    def busy(self, busy):
        for b in self.buttons:
            b.setEnabled(not busy)

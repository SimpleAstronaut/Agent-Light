from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame


class PendingAgentPage(QWidget):
    action = Signal(str)

    def __init__(self, definition):
        super().__init__()
        self.definition = definition
        layout = QVBoxLayout(self)
        title = QLabel(definition.name+' 接入')
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        card = QFrame()
        card.setObjectName('card')
        content = QVBoxLayout(card)
        status = QLabel('待适配')
        status.setObjectName('cardValue')
        content.addWidget(status)
        description = QLabel(definition.description)
        description.setWordWrap(True)
        content.addWidget(description)
        explanation = QLabel('此页暂不提供事件接入和配置安装。切换到此页不会改变其他 Agent 的连接或上报。')
        explanation.setWordWrap(True)
        content.addWidget(explanation)
        layout.addWidget(card)
        self.environment_status = QLabel('环境尚未检测。检测结果不代表事件适配已实现。'
                                        if 'detect' in definition.actions else '当前尚未提供环境检测。')
        self.environment_status.setWordWrap(True)
        layout.addWidget(self.environment_status)
        actions = QHBoxLayout()
        self.buttons = {}
        for action, label in (('detect','检测环境'),('generate','生成接入配置'),('install','安装接入'),('uninstall','卸载接入')):
            button = QPushButton(label)
            button.setEnabled(action in definition.actions)
            if action not in definition.actions:
                button.setToolTip('此 Agent 的相关适配尚未实现')
            button.clicked.connect(lambda checked=False,a=action: self.action.emit(a))
            self.buttons[action] = button
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addStretch()

    def busy(self, busy):
        for action, button in self.buttons.items():
            button.setEnabled(not busy and action in self.definition.actions)

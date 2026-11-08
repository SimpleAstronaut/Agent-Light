from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget
from ..agents import AGENTS


class PluginsPage(QWidget):
    action = Signal(str, str)  # agent_id, action
    selected = Signal(str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        self.stack = QStackedWidget()
        self.panels = {}
        for definition in AGENTS:
            panel = definition.page_factory(definition)
            panel.action.connect(lambda action,agent_id=definition.agent_id: self.action.emit(agent_id,action))
            self.panels[definition.agent_id] = panel
            self.stack.addWidget(panel)
        layout.addWidget(self.stack)
        self.current_agent_id = 'dsh'
        self.dsh_page = self.panels['dsh']
        self.stack.setCurrentWidget(self.dsh_page)

    def select_agent(self, agent_id):
        if agent_id not in self.panels:
            return False
        self.stack.setCurrentWidget(self.panels[agent_id])
        if self.current_agent_id != agent_id:
            self.current_agent_id = agent_id
            self.selected.emit(agent_id)
        return True

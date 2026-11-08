from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTableWidget,
                              QTableWidgetItem, QHeaderView, QPushButton, QAbstractItemView, QMessageBox)
from ..models import overview


class StatusPage(QWidget):
    manage = Signal(object, bool)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel('状态总览')
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        cards = QHBoxLayout()
        self.values = []
        for name in ('本地服务', 'DSH 上报', '灯板确认', '业务灯态'):
            card = QFrame()
            card.setObjectName('card')
            box = QVBoxLayout(card)
            box.addWidget(QLabel(name))
            value = QLabel('等待启动')
            value.setWordWrap(True)
            value.setObjectName('cardValue')
            box.addWidget(value)
            cards.addWidget(card)
            self.values.append(value)
        layout.addLayout(cards)
        self.details = QLabel('')
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        layout.addWidget(QLabel('来源明细 · Codex 真实适配器尚未实现'))
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['来源 / Producer', '管理状态', '健康 / 租约', '最近心跳（UTC）', '持久 / 已确认', '停用后上报'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        for label, enable in (('停用来源', False), ('重新启用来源', True)):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, e=enable: self.confirm_manage(e))
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.rows = []
        self.fresh = False

    def update_snapshot(self, snapshot=None, *, fresh=True, failures=0):
        self.fresh = fresh
        for label, text in zip(self.values, overview(snapshot, fresh=fresh, failures=failures)):
            label.setText(text)
        self.table.setEnabled(fresh)
        if not fresh or snapshot is None:
            self.details.setText('快照已过期，恢复通信后自动刷新。')
            return
        device = snapshot.get('device', {})
        self.details.setText('端口：{}　固件：{}　模式：{}　实际灯态：{}　ACK：{}　诊断：{}'.format(
            device.get('selected_port') or '自动发现', device.get('firmware_version','—'), device.get('mode','—'),
            device.get('applied_state','—'), device.get('acked_revision','—'), device.get('last_error') or device.get('diagnostic','—')))
        selected = self.table.currentRow()
        identity = (self.rows[selected]['agent'], self.rows[selected]['producer_id']) if 0 <= selected < len(self.rows) else None
        self.rows = snapshot.get('producers', [])
        self.table.setRowCount(len(self.rows))
        for row, p in enumerate(self.rows):
            texts = [p['agent'] + ' / ' + p['producer_id'], p.get('management_state','enabled'),
                str(p.get('health','—')) + (' / 租约过期' if p.get('lease_expired') else ''),
                p.get('last_heartbeat_at') or '本进程尚未收到', f"{p.get('persisted_seq',0)} / {p.get('acked_seq',0)}",
                p.get('rejected_after_disable_at') or '—']
            for column, text in enumerate(texts):
                self.table.setItem(row, column, QTableWidgetItem(text))
            if identity == (p['agent'], p['producer_id']):
                self.table.selectRow(row)

    def confirm_manage(self, enable):
        row = self.table.currentRow()
        if not self.fresh or not 0 <= row < len(self.rows):
            return
        producer = self.rows[row]
        text = ('重新启用后，需要重启对应 DSH，以新 runtime 和心跳恢复。旧来源在恢复前仍贡献异常。'
                if enable else '请确认已退出对应 DSH 采集器。停用将排除该来源及旧会话的灯态贡献，保留全部历史。')
        text = producer['agent'] + ' / ' + producer['producer_id'] + '\n\n' + text
        if QMessageBox.question(self, '确认来源管理', text) == QMessageBox.StandardButton.Yes:
            self.manage.emit(dict(agent=producer['agent'], producer_id=producer['producer_id'],
                                 expected_generation=producer['management_generation'], confirm=True), enable)

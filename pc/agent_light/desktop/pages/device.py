from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                              QPushButton, QComboBox, QCheckBox, QLineEdit, QPlainTextEdit)


class DevicePage(QWidget):
    scan = Signal(bool)
    connect_device = Signal(object)
    disconnect_device = Signal()
    test = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel('设备与灯板')
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItems(['自动发现', '手动指定端口'])
        form.addRow('连接方式', self.mode)
        row = QHBoxLayout()
        self.ports = QComboBox()
        self.ports.setMinimumContentsLength(28)
        self.scan_button = QPushButton('扫描')
        self.scan_button.clicked.connect(lambda: self.scan.emit(self.include_all.isChecked()))
        row.addWidget(self.ports, 1)
        row.addWidget(self.scan_button)
        form.addRow('串口', row)
        self.include_all = QCheckBox('显示全部串口（包括不匹配的设备）')
        form.addRow('', self.include_all)
        self.serial_number = QLineEdit()
        self.serial_number.setPlaceholderText('可选；留空清除旧筛选')
        form.addRow('序列号筛选', self.serial_number)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.connect_button = QPushButton('保存并连接')
        self.connect_button.setObjectName('primary')
        self.connect_button.clicked.connect(self.submit_connect)
        disconnect = QPushButton('断开')
        disconnect.clicked.connect(self.disconnect_device.emit)
        actions.addWidget(self.connect_button)
        actions.addWidget(disconnect)
        actions.addStretch()
        layout.addLayout(actions)
        self.detail = QLabel('等待设备状态')
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        self.test_button = QPushButton('开始红 → 黄 → 绿三色测试')
        self.test_button.clicked.connect(self.test.emit)
        self.test_button.setEnabled(False)
        layout.addWidget(self.test_button)
        self.test_status = QLabel('测试尚未开始。成功表示设备 ACK，不代表光学检测。')
        self.test_status.setWordWrap(True)
        layout.addWidget(self.test_status)
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        layout.addWidget(self.history, 1)
        self.mode.currentIndexChanged.connect(self.validate)
        self.ports.currentIndexChanged.connect(self.validate)
        self.validate()

    def validate(self):
        self.ports.setEnabled(self.mode.currentIndex() == 1)
        self.connect_button.setEnabled(self.mode.currentIndex() == 0 or bool(self.ports.currentData()))

    def submit_connect(self):
        body = dict(mode='auto' if self.mode.currentIndex() == 0 else 'manual',
                    serial_number=self.serial_number.text().strip() or None)
        if body['mode'] == 'manual':
            body['port'] = self.ports.currentData()
        self.connect_device.emit(body)

    def show_devices(self, rows):
        selected = self.ports.currentData()
        self.ports.clear()
        for p in rows:
            self.ports.addItem(p['port'] + ' · ' + (p.get('description') or '') + (' [匹配]' if p['matched'] else ''), p['port'])
        index = self.ports.findData(selected)
        if index >= 0:
            self.ports.setCurrentIndex(index)
        elif len(rows) > 1:
            self.ports.setCurrentIndex(-1)
        self.scan_button.setEnabled(True)
        self.validate()

    def update_snapshot(self, snapshot, fresh=True):
        device = snapshot.get('device', {}) if fresh else {}
        test = snapshot.get('display_test', {}) if fresh else {}
        self.detail.setText('状态：{}　端口：{}　确认：{}\n模式：{}　实际灯态：{}　亮度：{}　固件：{}\n诊断：{}'.format(
            device.get('state','未知（服务离线/快照过期）'), device.get('selected_port') or '—',
            '已确认' if device.get('confirmed') else '未确认', device.get('mode','—'),
            device.get('applied_state','—'), device.get('brightness_pct','—'), device.get('firmware_version','—'),
            device.get('last_error') or device.get('diagnostic','—')))
        running = test.get('state') == 'running'
        self.test_button.setEnabled(bool(device.get('confirmed')) and not running)
        state = test.get('state', 'idle')
        text = '灯板已确认完成三色测试' if state == 'succeeded' else '测试阶段：' + test.get('stage','none') if running else '测试失败：' + str(test.get('error')) if state == 'failed' else '等待测试'
        self.test_status.setText(text)
        self.history.setPlainText('\n'.join('{} · revision={} · ACK={} · 保持结束={} · {}'.format(
            r['stage'],r['revision'],r.get('acked_at') or '等待',r.get('held_until') or '—',r.get('error') or '') for r in test.get('stage_results',[])))

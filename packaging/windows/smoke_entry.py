import traceback
from pathlib import Path
log = Path(__import__('sys').executable).parent / 'smoke-result.txt'
try:
    import sys
    from PySide6.QtWidgets import QApplication, QLabel
    from PySide6.QtCore import QTimer
    from agent_light.desktop.resources import validate_plugin
    from agent_light.core import SCHEMA

    app = QApplication(sys.argv)
    validate_plugin()
    assert SCHEMA
    window = QLabel('Agent Light · Qt 分发验证')
    window.resize(480, 180)
    window.show()
    QTimer.singleShot(300, app.quit)
    sys.exit(app.exec())
except BaseException as exc:
    if isinstance(exc, SystemExit):
        log.write_text('PASS: '+str(exc.code), encoding='utf-8')
    else:
        log.write_text(traceback.format_exc(), encoding='utf-8')

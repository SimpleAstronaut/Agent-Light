import json
import sys
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QCheckBox, QDialogButtonBox, QMessageBox
from ..integrations import dsh
from .resources import integration_root
from .agents import AGENTS_BY_ID


def confirm_preview(parent, preview):
    dialog=QDialog(parent)
    dialog.setWindowTitle('确认修改 DSH 接入')
    dialog.resize(880,620)
    layout=QVBoxLayout(dialog)
    text='即将修改启动脚本；将备份原文件，保留数据和 outbox。'
    if preview.get('kind')=='legacy-unmarked':
        text+='\n本次会迁移已识别的旧接入，避免重复注入。'
    if preview.get('overlay_path'):
        text+='\n正式 overlay：'+preview['overlay_path']+'\n插件：'+preview['plugin_root']
    layout.addWidget(QLabel(text))
    diff=QPlainTextEdit(preview['diff'])
    diff.setReadOnly(True)
    layout.addWidget(diff,1)
    check=QCheckBox('我已退出所有加载此插件的 DSH Web 后端，并确认上述修改')
    layout.addWidget(check)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
    check.toggled.connect(buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    return dialog.exec()==QDialog.DialogCode.Accepted


def dsh_action(controller, action, page, finished):
    paths=page.values()
    for key,value in paths.items():
        controller.preferences.setValue('dsh/'+key,value)
    if action=='open':
        root=integration_root(controller.config_path)
        root.mkdir(parents=True,exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(root)))
        finished()
        return
    def fail(code):
        finished()
        controller.window.error(code)
    def detected(result):
        if controller.exiting:
            finished()
            return
        found,host,record=result
        for key,value in found.items():
            if key in page.paths and value and page.paths[key].text().strip() == paths.get(key,''):
                page.paths[key].setText(value)
                controller.preferences.setValue('dsh/'+key,value)
        page.summary.setText('宿主版本与指纹兼容；接入配置和实际运行状态仍需分别核对。' if host.get('compatible') else '未通过宿主检测：'+str(host.get('error_code')))
        status = '未登记接入' if not record else '配置已安装（运行状态请查看状态页）' if record.get('status')=='committed' else '接入已解除' if record.get('status')=='detached' else '接入事务待核对'
        page.summary.setText(page.summary.text()+'\n'+status)
        page.output.setPlainText(json.dumps(host,ensure_ascii=False,indent=2))
        finished()
    def detect():
        found=dsh.discover(paths)
        host=dsh.inspect_host(found.get('entry'),found.get('node'))
        return found,host,dsh.recover_pending(controller.config_path)
    if action=='detect':
        controller.tasks.submit(detect,detected,fail)
    elif action=='generate':
        def generated(path):
            page.summary.setText('配置已生成（草稿）；没有覆盖启动器正在引用的正式文件。')
            page.output.setPlainText(str(path))
            finished()
        controller.tasks.submit(lambda:dsh.generate_draft(controller.config_path,controller.cfg),generated,fail)
    elif action in ('install','uninstall'):
        def previewed(preview):
            if controller.exiting:
                finished()
                return
            if preview.get('status')=='detached':
                page.summary.setText('没有已登记的活动接入。')
                finished()
                return
            if not confirm_preview(controller.window,preview):
                finished()
                return
            def applied(result):
                finished()
                page.summary.setText('接入配置已安装，重启 DSH 后生效。' if action=='install' else '接入已解除。退出 / 重启 DSH 后，可在状态页显式停用旧来源。')
                page.output.setPlainText(json.dumps(result,ensure_ascii=False,indent=2))
            operation=dsh.install if action=='install' else dsh.uninstall
            controller.tasks.submit(lambda:operation(preview,confirmed_stopped=True),applied,fail)
        if action=='install':
            controller.tasks.submit(lambda:dsh.preview_install(controller.config_path,controller.cfg,
                launcher=paths['launcher'],entry=paths['entry'],node=paths['node']),previewed,fail)
        else:
            controller.tasks.submit(lambda:dsh.preview_uninstall(controller.config_path),previewed,fail)
    else:
        finished()


def codex_action(controller, action, page, finished):
    def detected(result):
        if not controller.exiting:
            page.environment_status.setText(result)
        finished()
    def failed(code):
        finished()
        if not controller.exiting:
            controller.window.error(code)
    controller.tasks.submit(dsh.detect_codex,detected,failed)


ACTION_HANDLERS = {'dsh': dsh_action, 'codex': codex_action}


def plugin_action(controller, action, agent_id='dsh'):
    definition = AGENTS_BY_ID.get(agent_id)
    if definition is None or action not in definition.actions or agent_id not in ACTION_HANDLERS:
        controller.window.error('ADAPTER_NOT_IMPLEMENTED')
        return False
    pending = getattr(controller,'_integration_jobs',None)
    if pending is None:
        pending = controller._integration_jobs = set()
    if agent_id in pending:
        return False
    page = controller.window.plugins_page.panels[agent_id]
    pending.add(agent_id)
    page.busy(True)
    def finished():
        pending.discard(agent_id)
        page.busy(False)
    try:
        ACTION_HANDLERS[agent_id](controller,action,page,finished)
    except (OSError,ValueError):
        finished()
        controller.window.error('OPERATION_FAILED')
        return False
    return True


def prepare_uninstall():
    try:
        references=dsh.managed_references(Path(sys.executable).parent)
        if references:
            QMessageBox.information(None,'卸载前检查','发现已登记的 DSH 启动器引用本安装目录。请先退出所有 DSH，再逐项确认解除接入。')
        for record in references:
            preview=dsh.preview_uninstall(record['config_path'])
            if preview.get('status')!='detached':
                if not confirm_preview(None,preview):
                    return 1
                dsh.uninstall(preview,confirmed_stopped=True)
        if QMessageBox.question(None,'保留用户数据','将保留配置、token、数据库、outbox、overlay 和备份。\n请同时解除任何手工创建、未登记的 overlay 引用。确认继续卸载程序？')!=QMessageBox.StandardButton.Yes:
            return 1
        # Remove only a Run value that still points at this exact installation.
        if sys.platform=='win32':
            import winreg
            import ctypes
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run',0,winreg.KEY_READ|winreg.KEY_SET_VALUE) as key:
                    value=winreg.QueryValueEx(key,'AgentLight')[0]
                    count=ctypes.c_int()
                    split=ctypes.windll.shell32.CommandLineToArgvW
                    split.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_int)]
                    split.restype=ctypes.POINTER(ctypes.c_wchar_p)
                    args=split(value,ctypes.byref(count))
                    if args:
                        try:
                            if count.value and Path(args[0]).resolve()==Path(sys.executable).resolve():
                                winreg.DeleteValue(key,'AgentLight')
                        finally:
                            ctypes.windll.kernel32.LocalFree(args)
            except FileNotFoundError:
                pass
        return 0
    except (ValueError,OSError) as error:
        code=str(error).split(':',1)[0]
        QMessageBox.critical(None,'无法安全解除接入',code+'\n请通过插件页或安装记录核对启动器，完成后重新卸载。')
        return 1

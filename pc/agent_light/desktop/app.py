import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from PySide6.QtCore import QSettings, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox
from .client import ApiClient
from .instance import DesktopInstance
from .main_window import MainWindow
from .models import overview
from .resources import canonical, integration_root, validate_plugin
from .startup import StartupManager
from .tasks import Tasks
from .tray import Tray, app_icon
from ..config import default_path, initialize, validate_config
from ..runtime import ServiceRuntime


def prepare_configuration(path):
    validate_plugin()
    cfg = initialize(path)
    validate_config(cfg)
    token = Path(cfg['tokenFile']).read_text(encoding='utf-8').strip()
    if not token:
        raise ValueError('TOKEN_MISSING')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(cfg['endpoint'].rstrip('/')+'/v1/health', headers={'Authorization':'Bearer '+token})
    try:
        with opener.open(request,timeout=.7) as response:
            try:
                compatible = json.loads(response.read(65536)).get('desktop_api') == 1
            except (ValueError,AttributeError):
                compatible = False
            raise ValueError('SERVICE_ALREADY_RUNNING' if compatible else 'ENDPOINT_IN_USE')
    except urllib.error.HTTPError:
        raise ValueError('ENDPOINT_IN_USE') from None
    except (urllib.error.URLError, TimeoutError):
        # A failed probe is inconclusive (Windows refusal can exceed its timeout).
        # ProcessLock and TCPSite binding remain the authoritative ownership checks.
        pass
    return cfg, token


class DesktopController:
    def __init__(self, application, args, instance):
        self.application, self.args, self.instance = application, args, instance
        self.config_path = args.config.resolve()
        self.preferences = QSettings('AgentLight','Desktop')
        self.window = MainWindow()
        self.window.setWindowIcon(app_icon())
        self.tray = Tray(self.window)
        self.tasks = Tasks(self.window)
        self.runtime = self.client = None
        self.cfg = None
        self.exiting = False
        self.exit_started = 0
        self.last_poll = 0
        self.failures = 0
        self.snapshot = {}
        self.fresh = False
        self.started_polling = False
        self.startup = StartupManager(self.config_path)
        self._wire()
        self.timer = QTimer(self.window)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.refresh_tray_availability()
        settings = self.window.settings_page
        settings.close_to_tray.setChecked(self.preferences.value('close_to_tray',True,type=bool) and self.tray.available())
        settings.startup.blockSignals(True)
        settings.startup.setChecked(self.startup.enabled())
        settings.startup.blockSignals(False)
        settings.startup.setEnabled(self.startup.available)
        for key,edit in self.window.plugins_page.dsh_page.paths.items():
            edit.setText(self.preferences.value('dsh/'+key,''))
        selected = self.preferences.value('integrations/selected_agent','dsh')
        if not self.window.plugins_page.select_agent(selected):
            self.preferences.setValue('integrations/selected_agent','dsh')
        if not args.minimized or not self.tray.available():
            self.window.show()
        self.tasks.submit(lambda: prepare_configuration(self.config_path), self.configured, self.window.error)

    def _wire(self):
        window = self.window
        window.refresh_requested.connect(self.refresh)
        window.close_requested.connect(self.window_closed)
        self.tray.open_requested.connect(window.activate)
        self.tray.settings_requested.connect(lambda: (window.navigate('settings'),window.activate()))
        self.tray.test_requested.connect(lambda:self.call('display/test','POST',{}))
        self.tray.exit_requested.connect(self.request_exit)
        self.instance.activate.connect(self.activate)
        window.status_page.manage.connect(lambda body,enable:self.call('producers/'+('enable' if enable else 'disable'),'POST',body,tag='manage_source'))
        window.device_page.scan.connect(self.scan)
        window.device_page.connect_device.connect(lambda body:self.call('device/connect','POST',body,tag='connect'))
        window.device_page.disconnect_device.connect(lambda:self.call('device/disconnect','POST',{},tag='disconnect'))
        window.device_page.test.connect(lambda:self.call('display/test','POST',{}))
        window.settings_page.save.connect(lambda body:self.call('config/display','PATCH',body,tag='save_display'))
        window.settings_page.tray_changed.connect(self.set_tray_preference)
        window.settings_page.startup_changed.connect(self.set_startup)
        window.plugins_page.action.connect(lambda agent_id,action:self.plugin_action(action,agent_id=agent_id))
        window.plugins_page.selected.connect(lambda agent_id:self.preferences.setValue('integrations/selected_agent',agent_id))

    def configured(self, result):
        if self.exiting:
            return
        self.cfg, token = result
        self.client = ApiClient(self.cfg['endpoint'], token, self.window)
        self.client.response.connect(self.response)
        self.client.failure.connect(self.failure)
        self.window.endpoint_label.setText(self.cfg['endpoint']+' · '+str(self.config_path))
        self.runtime = ServiceRuntime(self.cfg,config_path=self.config_path)
        self.runtime.start()

    def activate(self, config):
        self.window.activate()
        if canonical(config) != canonical(self.config_path):
            self.window.error('CONFIG_INSTANCE_CONFLICT')

    def set_tray_preference(self, enabled):
        enabled = bool(enabled and self.tray.available())
        self.window.close_to_tray = enabled
        self.preferences.setValue('close_to_tray',enabled)

    def set_startup(self, enabled):
        try:
            self.startup.set_enabled(enabled)
        except (OSError,ValueError):
            checkbox = self.window.settings_page.startup
            checkbox.blockSignals(True)
            checkbox.setChecked(self.startup.enabled())
            checkbox.blockSignals(False)
            self.window.error('STARTUP_SAVE_FAILED')

    def refresh_tray_availability(self):
        available = self.tray.available()
        if self.window.tray_available and not available:
            self.window.activate()
        self.window.tray_available = available
        self.window.settings_page.close_to_tray.setEnabled(available)
        self.window.close_to_tray = available and self.preferences.value('close_to_tray',True,type=bool)

    def window_closed(self):
        if self.window.close_to_tray and self.tray.available() and not self.window.isVisible():
            if not self.preferences.value('tray_notice_seen',False,type=bool):
                self.tray.icon.showMessage('Agent Light','仍在后台运行，可从托盘菜单退出。')
                self.preferences.setValue('tray_notice_seen',True)
        else:
            self.request_exit()

    def request_exit(self):
        if self.exiting:
            return
        self.exiting = True
        self.exit_started = time.monotonic()
        self.window.banner.setText('正在退出，等待后台和在途操作完成…')
        self.window.banner.show()
        self.window.stack.setEnabled(False)
        if self.client:
            self.client.close()
        if self.runtime:
            self.runtime.request_stop()

    def tick(self):
        if self.exiting:
            if (self.runtime is None or self.runtime.is_stopped()) and not self.tasks.jobs:
                self.tray.icon.hide()
                self.instance.close()
                self.timer.stop()
                self.window.final_close = True
                self.window.close()
                self.application.quit()
            elif time.monotonic()-self.exit_started > 5:
                self.window.error('SHUTDOWN_TIMEOUT')
                self.window.show()
            return
        self.refresh_tray_availability()
        if self.runtime and self.runtime.state == 'FAILED':
            self.window.error((self.runtime.startup_error or {}).get('code','SERVICE_START_FAILED'))
            self.invalidate()
            return
        if self.runtime and self.runtime.is_running() and not self.started_polling:
            self.started_polling = True
            self.window.banner.hide()
            self.call('health',tag='health')
            self.call('config/display',tag='load_display')
            self.scan(False)
            self.refresh()
            self.plugin_action('detect',agent_id='dsh')
        interval = .25 if self.snapshot.get('display_test',{}).get('state')=='running' else 2 if self.window.isVisible() else 5
        if self.started_polling and time.monotonic()-self.last_poll >= interval:
            self.refresh()

    def call(self, route, method='GET', body=None, tag=None):
        if not self.client or self.exiting:
            return False
        accepted = self.client.request(route,method,body,tag=tag)
        if accepted and method != 'GET':
            self.client.invalidate('status')
            self.invalidate()
            if tag == 'connect':
                self.window.device_page.connect_button.setEnabled(False)
        return accepted

    def refresh(self):
        if self.call('status',tag='status'):
            self.last_poll = time.monotonic()

    def scan(self, include_all):
        if self.call('devices?include_all='+str(include_all).lower(),tag='scan'):
            self.window.device_page.scan_button.setEnabled(False)

    def response(self, tag, body):
        if self.exiting:
            return
        if tag == 'status':
            self.snapshot, self.fresh, self.failures = body, True, 0
            self.window.status_page.update_snapshot(body)
            self.window.device_page.update_snapshot(body)
            running = body.get('display_test',{}).get('state') == 'running'
            self.window.settings_page.save_button.setEnabled(not running)
            self.tray.update(overview(body),body.get('device',{}).get('confirmed',False) and not running)
        elif tag == 'scan':
            self.window.device_page.show_devices(body['devices'])
        elif tag == 'load_display':
            self.window.settings_page.set_display(body)
        elif tag == 'save_display':
            self.cfg.update({k:body[k] for k in ('brightness','completedHoldSeconds')})
            self.window.settings_page.saved.setText('配置已保存，后台已应用；设备确认请查看状态页。')
            self.refresh()
        elif tag == 'health':
            self.window.endpoint_label.setText(self.cfg['endpoint']+' · 服务 '+body.get('service_version','—'))
        else:
            if tag == 'connect':
                self.window.device_page.validate()
                self.window.device_page.detail.setText('连接意图已保存，正在连接…')
            self.refresh()

    def invalidate(self):
        self.fresh = False
        self.window.status_page.update_snapshot(self.snapshot,fresh=False,failures=self.failures)
        self.window.device_page.update_snapshot(self.snapshot,fresh=False)
        self.tray.update(overview(fresh=False,failures=self.failures),False)

    def failure(self, tag, code):
        if tag == 'status':
            self.failures += 1
            self.invalidate()
        elif tag == 'scan':
            self.window.device_page.scan_button.setEnabled(True)
        elif tag == 'connect':
            self.window.device_page.validate()
        self.window.error(code)

    def plugin_action(self, action, *, agent_id='dsh'):
        if self.cfg is None or self.exiting:
            return
        from .plugin_controller import plugin_action
        plugin_action(self,action,agent_id)


def main():
    parser = argparse.ArgumentParser(prog='agent-light-desktop')
    parser.add_argument('--config',type=Path,default=default_path())
    parser.add_argument('--minimized',action='store_true')
    parser.add_argument('--prepare-uninstall',action='store_true')
    parser.add_argument('--smoke-test',action='store_true',help=argparse.SUPPRESS)
    args = parser.parse_args()
    application = QApplication(sys.argv)
    application.setQuitOnLastWindowClosed(False)
    application.setApplicationName('Agent Light')
    application.setWindowIcon(app_icon())
    if args.smoke_test:
        validate_plugin()
        from ..integrations.dsh import discover, inspect_host
        paths = discover()
        detected = inspect_host(paths.get('entry'),paths.get('node'))
        from importlib.metadata import version
        from ..core import SCHEMA
        assert SCHEMA and version('agent-light')
        window = MainWindow()
        # Exercise the frozen catalogue and each registered panel, without actions.
        saved = window.plugins_page.dsh_page.values()
        for agent_id in window.plugins_page.panels:
            assert window.navigate('integrations',agent_id)
            assert window.plugins_page.current_agent_id == agent_id
        assert window.plugins_page.dsh_page.values() == saved
        window.navigate('integrations','dsh')
        window.show()
        def finish_smoke():
            if getattr(sys,'frozen',False):
                (Path(sys.executable).parent/'smoke-result.txt').write_text(
                    'PASS: Agent navigation, Qt, resources, schema, metadata, frozen external Node: '+str(detected.get('compatible'))+
                    ' / '+str(detected.get('error_code')),encoding='utf-8')
            window.final_close = True
            window.close()
            application.quit()
        QTimer.singleShot(500,finish_smoke)
        return application.exec()
    instance = DesktopInstance(args.config)
    try:
        if not instance.acquire():
            return 1 if args.prepare_uninstall else 0
    except ValueError as exc:
        QMessageBox.critical(None,'Agent Light',str(exc))
        return 1
    if args.prepare_uninstall:
        from .plugin_controller import prepare_uninstall
        try:
            return prepare_uninstall()
        finally:
            instance.close()
    controller = DesktopController(application,args,instance)
    application.aboutToQuit.connect(controller.preferences.sync)
    return application.exec()


if __name__ == '__main__':
    sys.exit(main())

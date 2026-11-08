import argparse
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from agent_light.config import save_atomic, load
from agent_light.desktop.app import DesktopController
from agent_light.desktop.instance import DesktopInstance
from test_runtime import configuration

APP=QApplication.instance() or QApplication([])


def spin(predicate,timeout=6):
    deadline=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>deadline:
            raise AssertionError('Qt lifecycle condition timed out')
        QTest.qWait(20)
        time.sleep(.005)  # Release the GIL for QRunnable Python callbacks in this QTest harness.


class DesktopLifecycleChecks(unittest.TestCase):
    def test_async_start_config_save_and_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            config=root/'config.json'
            save_atomic(config,configuration(root))
            settings=QSettings(str(root/'desktop.ini'),QSettings.Format.IniFormat)
            settings.setValue('dsh/entry','C:/Saved DSH/lib/bin.js')
            settings.setValue('integrations/selected_agent','workbuddy')
            with patch('agent_light.desktop.instance.default_path',return_value=root/'config.json'), \
                 patch('agent_light.desktop.app.QSettings',return_value=settings), \
                 patch('agent_light.desktop.tray.QSystemTrayIcon.isSystemTrayAvailable',return_value=False), \
                 patch.object(DesktopController,'plugin_action'):
                instance=DesktopInstance(config)
                self.assertTrue(instance.acquire())
                controller=DesktopController(APP,argparse.Namespace(config=config,minimized=True),instance)
                try:
                    spin(lambda:controller.fresh)
                    self.assertTrue(controller.window.isVisible())
                    self.assertEqual(controller.window.status_page.values[0].text(),'服务在线')
                    self.assertFalse(controller.window.device_page.test_button.isEnabled())
                    self.assertEqual(controller.window.plugins_page.current_agent_id,'workbuddy')
                    self.assertEqual(controller.window.plugins_page.dsh_page.paths['entry'].text(),'C:/Saved DSH/lib/bin.js')
                    controller.window.navigate('integrations','codex')
                    self.assertTrue(controller.runtime.is_running())
                    self.assertEqual(settings.value('integrations/selected_agent'),'codex')
                    self.assertEqual(load(config)['brightness'],35)
                    controller.call('config/display','PATCH',{'brightness':60},tag='save_display')
                    spin(lambda:'配置已保存' in controller.window.settings_page.saved.text())
                    self.assertEqual(load(config)['brightness'],60)
                    controller.request_exit()
                    spin(lambda:controller.runtime.is_stopped() and not controller.timer.isActive())
                    self.assertFalse(controller.tasks.jobs)
                finally:
                    controller.request_exit()
                    spin(lambda:controller.runtime is None or controller.runtime.is_stopped())
                    controller.timer.stop()
                    instance.close()
                    controller.window.final_close=True
                    controller.window.close()

    def test_second_instance_activates_with_config_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('agent_light.desktop.instance.default_path',return_value=root/'default.json'):
                first=DesktopInstance(root/'a.json')
                self.assertTrue(first.acquire())
                received=[]
                first.activate.connect(received.append)
                second=DesktopInstance(root/'b.json')
                try:
                    self.assertFalse(second.acquire())
                    spin(lambda:bool(received))
                    self.assertEqual(received,[str((root/'b.json').resolve())])
                finally:
                    first.close()

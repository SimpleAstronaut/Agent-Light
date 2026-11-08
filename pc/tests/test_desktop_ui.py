import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QTcpServer, QHostAddress
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from agent_light.desktop.client import ApiClient
from agent_light.desktop.main_window import MainWindow
from agent_light.desktop.models import reporting, overview
from agent_light.desktop.startup import StartupManager

APP = QApplication.instance() or QApplication([])


class DesktopChecks(unittest.TestCase):
    def test_summary_does_not_infer_reporting_or_device_confirmation(self):
        row = dict(agent='dsh',management_state='enabled',health='healthy',lease_expired=False,last_heartbeat_at=None)
        self.assertNotEqual(reporting([row]),'上报正常')
        self.assertEqual(reporting([{**row,'last_heartbeat_at':'now'}]),'上报正常')
        self.assertEqual(reporting([{**row,'last_heartbeat_at':'now'}, {**row,'lease_expired':True}]),'上报异常')
        self.assertEqual(reporting([{**row,'management_state':'disabled'}]),'来源已停用')
        stale = overview({'device':{'confirmed':True},'desired':'COMPLETED'},fresh=False,failures=1)
        self.assertNotIn('灯板已确认', stale)

    def test_navigation_device_and_test_rendering(self):
        window = MainWindow()
        window.show()
        try:
            QTest.qWait(40)
            for index,section in enumerate(('status','device','integrations','settings')):
                window.navigate(section)
                self.assertEqual(window.stack.currentIndex(),index)
            page = window.device_page
            page.mode.setCurrentIndex(1)
            self.assertFalse(page.connect_button.isEnabled())
            page.show_devices([dict(port='COM_TEST',description='Fake device',matched=True)])
            self.assertTrue(page.connect_button.isEnabled())
            page.update_snapshot(dict(device=dict(confirmed=True,connected=True,state='CONNECTED'),display_test=dict(state='running',stage='yellow',stage_results=[])))
            self.assertFalse(page.test_button.isEnabled())
            self.assertIn('yellow',page.test_status.text())
            page.update_snapshot({},fresh=False)
            self.assertFalse(page.test_button.isEnabled())
            window.close_to_tray = True
            window.tray_available = True
            window.close()
            self.assertFalse(window.isVisible())
        finally:
            window.final_close = True
            window.close()

    def test_network_timeout_releases_reply_and_no_proxy(self):
        server = QTcpServer()
        self.assertTrue(server.listen(QHostAddress.SpecialAddress.LocalHost,0))
        sockets = []
        server.newConnection.connect(lambda: sockets.append(server.nextPendingConnection()))
        client = ApiClient(f'http://127.0.0.1:{server.serverPort()}','synthetic-token')
        failures = []
        client.failure.connect(lambda tag,code: failures.append((tag,code)))
        try:
            self.assertTrue(client.request('status'))
            self.assertFalse(client.request('status'))
            QTest.qWait(2300)
            self.assertEqual(failures,[('status','SERVICE_UNAVAILABLE')])
            self.assertFalse(client.pending)
        finally:
            client.close()
            for socket in sockets:
                socket.close()
            server.close()

    def test_startup_command_quotes_custom_config(self):
        manager = StartupManager('C:/Example 中文/User Files/config.json', executable='C:/Example Program/AgentLight.exe')
        self.assertIn('"',manager.command())
        self.assertIn('--minimized --config', manager.command())
        self.assertIn('config.json"',manager.command())
        class Key:
            def __enter__(self): return self
            def __exit__(self,*args): return False
        class Registry:
            HKEY_CURRENT_USER = 0
            REG_SZ = 1
            values = {}
            def OpenKey(self,*args): return Key()
            def CreateKey(self,*args): return Key()
            def QueryValueEx(self,key,name):
                if name not in self.values: raise FileNotFoundError()
                return self.values[name],1
            def SetValueEx(self,key,name,reserved,kind,value): self.values[name]=value
            def DeleteValue(self,key,name): self.values.pop(name)
        fake = Registry()
        manager.registry = fake
        manager.available = True
        manager.set_enabled(True)
        self.assertTrue(manager.enabled())
        fake.values['AgentLight'] = 'user-changed-command'
        manager.set_enabled(False)
        self.assertEqual(fake.values['AgentLight'],'user-changed-command')

import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from agent_light.desktop.main_window import MainWindow
from agent_light.desktop.plugin_controller import plugin_action

APP = QApplication.instance() or QApplication([])


class Preferences:
    def __init__(self):
        self.values = {}

    def setValue(self,key,value):
        self.values[key] = value


class DeferredTasks:
    def __init__(self):
        self.jobs = []

    def submit(self,function,result,error):
        self.jobs.append(SimpleNamespace(function=function,result=result,error=error))


class AgentNavigationChecks(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()
        self.controller = SimpleNamespace(window=self.window,preferences=Preferences(),
            tasks=DeferredTasks(),config_path=Path('unused-test-config.json'),cfg={},exiting=False)

    def tearDown(self):
        self.window.final_close = True
        self.window.close()

    def test_subpages_preserve_dsh_input_and_selection_has_no_actions(self):
        page = self.window.plugins_page
        self.assertEqual(set(page.panels),{'dsh','codex','zcode','workbuddy'})
        page.dsh_page.paths['entry'].setText('C:/Unsaved DSH/lib/bin.js')
        page.dsh_page.output.setPlainText('prior inspection result')
        actions = []
        page.action.connect(lambda agent,action:actions.append((agent,action)))
        for agent in page.panels:
            self.assertTrue(self.window.navigate('integrations',agent))
            self.assertEqual(self.window.stack.currentIndex(),2)
            self.assertIs(page.stack.currentWidget(),page.panels[agent])
        self.assertFalse(actions)
        for agent in ('codex','zcode','workbuddy'):
            buttons = page.panels[agent].buttons
            self.assertFalse(buttons['install'].isEnabled())
            self.assertFalse(buttons['generate'].isEnabled())
            self.assertFalse(buttons['uninstall'].isEnabled())
            self.assertEqual(buttons['detect'].isEnabled(),agent=='codex')
        self.window.navigate('integrations','dsh')
        self.assertEqual(page.dsh_page.paths['entry'].text(),'C:/Unsaved DSH/lib/bin.js')
        self.assertEqual(page.dsh_page.output.toPlainText(),'prior inspection result')
        QTest.mouseClick(page.dsh_page.buttons[0],Qt.MouseButton.LeftButton)
        self.assertEqual(actions,[('dsh','detect')])
        self.assertFalse(self.window.navigate('integrations','unknown'))
        self.assertFalse(page.select_agent('unknown'))
        self.assertEqual(page.current_agent_id,'dsh')

    def test_late_results_stay_with_origin_and_agents_have_independent_jobs(self):
        page = self.window.plugins_page
        dsh = page.dsh_page
        dsh.paths['entry'].setText('C:/Before/lib/bin.js')
        self.assertTrue(plugin_action(self.controller,'detect','dsh'))
        self.assertFalse(plugin_action(self.controller,'detect','dsh'))
        self.assertEqual(self.controller.preferences.values['dsh/entry'],'C:/Before/lib/bin.js')
        self.window.navigate('integrations','codex')
        self.assertTrue(plugin_action(self.controller,'detect','codex'))
        self.assertEqual(len(self.controller.tasks.jobs),2)
        self.window.navigate('integrations','workbuddy')
        dsh.paths['entry'].setText('C:/Edited While Detecting/lib/bin.js')
        self.controller.tasks.jobs[1].result('Codex test version；真实适配器尚未实现')
        self.controller.tasks.jobs[0].result(({'entry':'C:/Discovered/lib/bin.js'},
                                            {'compatible':True,'detected':{}},None))
        self.assertEqual(page.current_agent_id,'workbuddy')
        self.assertIn('Codex test version',page.panels['codex'].environment_status.text())
        self.assertNotIn('Codex test version',page.panels['workbuddy'].environment_status.text())
        self.assertIn('宿主版本与指纹兼容',dsh.summary.text())
        self.assertEqual(dsh.paths['entry'].text(),'C:/Edited While Detecting/lib/bin.js')
        self.assertFalse(self.controller._integration_jobs)
        self.assertTrue(dsh.buttons[0].isEnabled())

    def test_unimplemented_or_unknown_actions_never_dispatch_to_dsh(self):
        for agent,action in (('codex','install'),('zcode','detect'),('workbuddy','generate'),('unknown','uninstall')):
            self.assertFalse(plugin_action(self.controller,action,agent))
        self.assertFalse(self.controller.tasks.jobs)
        self.assertFalse(self.controller.preferences.values)
        self.assertIn('ADAPTER_NOT_IMPLEMENTED',self.window.banner.text())

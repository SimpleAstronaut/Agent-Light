"""Synthetic 16-session/1000-event GUI+service load and slow-disk probe."""
import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'pc'),str(ROOT/'pc/tests')]
from aiohttp import ClientSession, ClientTimeout
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings,QTimer
from agent_light.desktop.app import DesktopController
from agent_light.desktop.instance import DesktopInstance
from agent_light.core import Store
from agent_light.config import save_atomic
from test_runtime import configuration
from test_devices import FakePort


class TimedPort(FakePort):
    def __init__(self):
        super().__init__()
        self.requests=[]
        self.link_losses=0

    def write(self,data):
        now=time.monotonic()
        if self.requests and now-self.requests[-1]>5:
            self.mode=3
            self.link_losses+=1
        self.requests.append(now)
        super().write(data)


def run():
    app=QApplication.instance() or QApplication([])
    result={}
    slow=threading.Event()
    observed={'slow_ui_invalidated':False}
    port=TimedPort()
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        cfg=configuration(root)
        config=root/'config.json'
        save_atomic(config,cfg)
        settings=QSettings(str(root/'prefs.ini'),QSettings.Format.IniFormat)
        with patch('agent_light.desktop.instance.default_path',return_value=config), \
             patch('agent_light.desktop.app.QSettings',return_value=settings), \
             patch('agent_light.desktop.tray.QSystemTrayIcon.isSystemTrayAvailable',return_value=False), \
             patch.object(DesktopController,'plugin_action'), \
             patch('agent_light.serial_link.SerialWorker.open',return_value=port):
            instance=DesktopInstance(config)
            assert instance.acquire()
            controller=DesktopController(app,argparse.Namespace(config=config,minimized=False),instance)
            async def load():
                sequence=0
                latency=[]
                loop_delays=[]
                monitoring=True
                async def monitor():
                    while monitoring:
                        start=time.monotonic()
                        await asyncio.sleep(.05)
                        loop_delays.append(max(0,time.monotonic()-start-.05))
                monitored=asyncio.run_coroutine_threadsafe(monitor(),controller.runtime._loop)
                async with ClientSession(timeout=ClientTimeout(total=15),trust_env=False,
                                         headers={'Authorization':'Bearer test-token'}) as client:
                    def event(kind,session,turn):
                        nonlocal sequence
                        sequence+=1
                        return dict(schema_version=1,event_id=f'e{sequence}',agent='dsh',channel='plugin',producer_id='synthetic',
                            runtime_id='r',runtime_seq=1,producer_seq=sequence,session_id=f's{session}',instance_id=f'i{session}',instance_seq=1,
                            turn_id=f't{turn}' if turn else None,turn_seq=turn,attention_id=None,type=kind,
                            occurred_at='2026-11-08T00:00:00Z',reason_code=None)
                    async def send(body):
                        start=time.monotonic()
                        async with client.post(cfg['endpoint']+'/v1/events',json=body) as response:
                            assert response.status==200, (response.status,await response.text())
                            await response.read()
                        return time.monotonic()-start
                    for i in range(16):
                        await send(event('session_start',i,0))
                    sequence+=1
                    await send(dict(schema_version=1,event_id='ready',agent='dsh',producer_id='synthetic',runtime_id='r',
                                    runtime_seq=1,producer_seq=sequence,type='runtime_ready',live_instances=[f'i{i}' for i in range(16)]))
                    async def heartbeat():
                        while True:
                            async with client.post(cfg['endpoint']+'/v1/producers/heartbeat',json=dict(agent='dsh',producer_id='synthetic',
                                runtime_id='r',runtime_seq=1,health='healthy',persisted_seq=sequence,acked_seq=sequence)) as response:
                                await response.read()
                            await asyncio.sleep(2)
                    beating=asyncio.create_task(heartbeat())
                    try:
                        for n in range(1000):
                            latency.append(await send(event('turn_start' if n%32<16 else 'turn_complete',n%16,1+n//32)))
                            await asyncio.sleep(.01)
                        normal_requests=list(port.requests)
                        monitoring=False
                        await asyncio.wrap_future(monitored)
                        normal_delays=list(loop_delays)
                        original=Store.persist
                        delayed=False
                        def persist(store):
                            nonlocal delayed
                            if not delayed:
                                delayed=True
                                slow.set()
                                time.sleep(5.3)
                            return original(store)
                        sets_before=len(port.sets)
                        with patch.object(Store,'persist',persist):
                            await send(event('turn_start',0,1000))
                        deadline=time.monotonic()+5
                        reconfirmed=False
                        while time.monotonic()<deadline:
                            async with client.get(cfg['endpoint']+'/v1/status') as response:
                                status=await response.json()
                            if status['device']['confirmed'] and len(port.sets)>sets_before:
                                reconfirmed=True
                                break
                            await asyncio.sleep(.1)
                        slow.clear()
                    finally:
                        beating.cancel()
                        await asyncio.gather(beating,return_exceptions=True)
                        monitoring=False
                    p95=sorted(latency)[int(len(latency)*.95)-1]
                    max_gap=max(b-a for a,b in zip(normal_requests,normal_requests[1:]))
                    output=dict(sessions=16,backlog_events=1000,http_p95_ms=round(p95*1000,3),
                                http_max_ms=round(max(latency)*1000,3),service_loop_max_delay_ms=round(max(normal_delays)*1000,3),
                                normal_usb_max_interval_s=round(max_gap,3),slow_disk_seconds=5.3,
                                slow_disk_ui_invalidated=observed['slow_ui_invalidated'],slow_disk_reconfirmed_after_set=reconfirmed,
                                slow_disk_link_loss_observed=port.link_losses>0)
                    assert p95<.2 and max_gap<2,output
                    assert observed['slow_ui_invalidated'] and reconfirmed and port.link_losses>0,output
                    return output
            def done(value):
                result.update(value)
                controller.request_exit()
            def failed(code):
                result['error']=code
                controller.request_exit()
            launched=False
            def tick():
                nonlocal launched
                if slow.is_set() and not controller.fresh:
                    observed['slow_ui_invalidated']=True
                if controller.fresh and not launched:
                    launched=True
                    controller.tasks.submit(lambda:asyncio.run(load()),done,failed)
            timer=QTimer()
            timer.timeout.connect(tick)
            timer.start(50)
            QTimer.singleShot(60000,lambda:failed('LOAD_PROBE_TIMEOUT'))
            app.exec()
            timer.stop()
            assert controller.runtime and controller.runtime.is_stopped()
    (ROOT/'outputs/desktop-load-results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    assert 'error' not in result,result


if __name__=='__main__':
    run()

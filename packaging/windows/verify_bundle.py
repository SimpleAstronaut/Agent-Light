"""Run distribution checks in a source-free directory. Uses synthetic data only."""
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'pc'))
from agent_light.runtime import ServiceRuntime
from agent_light.desktop.resources import validate_plugin
from agent_light.desktop.processes import run_readonly


def verify(source, destination):
    root = Path(destination).resolve()
    shutil.copytree(source, root, dirs_exist_ok=True)
    validate_plugin(root / 'resources/plugins/dsh')
    smoke_log = root / 'smoke-result.txt'
    smoke_log.unlink(missing_ok=True)
    subprocess.run([str(root / 'AgentLight.exe'), '--smoke-test'], cwd=root, timeout=20, check=True)
    if smoke_log.exists():
        assert smoke_log.read_text(encoding='utf-8').startswith('PASS'), smoke_log.read_text(encoding='utf-8')
    node = shutil.which('node')
    code, out, err = run_readonly([node, root / 'resources/plugins/dsh/tools/inspect-host.mjs',
                                   root / 'missing/lib/bin.js'], cwd=root)
    assert json.loads(out)['error_code'] == 'HOST_NOT_FOUND', out
    script = root / 'worker-smoke.mjs'
    script.write_text("""import {Reporter} from './resources/plugins/dsh/dist/reporter.js';
import {writeFileSync,mkdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
writeFileSync('fake-token','synthetic-token');mkdirSync('fake-outbox',{recursive:true});
const reporter=new Reporter({endpoint:'http://127.0.0.1:1',
tokenFile:fileURLToPath(new URL('./fake-token',import.meta.url)),
dataDir:fileURLToPath(new URL('./fake-outbox',import.meta.url))});
try{const ready=await reporter.start();if(!ready.key)throw Error('NOT_READY');console.log('WORKER_READY');}
finally{await reporter.close();}
""", encoding='utf-8')
    code, out, err = run_readonly([node, script], cwd=root)
    assert code == 0 and 'WORKER_READY' in out, (code, out, err)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td)
        (path / 'token').write_text('synthetic-token')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        cfg = dict(endpoint=f'http://127.0.0.1:{port}', tokenFile=str(path / 'token'),
                   database=str(path / 'state.db'), dataDir=str(path / 'outbox'), brightness=35,
                   completedHoldSeconds=300, vid=0x0483, pid=0x5740, port=None,
                   serialNumber='no-such-device')
        config = path / 'config.json'
        config.write_text(json.dumps(cfg), encoding='utf-8')
        runtime = ServiceRuntime(cfg, config_path=config)
        runtime.start()
        try:
            limit = time.monotonic() + 4
            while runtime.state == 'STARTING' and time.monotonic() < limit:
                time.sleep(.01)
            assert runtime.is_running(), runtime.startup_error
            for command in ('health', 'status'):
                result = subprocess.run([str(root / 'agent-light.exe'), '--config', str(config), command],
                                        cwd=root, capture_output=True, timeout=10)
                assert result.returncode == 0, result.stderr
                assert isinstance(json.loads(result.stdout), dict)
        finally:
            runtime.request_stop()
            assert runtime.wait_stopped(5)
    worker = root / 'resources/plugins/dsh/dist/worker.js'
    worker.rename(worker.with_suffix('.missing'))
    try:
        try:
            validate_plugin(root / 'resources/plugins/dsh')
        except ValueError:
            pass
        else:
            raise AssertionError('Missing worker accepted')
    finally:
        worker.with_suffix('.missing').rename(worker)
    print('PASS: Qt, CLI health/status, schema/metadata, complete plugin, inspect-host, Worker, Unicode path')


if __name__ == '__main__':
    verify(sys.argv[1], sys.argv[2])

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from .config import default_path, initialize, load


def main():
    p = argparse.ArgumentParser(prog='agent-light')
    p.add_argument('--config', type=Path, default=default_path())
    p.add_argument('command', choices=['init','serve','status','health','clear','test','event','overlay'])
    p.add_argument('--package', type=Path, default=Path(__file__).resolve().parents[2] / 'plugins/dsh')
    p.add_argument('--installed', action='store_true', help='overlay overrides an already installed bundle node')
    args = p.parse_args()
    if args.command == 'init':
        initialize(args.config)
        print(args.config.resolve())
        return
    cfg = load(args.config)
    if args.command == 'serve':
        from .api import serve
        serve(cfg)
        return
    if args.command == 'overlay':
        indent = '  ' if args.installed else '      '
        if args.installed:
            print('- id: agent-light-dsh')
        else:
            entry = (args.package / 'dist' / 'index.js').resolve()
            if not entry.is_file():
                p.exit(1, 'PLUGIN_BUILD_MISSING: ' + str(entry) + '\n')
            print('- insert:\n    - id: agent-light-dsh\n      name: ' + json.dumps(entry.as_uri()))
        print(indent + 'disabled: false\n' + indent + 'config:')
        for k in ('endpoint','tokenFile','dataDir'):
            print(indent + '  ' + k + ': ' + json.dumps(cfg[k]))
        return
    route = {'status':'status','health':'health','clear':'display/clear','test':'display/test','event':'events'}[args.command]
    payload = sys.stdin.buffer.read(2049) if args.command == 'event' else b'{}' if args.command in ('clear','test') else None
    req = urllib.request.Request(cfg['endpoint'] + '/v1/' + route, data=payload,
        headers={'Authorization':'Bearer ' + Path(cfg['tokenFile']).read_text().strip(), 'Content-Type':'application/json'})
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=.2 if args.command=='event' else 2) as response:
            if args.command != 'event':
                print(response.read().decode())
    except Exception:
        if args.command != 'event':
            p.exit(1, 'SERVICE_UNAVAILABLE\n')


if __name__ == '__main__':
    main()

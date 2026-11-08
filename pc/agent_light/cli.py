import argparse
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from .config import default_path, initialize, load


def main():
    p = argparse.ArgumentParser(prog='agent-light')
    p.add_argument('--config', type=Path, default=default_path())
    p.add_argument('command', choices=['init','serve','status','health','clear','test','event','overlay'])
    from .desktop.resources import plugin_root
    p.add_argument('--package', type=Path, default=plugin_root())
    p.add_argument('--installed', action='store_true', help='overlay overrides an already installed bundle node')
    args = p.parse_args()
    if args.command == 'init':
        initialize(args.config)
        print(args.config.resolve())
        return
    cfg = load(args.config)
    if args.command == 'serve':
        from .api import serve
        serve(cfg, config_path=args.config.resolve())
        return
    if args.command == 'overlay':
        from .integrations.dsh import generate_dsh_overlay
        try:
            print(generate_dsh_overlay(cfg, args.package, args.installed), end='')
        except ValueError as error:
            p.exit(1, str(error)+'\n')
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
    except urllib.error.HTTPError as exc:
        try:
            if args.command != 'event':
                if exc.code in (401, 403):
                    p.exit(4, 'AUTH_FAILED\n')
                allowed = {'DEVICE_NOT_READY', 'DISPLAY_TEST_RUNNING', 'INVALID_REQUEST',
                           'DEVICE_BUSY', 'SERVICE_STOPPING', 'CONFIG_SAVE_FAILED',
                           'CONFIG_CHANGED_EXTERNALLY', 'INVALID_DISPLAY_CONFIG',
                           'CONFIG_PATH_REQUIRED', 'PRODUCER_DISABLED'}
                try:
                    code = json.loads(exc.read(4096))['error']['code']
                    code = code if code in allowed else 'HTTP_ERROR'
                except (ValueError, KeyError, TypeError):
                    code = 'HTTP_ERROR'
                p.exit(3 if args.command == 'test' and code in
                       ('DEVICE_NOT_READY', 'DISPLAY_TEST_RUNNING') else 1, code + '\n')
        finally:
            exc.close()
    except (urllib.error.URLError, TimeoutError, OSError):
        if args.command != 'event':
            p.exit(1, 'SERVICE_UNAVAILABLE\n')


if __name__ == '__main__':
    main()

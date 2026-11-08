import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path

root=Path(__file__).resolve().parents[2]
lock=json.loads((root/'packaging/windows/runtime-lock.json').read_text(encoding='utf-8'))
errors=[]
if sys.platform!='win32' or platform.machine().lower() not in ('amd64','x86_64') or platform.python_version()!='3.14.0':
    errors.append('Windows x64 CPython 3.14.0 required')
for item in lock['dependencies']:
    try:
        if version(item['name'])!=item['version']:
            errors.append(item['name']+' version mismatch')
    except Exception:
        errors.append(item['name']+' missing')
typescript=root/'plugins/dsh/node_modules/typescript/package.json'
if not typescript.is_file() or json.loads(typescript.read_text(encoding='utf-8'))['version']!=lock['typescript']:
    errors.append('TypeScript version mismatch')
if errors:
    raise SystemExit('\n'.join(errors))
print('Verified locked Python/Qt/build dependencies and TypeScript versions')

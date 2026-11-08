"""Publish the complete plugin tree beside the onedir executables, with hashes."""
import hashlib
import json
import shutil
import sys
from importlib.metadata import distribution, PackageNotFoundError
from pathlib import Path
root = Path(__file__).resolve().parents[2]
target = Path(sys.argv[1]).resolve() / 'resources'
plugin = target / 'plugins/dsh'
plugin.mkdir(parents=True, exist_ok=True)
source = root / 'plugins/dsh'
shutil.copytree(source/'dist', plugin/'dist', dirs_exist_ok=True)
shutil.copytree(source/'tools', plugin/'tools', dirs_exist_ok=True)
shutil.copy2(source/'package.json', plugin/'package.json')
manifest = {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in plugin.rglob('*') if p.is_file()}
(target/'resource-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
licenses = Path(sys.argv[1]).resolve() / 'licenses'
licenses.mkdir(exist_ok=True)
lock = json.loads((root/'packaging/windows/runtime-lock.json').read_text(encoding='utf-8'))
for item in lock['dependencies']:
    try:
        dist = distribution(item['name'])
    except PackageNotFoundError:
        continue
    for filename in dist.files or []:
        name = str(filename).lower()
        if ('license' in name or 'copying' in name or 'notice' in name) and '.dist-info/' in name:
            source = Path(dist.locate_file(filename))
            if source.is_file():
                destination = licenses / item['name'] / str(filename).split('.dist-info/',1)[-1]
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,destination)
shutil.copytree(root/'packaging/windows/licenses',licenses/'Qt',dirs_exist_ok=True)
python_license = Path(sys.base_prefix)/'LICENSE.txt'
if python_license.is_file():
    shutil.copy2(python_license,licenses/'CPython-LICENSE.txt')
shutil.copy2(root/'THIRD_PARTY_NOTICES.md',Path(sys.argv[1])/'THIRD_PARTY_NOTICES.md')
shutil.copy2(root/'LICENSE',Path(sys.argv[1])/'LICENSE')
shutil.copy2(root/'docs/desktop-guide.md',Path(sys.argv[1])/'desktop-guide.md')
shutil.copy2(root/'docs/user-manual.md',Path(sys.argv[1])/'user-manual.md')
shutil.copy2(root/'docs/installation-guide.md',Path(sys.argv[1])/'installation-guide.md')
history = Path(sys.argv[1])/'superpowers/plans'
history.mkdir(parents=True,exist_ok=True)
shutil.copy2(root/'docs/superpowers/plans/2026-11-08-desktop-ui-progress.md',history/'2026-11-08-desktop-ui-progress.md')

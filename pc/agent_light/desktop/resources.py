import hashlib
import json
import os
import sys
from pathlib import Path

REQUIRED_PLUGIN_FILES = ('package.json', 'dist/index.js', 'dist/reporter.js', 'dist/worker.js',
                         'dist/adapter-0.2.1-rc.2.js', 'dist/host-lock.js', 'dist/types.js',
                         'tools/inspect-host.mjs')


def plugin_root():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / 'resources/plugins/dsh'
    return Path(__file__).resolve().parents[3] / 'plugins/dsh'


def validate_plugin(root=None):
    root = Path(root) if root is not None else plugin_root()
    missing = [name for name in REQUIRED_PLUGIN_FILES if not (root / name).is_file()]
    if missing:
        raise ValueError('PLUGIN_BUILD_MISSING: ' + ', '.join(missing))
    if json.loads((root / 'package.json').read_text(encoding='utf-8')).get('type') != 'module':
        raise ValueError('PLUGIN_BUILD_MISSING: package.json type')
    manifest = root.parents[1] / 'resource-manifest.json'
    if getattr(sys, 'frozen', False) and not manifest.is_file():
        raise ValueError('PLUGIN_BUILD_MISSING: resource-manifest.json')
    if manifest.is_file():
        for name, digest in json.loads(manifest.read_text(encoding='utf-8')).items():
            path = manifest.parent / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('PLUGIN_BUILD_MISSING: ' + name)
    return root.resolve()


def canonical(path):
    return os.path.normcase(str(Path(path).resolve()))


def integration_root(config_path):
    from ..config import default_path
    path = Path(config_path).resolve()
    if canonical(path) == canonical(default_path()):
        return default_path().parent / 'integrations'
    identity = hashlib.sha256(canonical(path).encode('utf-8')).hexdigest()
    return path.parent / 'integrations' / identity

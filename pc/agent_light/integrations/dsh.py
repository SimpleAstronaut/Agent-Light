import difflib
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from ..config import default_path, load
from ..locking import ProcessLock
from ..desktop.processes import run_readonly
from ..desktop.resources import canonical, integration_root, plugin_root, validate_plugin

BEGIN = '# BEGIN AGENT-LIGHT MANAGED v1'
END = '# END AGENT-LIGHT MANAGED v1'
TEMPLATES = Path(__file__).with_name('templates')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    path = Path(path)
    return digest(path.read_bytes()) if path.exists() else None


def atomic_bytes(path, data, expected=None, *, check=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if check and file_hash(path) != expected:
            raise ValueError('INSTALLER_CONCURRENT_CHANGE')
        if path.exists() and os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            replace = ctypes.WinDLL('kernel32',use_last_error=True).ReplaceFileW
            replace.argtypes = [wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.DWORD,wintypes.LPVOID,wintypes.LPVOID]
            replace.restype = wintypes.BOOL
            if not replace(str(path.resolve()),name,None,0,None,None):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            if path.exists():
                os.chmod(name,path.stat().st_mode & 0o777)
            os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)


def write_json(path, value):
    atomic_bytes(path,(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))


def index_path():
    return default_path().parent / 'integrations/config-index.json'


def read_index():
    path = index_path()
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def read_record(config_path):
    path = integration_root(config_path) / 'dsh-installation.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def discover(previous=None):
    result = dict(previous or {})
    for key in ('entry','node','launcher'):
        if result.get(key) and not Path(result[key]).is_file():
            result[key] = ''
    if not result.get('launcher'):
        result['launcher'] = next((str(Path(p)/'dsh-web.ps1') for p in os.environ.get('PATH','').split(os.pathsep)
                                   if (Path(p)/'dsh-web.ps1').is_file()), '')
    # Resolve literal paths in the selected wrapper, never execute it for discovery.
    wrapper = shutil.which('dsh.cmd')
    if wrapper and not result.get('entry'):
        text = Path(wrapper).read_text(encoding='utf-8',errors='replace')[:65536]
        root_line = 'for %%I in ("%~dp0..") do set "DSH_ROOT=%%~fI"'
        if text.count(root_line)==1:
            base = str(Path(wrapper).resolve().parent.parent)
            for variable,key in (('DSH_CLI','entry'),('DSH_NODE','node')):
                matches = re.findall(r'(?mi)^set "'+variable+r'=([^"\r\n]+)"\s*$',text)
                if len(matches)==1:
                    value=matches[0].replace('%DSH_ROOT%',base)
                    if '%' not in value and Path(value).is_file() and not result.get(key):
                        result[key]=str(Path(value).resolve())
        candidates = re.findall(r'([A-Za-z]:[\\/][^"\r\n]+[\\/]lib[\\/]bin\.js)', text)
        if len(candidates) == 1 and Path(candidates[0]).is_file():
            result['entry'] = candidates[0]
        # npm-generated wrappers resolve their entry relative to %dp0%.
        for candidate in (Path(wrapper).parent/'node_modules/@deepseek-ai/dsh/lib/bin.js',):
            if candidate.is_file():
                result['entry'] = str(candidate)
        nodes = re.findall(r'([A-Za-z]:[\\/][^"\r\n]+[\\/]node\.exe)',text)
        if not result.get('node') and len(nodes)==1 and Path(nodes[0]).is_file():
            result['node'] = nodes[0]
    if result.get('entry') and not result.get('node'):
        # Only infer Node beside the chosen host, never an unrelated PATH runtime.
        for parent in Path(result['entry']).resolve().parents:
            candidate = parent / 'node.exe'
            if candidate.is_file():
                result['node'] = str(candidate)
                break
    return result


def inspect_host(entry, node, package_dir=None):
    root = validate_plugin(package_dir)
    if not entry or not Path(entry).is_file():
        return dict(compatible=False,error_code='HOST_NOT_FOUND',detected={})
    if not node or not Path(node).is_file():
        return dict(compatible=False,error_code='NODE_RUNTIME_MISSING',detected={})
    code, stdout, stderr = run_readonly([node,root/'tools/inspect-host.mjs',Path(entry).resolve()],cwd=Path(entry).resolve().parent)
    try:
        result = json.loads(stdout)
        if result.get('schema_version') != 1 or not isinstance(result.get('compatible'),bool):
            raise ValueError()
    except (ValueError,AttributeError):
        raise ValueError('DETECTION_INVALID_RESULT') from None
    if code:
        raise ValueError('DETECTION_FAILED')
    return result


def detect_codex():
    command = shutil.which('codex.exe') or shutil.which('codex')
    if not command:
        return '未发现 Codex 命令；真实适配器尚未实现'
    if Path(command).suffix.lower() in ('.cmd','.bat','.ps1'):
        return '发现 Codex 命令；真实适配器尚未实现'
    try:
        code,out,err = run_readonly([command,'--version'],cwd=Path(command).parent)
        version = out.strip()[:120] if code==0 else '版本未知'
    except (OSError,ValueError):
        version = '版本检测失败'
    return '环境：'+version+'；真实适配器尚未实现'


def generate_dsh_overlay(cfg, package_dir=None, installed=False):
    root = validate_plugin(package_dir)
    indent = '  ' if installed else '      '
    prefix = '- id: agent-light-dsh\n' if installed else '- insert:\n    - id: agent-light-dsh\n      name: '+json.dumps((root/'dist/index.js').as_uri())+'\n'
    text = prefix + indent+'disabled: false\n'+indent+'config:\n'
    return text + ''.join(indent+'  '+k+': '+json.dumps(cfg[k])+'\n' for k in ('endpoint','tokenFile','dataDir'))


def generate_draft(config_path, cfg, package_dir=None):
    path = integration_root(config_path) / 'drafts/dsh-overlay.yml'
    atomic_bytes(path,generate_dsh_overlay(cfg,package_dir).encode('utf-8'))
    return path


def decode_script(raw):
    if raw.startswith(b'\xff\xfe'):
        text, encoding, bom = raw[2:].decode('utf-16le'), 'utf-16le', b'\xff\xfe'
    else:
        bom = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
        try:
            text = raw[len(bom):].decode('utf-8')
        except UnicodeError:
            raise ValueError('INSTALLER_UNSUPPORTED') from None
        encoding = 'utf-8'
    newline = '\r\n' if '\r\n' in text else '\n'
    if '\x00' in text or '\r' in text.replace('\r\n',''):
        raise ValueError('INSTALLER_UNSUPPORTED')
    return text.replace('\r\n','\n'), encoding, bom, newline


def encode_script(text, encoding, bom, newline):
    return bom + text.replace('\n',newline).encode(encoding)


def _legacy_parts():
    source = (TEMPLATES/'legacy-unmarked.ps1').read_text(encoding='utf-8').replace('\r\n','\n')
    start = source.index('# Agent Light local integration.')
    end = source.index('$dshShouldOpen =')
    return source, source[start:end]


def _block(overlay):
    _, template = _legacy_parts()
    literal = "'"+str(Path(overlay).resolve()).replace("'","''")+"'"
    template = re.sub(r"(?m)^\$agentLightPatchPath = .*?$",lambda _: '$agentLightPatchPath = '+literal,template)
    return BEGIN+'\n'+template+END+'\n'


def _managed_range(text):
    if text.count(BEGIN)!=1 or text.count(END)!=1:
        raise ValueError('INSTALLER_UNSUPPORTED')
    start = text.index(BEGIN)
    end = text.index(END)+len(END)
    if start and text[start-1]!='\n' or text[end:end+1] not in ('','\n') or end<start:
        raise ValueError('INSTALLER_UNSUPPORTED')
    return start, end+(1 if text[end:end+1]=='\n' else 0)


def classify(text, record=None):
    if BEGIN in text or END in text:
        start,end = _managed_range(text)
        block = text[start:end]
        if record is None or digest(block.encode()) != record.get('managed_block_hash'):
            raise ValueError('INSTALLER_UNSUPPORTED')
        return 'managed-v1',start,end
    clean = (TEMPLATES/'clean.ps1').read_text(encoding='utf-8').replace('\r\n','\n')
    if text == clean:
        anchor = text.index('$dshShouldOpen =')
        return 'clean',anchor,anchor
    legacy,block = _legacy_parts()
    # Exact audited control flow; only this one quoted path literal may vary.
    pattern = r"(?m)^\$agentLightPatchPath = '(?:[^']|'')*'$"
    normalized = re.sub(pattern,"$agentLightPatchPath = '<overlay>'",text)
    if normalized == re.sub(pattern,"$agentLightPatchPath = '<overlay>'",legacy):
        start=text.index('# Agent Light local integration.')
        return 'legacy-unmarked',start,text.index('$dshShouldOpen =')
    raise ValueError('INSTALLER_UNSUPPORTED')


def _active_records():
    result = []
    for config, record_path in read_index().items():
        path = Path(record_path)
        if not path.is_file():
            raise ValueError('INTEGRATION_RECORD_MISSING')
        record = json.loads(path.read_text(encoding='utf-8'))
        if record.get('status') in ('pending','committed'):
            result.append(record)
    return result


def _ownership(config_path, launcher):
    for record in _active_records():
        if canonical(record['config_path']) == canonical(config_path):
            if canonical(record['launcher_path']) != canonical(launcher):
                raise ValueError('INTEGRATION_TARGET_CHANGED')
        elif canonical(record['launcher_path']) == canonical(launcher):
            raise ValueError('INTEGRATION_OWNED_BY_OTHER_CONFIG')


def recover_pending(config_path):
    record = read_record(config_path)
    if record is None or record.get('status') != 'pending':
        return record
    current = file_hash(record['launcher_path'])
    if record.get('operation') == 'uninstall':
        if current == record['new_file_hash']:
            record['status'] = 'detached'
        elif current == record['original_file_hash']:
            record['status'] = 'committed'
        else:
            raise ValueError('INSTALLER_ROLLBACK_REQUIRED')
        record.pop('operation', None)
        write_json(integration_root(config_path)/'dsh-installation.json',record)
        return record
    if current == record['new_file_hash'] and file_hash(record['overlay_path']) == record['overlay_hash']:
        record['status'] = 'committed'
    elif current == record['original_file_hash'] and file_hash(record['overlay_path']) == record.get('previous_overlay_hash'):
        previous = record.get('previous_record_backup')
        record = json.loads(Path(previous).read_text(encoding='utf-8')) if previous else {**record,'status':'detached'}
    else:
        raise ValueError('INSTALLER_ROLLBACK_REQUIRED')
    write_json(integration_root(config_path)/'dsh-installation.json',record)
    return record


def preview_install(config_path, cfg, *, launcher, entry, node, package_dir=None):
    root = validate_plugin(package_dir)
    host = inspect_host(entry,node,root)
    if not host['compatible']:
        raise ValueError(host.get('error_code') or 'UNSUPPORTED_VERSION')
    launcher = Path(launcher).resolve()
    _ownership(config_path,launcher)
    record = recover_pending(config_path)
    text,encoding,bom,newline = decode_script(launcher.read_bytes())
    kind,start,end = classify(text,record if record and record.get('status')=='committed' else None)
    overlay = integration_root(config_path)/'dsh-overlay.yml'
    draft = generate_draft(config_path,cfg,root)
    block = _block(overlay)
    updated = text[:start]+block+text[end:]
    # Literal extra overlay references are never silently combined with this integration.
    for literal in re.findall(r"'((?:[^']|'')+\.ya?ml)'",text[:start]+text[end:],re.IGNORECASE):
        candidate = Path(literal.replace("''","'"))
        if candidate.is_file() and 'agent-light-dsh' in candidate.read_text(encoding='utf-8',errors='replace'):
            raise ValueError('INTEGRATION_CONFLICT')
    return dict(action='install',kind=kind,config_path=str(Path(config_path).resolve()),launcher_path=str(launcher),
                entry=str(Path(entry).resolve()),node=str(Path(node).resolve()),plugin_root=str(root),
                overlay_path=str(overlay),draft_path=str(draft),original_file_hash=file_hash(launcher),
                previous_overlay_hash=file_hash(overlay),record_hash=file_hash(integration_root(config_path)/'dsh-installation.json'),
                index_hash=file_hash(index_path()),configuration_hash=file_hash(config_path),new_bytes=encode_script(updated,encoding,bom,newline),
                overlay_bytes=draft.read_bytes(),managed_block_hash=digest(block.encode()),
                diff=''.join(difflib.unified_diff(text.splitlines(True),updated.splitlines(True),fromfile=str(launcher),tofile=str(launcher)+' (planned)')))


def _backup(path, directory):
    path=Path(path)
    if not path.exists():
        return None
    directory.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    backup=directory/(path.name+'.'+stamp+'.'+file_hash(path)[:12]+'.bak')
    shutil.copy2(path,backup)
    return str(backup)


def install(preview, *, confirmed_stopped=False):
    if not confirmed_stopped:
        raise ValueError('HOST_EXIT_CONFIRMATION_REQUIRED')
    host=inspect_host(preview['entry'],preview['node'],preview['plugin_root'])
    if not host['compatible']:
        raise ValueError(host.get('error_code') or 'UNSUPPORTED_VERSION')
    config=preview['config_path']
    root=integration_root(config)
    index_path().parent.mkdir(parents=True,exist_ok=True)
    lock=ProcessLock(str(index_path())+'.lock')
    try:
        _ownership(config,preview['launcher_path'])
        record_path=root/'dsh-installation.json'
        for path,expected in ((config,preview['configuration_hash']), (preview['launcher_path'],preview['original_file_hash']),
                              (preview['overlay_path'],preview['previous_overlay_hash']),
                              (record_path,preview['record_hash']), (index_path(),preview['index_hash'])):
            if file_hash(path)!=expected:
                raise ValueError('INSTALLER_CONCURRENT_CHANGE')
        if digest(preview['new_bytes'])==preview['original_file_hash'] and digest(preview['overlay_bytes'])==preview['previous_overlay_hash']:
            return {'status':'unchanged','restart_required':True}
        backups=default_path().parent/'backups'
        launcher_backup=_backup(preview['launcher_path'],backups)
        overlay_backup=_backup(preview['overlay_path'],backups)
        previous_record_backup=_backup(record_path,backups)
        record={k:preview[k] for k in ('config_path','launcher_path','plugin_root','overlay_path','managed_block_hash','original_file_hash','previous_overlay_hash')}
        record.update(status='pending',template_version=1,backup_path=launcher_backup,overlay_backup=overlay_backup,
                      previous_record_backup=previous_record_backup,new_file_hash=digest(preview['new_bytes']),overlay_hash=digest(preview['overlay_bytes']))
        write_json(record_path,record)
        index=read_index()
        index[canonical(config)]=str(record_path)
        write_json(index_path(),index)
        wrote_overlay=wrote_launcher=False
        try:
            atomic_bytes(preview['overlay_path'],preview['overlay_bytes'],preview['previous_overlay_hash'],check=True)
            wrote_overlay=True
            atomic_bytes(preview['launcher_path'],preview['new_bytes'],preview['original_file_hash'],check=True)
            wrote_launcher=True
            if file_hash(preview['launcher_path'])!=record['new_file_hash'] or file_hash(preview['overlay_path'])!=record['overlay_hash']:
                raise ValueError('INSTALLER_CONCURRENT_CHANGE')
            record['status']='committed'
            write_json(record_path,record)
        except Exception:
            safe=True
            for changed,path,expected,backup in ((wrote_launcher,preview['launcher_path'],record['new_file_hash'],launcher_backup),
                                                 (wrote_overlay,preview['overlay_path'],record['overlay_hash'],overlay_backup)):
                if not changed:
                    continue
                if file_hash(path)!=expected:
                    safe=False
                elif backup:
                    atomic_bytes(path,Path(backup).read_bytes(),expected,check=True)
                else:
                    Path(path).unlink()
            if safe:
                if previous_record_backup:
                    atomic_bytes(record_path,Path(previous_record_backup).read_bytes())
                else:
                    write_json(record_path,{**record,'status':'detached'})
            else:
                raise ValueError('INSTALLER_ROLLBACK_REQUIRED') from None
            raise
        return {'status':'installed','restart_required':True,'backup_path':launcher_backup}
    finally:
        lock.close()


def preview_uninstall(config_path):
    record=recover_pending(config_path)
    if not record or record.get('status')=='detached':
        return dict(action='uninstall',status='detached',diff='没有已登记的活动接入。')
    launcher=Path(record['launcher_path'])
    if not launcher.is_file():
        raise ValueError('INTEGRATION_TARGET_CHANGED')
    text,encoding,bom,newline=decode_script(launcher.read_bytes())
    kind,start,end=classify(text,record)
    if kind!='managed-v1':
        raise ValueError('INSTALLER_UNSUPPORTED')
    updated=text[:start]+text[end:]
    return dict(action='uninstall',status='ready',config_path=str(Path(config_path).resolve()),record=record,
                original_file_hash=file_hash(launcher),record_hash=file_hash(integration_root(config_path)/'dsh-installation.json'),
                new_bytes=encode_script(updated,encoding,bom,newline),
                diff=''.join(difflib.unified_diff(text.splitlines(True),updated.splitlines(True),fromfile=str(launcher),tofile=str(launcher)+' (planned)')))


def uninstall(preview, *, confirmed_stopped=False):
    if preview.get('status')=='detached':
        return {'status':'detached'}
    if not confirmed_stopped:
        raise ValueError('HOST_EXIT_CONFIRMATION_REQUIRED')
    record=preview['record']
    lock=ProcessLock(str(index_path())+'.lock')
    try:
        record_path=integration_root(preview['config_path'])/'dsh-installation.json'
        if file_hash(record_path)!=preview['record_hash'] or file_hash(record['launcher_path'])!=preview['original_file_hash']:
            raise ValueError('INSTALLER_CONCURRENT_CHANGE')
        backup=_backup(record['launcher_path'],default_path().parent/'backups')
        pending={**record,'status':'pending','operation':'uninstall','original_file_hash':preview['original_file_hash'],
                 'new_file_hash':digest(preview['new_bytes']),'backup_path':backup}
        write_json(record_path,pending)
        atomic_bytes(record['launcher_path'],preview['new_bytes'],preview['original_file_hash'],check=True)
        write_json(record_path,{**record,'status':'detached','uninstall_backup':backup})
        return {'status':'detached','restart_required':True}
    finally:
        lock.close()


def managed_references(install_root=None):
    references=_active_records()
    if install_root is None:
        return references
    install_root=Path(install_root).resolve()
    return [r for r in references if Path(r['plugin_root']).resolve().is_relative_to(install_root)]

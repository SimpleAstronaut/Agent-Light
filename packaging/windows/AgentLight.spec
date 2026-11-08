from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
root = Path(SPECPATH).parents[1]
smoke = 'AGENT_LIGHT_SMOKE' in __import__('os').environ
entry = root / 'packaging/windows' / ('smoke_entry.py' if smoke else 'gui_entry.py')
datas = collect_data_files('agent_light') + copy_metadata('agent-light')
datas += [(str(root/'packaging/windows/runtime-lock.json'), '.')]
a = Analysis([str(entry)], pathex=[str(root/'pc')], binaries=[], datas=datas,
             hiddenimports=['PySide6.QtSvg'], excludes=['tkinter'], noarchive=False,
             runtime_hooks=[str(root/'packaging/windows/windows_icu.py')])
# Qt 6.10 uses the Windows ICU API. Do not collect unrelated, symbol-versioned
# ICU builds from tools on the build machine's PATH (e.g. Poppler).
qt_modules = {'qt6core.dll','qt6gui.dll','qt6widgets.dll','qt6network.dll','qt6svg.dll','qt6opengl.dll'}
qt_plugins = {'qwindows.dll','qsvg.dll','qsvgicon.dll','qmodernwindowsstyle.dll'}
def included(item):
    name = Path(item[0]).name.lower()
    path = item[0].replace('\\','/').lower()
    if name.startswith('icu'):
        return False
    if name.startswith('qt6') and name.endswith('.dll'):
        return name in qt_modules
    if '/plugins/' in path:
        return name in qt_plugins
    return True
a.binaries = [item for item in a.binaries if included(item)]
pyz = PYZ(a.pure)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AgentLight', console=False,
          icon=str(root/'packaging/windows/agent-light.ico'))
b = Analysis([str(root/'packaging/windows/cli_entry.py')], pathex=[str(root/'pc')],
             binaries=[], datas=datas, hiddenimports=[], excludes=['tkinter'], noarchive=False)
cli = EXE(PYZ(b.pure), b.scripts, [], exclude_binaries=True, name='agent-light', console=True)
coll = COLLECT(gui, cli, a.binaries, a.datas, b.binaries, b.datas, name='AgentLight')

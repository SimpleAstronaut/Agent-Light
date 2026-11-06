import json
import os
import secrets
from pathlib import Path


def default_path():
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "AgentLight" / "config.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def initialize(path):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return load(path)
    if os.name == "nt":
        import subprocess
        import getpass
        subprocess.run(["icacls", str(path.parent), "/inheritance:r", "/grant:r",
                        f"{getpass.getuser()}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
                       check=True, capture_output=True)
    else:
        path.parent.chmod(0o700)
    token = path.parent / "token"
    with token.open("x", encoding="ascii") as stream:
        stream.write(secrets.token_urlsafe(32))
    token.chmod(0o600)
    cfg = dict(endpoint="http://127.0.0.1:17321", tokenFile=str(token),
               dataDir=str(path.parent / "dsh-outbox"), database=str(path.parent / "state.sqlite3"),
               brightness=35, completedHoldSeconds=300, port=None,
               vid=0x0483, pid=0x5740, serialNumber=None)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg

param([string]$ISCC = "$PSScriptRoot/../../.tmp/inno/ISCC.exe")
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath "$PSScriptRoot/../..").Path
Push-Location -LiteralPath $projectRoot
try {
    $python = Join-Path $projectRoot 'pc/.venv/Scripts/python.exe'
    Remove-Item Env:AGENT_LIGHT_SMOKE -ErrorAction SilentlyContinue
    $env:PYTHONUTF8 = '1'
    & $python packaging/windows/verify_toolchain.py
    if ($LASTEXITCODE -ne 0) { throw 'Install the locked build requirements first' }
    Push-Location -LiteralPath (Join-Path $projectRoot 'plugins/dsh')
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Plugin build failed' }
    } finally { Pop-Location }
    & $python -m PyInstaller --noconfirm --distpath pc/dist --workpath pc/build packaging/windows/AgentLight.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    & $python packaging/windows/prepare_resources.py pc/dist/AgentLight
    if ($LASTEXITCODE -ne 0) { throw 'Resource preparation failed' }
    & $python packaging/windows/verify_bundle.py pc/dist/AgentLight '.tmp/分发 final'
    if ($LASTEXITCODE -ne 0) { throw 'Distribution verification failed' }
    & $ISCC packaging/windows/agent-light.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
} finally { Pop-Location }

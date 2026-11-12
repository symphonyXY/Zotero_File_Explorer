param([string]$IsccPath = '', [switch]$SkipTests)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$env:PYINSTALLER_CONFIG_DIR = Join-Path $projectRoot 'build\pyinstaller-config'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run scripts\dev-setup.ps1 first.' }
$version = & $python -c 'from zotero_file_explorer import __version__; print(__version__)'
if ($LASTEXITCODE -ne 0) { throw 'Version lookup failed.' }
if (-not $SkipTests) {
    & $python -m ruff check src tests scripts
    if ($LASTEXITCODE -ne 0) { throw 'Lint failed.' }
    $testTemp = Join-Path $projectRoot ('build\pytest-build-' + [guid]::NewGuid().ToString('N'))
    & $python -m pytest -q "--basetemp=$testTemp" --junitxml="docs/evidence/tests-$version.xml"
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
}
& $python scripts/check_docs.py
if ($LASTEXITCODE -ne 0) { throw 'Documentation links failed.' }
& $python scripts/check_repository.py
if ($LASTEXITCODE -ne 0) { throw 'Publication tree audit failed.' }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency integrity failed.' }
& $python -m PyInstaller --noconfirm --clean --workpath build/pyinstaller --distpath build/release installer/ZoteroFileExplorer.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
& $python scripts/package_notices.py
if ($LASTEXITCODE -ne 0) { throw 'Notices packaging failed.' }
if (-not $IsccPath) {
    $candidates = @(
        (Join-Path $projectRoot 'build\tools\inno\ISCC.exe'),
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 7\ISCC.exe"
    )
    $IsccPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $IsccPath) { throw 'Inno Setup ISCC.exe missing. Pass -IsccPath.' }
& $IsccPath "/DAppVersion=$version" installer/ZoteroFileExplorer.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
& $python scripts/verify_package.py
if ($LASTEXITCODE -ne 0) { throw 'Package verification failed.' }

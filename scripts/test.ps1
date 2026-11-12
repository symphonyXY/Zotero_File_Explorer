param()
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location -LiteralPath $projectRoot
try {
    $python = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw 'Run scripts\dev-setup.ps1 first.' }
    & $python -m ruff check src tests scripts
    $lintCode = $LASTEXITCODE
    & $python -m pytest -q
    $testCode = $LASTEXITCODE
    & $python scripts/check_docs.py
    $docsCode = $LASTEXITCODE
    Write-Output "Ruff=$lintCode pytest=$testCode docs=$docsCode"
    if ($lintCode -ne 0 -or $testCode -ne 0 -or $docsCode -ne 0) { throw 'Validation failed; see output above.' }
} finally {
    Pop-Location
}

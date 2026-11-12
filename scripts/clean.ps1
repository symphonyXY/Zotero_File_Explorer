param([switch]$DryRun, [switch]$Apply)
$ErrorActionPreference = 'Stop'
if ($DryRun -and $Apply) { throw 'Use either -DryRun or -Apply.' }
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run scripts\dev-setup.ps1 first.' }
$arguments = @((Join-Path $PSScriptRoot 'clean_project.py'))
if ($Apply) { $arguments += '--apply' }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Cleanup failed; inspect the manifest and retained files.' }

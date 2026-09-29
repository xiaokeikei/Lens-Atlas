$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
$python = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Run python -m venv .venv and install requirements-desktop.txt first.' }
Push-Location frontend
try { npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }; npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' } } finally { Pop-Location }
& $python scripts/make_icon.py
& $python scripts/fetch_tools.py
if ($LASTEXITCODE -ne 0) { throw 'Tool download failed' }
& $python scripts/collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
& $python -m PyInstaller --noconfirm LensAtlas.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
Copy-Item -LiteralPath README.md,THIRD_PARTY_NOTICES.md,LICENSE -Destination dist/LensAtlas
Write-Output 'Built dist/LensAtlas/LensAtlas.exe. Keep the complete directory together.'

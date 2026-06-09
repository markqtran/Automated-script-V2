$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

Write-Host ''
Write-Host '=== Build FootageWorkflow.exe ===' -ForegroundColor Cyan
Write-Host ''

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host 'Python not found. Install from https://www.python.org/downloads/' -ForegroundColor Red
    exit 1
}

$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$venvDir = Join-Path $PSScriptRoot '.venv'

function Test-VenvPython {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    & $Path -c "import sys" 2>$null
    return $LASTEXITCODE -eq 0
}

if (-not (Test-VenvPython $venvPython)) {
    if (Test-Path $venvDir) {
        Write-Host 'Removing broken .venv (often copied from another PC or old Python path)...' -ForegroundColor Yellow
        Remove-Item -Recurse -Force $venvDir
    }
    Write-Host 'Creating virtual environment...'
    & $python.Source -m venv $venvDir
    if (-not (Test-VenvPython $venvPython)) {
        Write-Host "Could not create a working venv at $venvPython" -ForegroundColor Red
        exit 1
    }
}

Write-Host 'Installing dependencies...'
& $venvPython -m pip install -q -r requirements.txt
& $venvPython -m pip install -q pyinstaller

Write-Host 'Building executable...'
& $venvPython -m PyInstaller --noconfirm FootageWorkflow.spec
if ($LASTEXITCODE -ne 0) {
    Write-Host 'PyInstaller failed.' -ForegroundColor Red
    exit 1
}

$exe = Join-Path $PSScriptRoot 'dist\FootageWorkflow.exe'
if (Test-Path $exe) {
    Write-Host ''
    Write-Host '=== Build complete ===' -ForegroundColor Green
    Write-Host ''
    Write-Host "  $exe"
    Write-Host ''
    Write-Host 'Share the dist\FootageWorkflow.exe file (or zip the whole dist folder).'
    Write-Host 'Each user configures drive letters and Google links in Settings on first run.'
    Write-Host ''
} else {
    Write-Host 'Build failed — FootageWorkflow.exe not found.' -ForegroundColor Red
    exit 1
}

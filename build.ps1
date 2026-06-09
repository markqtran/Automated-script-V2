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

function Test-VenvUsable {
    param(
        [string]$VenvDir,
        [string]$VenvPython
    )

    if (-not (Test-Path $VenvPython)) {
        return $false
    }

    $cfg = Join-Path $VenvDir 'pyvenv.cfg'
    if (Test-Path $cfg) {
        foreach ($line in Get-Content $cfg) {
            if ($line -match '^home\s*=\s*(.+)$') {
                $home = $Matches[1].Trim().Trim('"')
                $basePython = Join-Path $home 'python.exe'
                if (-not (Test-Path $basePython)) {
                    return $false
                }
            }
        }
    }

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $VenvPython -c "import sys" 1>$null 2>$null
        return $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $previous
    }
}

if (-not (Test-VenvUsable -VenvDir $venvDir -VenvPython $venvPython)) {
    if (Test-Path $venvDir) {
        Write-Host 'Removing broken .venv (copied from another PC or missing Python)...' -ForegroundColor Yellow
        Remove-Item -Recurse -Force $venvDir
    }
    Write-Host 'Creating virtual environment...'
    & $python.Source -m venv $venvDir
    if (-not (Test-VenvUsable -VenvDir $venvDir -VenvPython $venvPython)) {
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

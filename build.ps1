$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

Write-Host ''
Write-Host '=== Build FootageWorkflow.exe ===' -ForegroundColor Cyan
Write-Host ''

function Test-PythonExe {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $Path -c "import sys" 1>$null 2>$null
    $ok = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $previous
    return $ok
}

function Find-SystemPython {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $listed = & py -0p 2>$null
        foreach ($line in $listed) {
            if ($line -match '([A-Za-z]:\\[^\s]+\\python\.exe)\s*$') {
                $candidate = $Matches[1].Trim('*').Trim()
            } else {
                continue
            }
            if (Test-PythonExe $candidate) {
                $ErrorActionPreference = $previous
                return $candidate
            }
        }
        $exe = (& py -3 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
        $ErrorActionPreference = $previous
        if ($LASTEXITCODE -eq 0 -and $exe -and (Test-PythonExe $exe.Trim())) {
            return $exe.Trim()
        }
    }

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $where = & where.exe python 2>$null
    $ErrorActionPreference = $previous
    foreach ($line in ($where -split "[`r`n]+")) {
        $candidate = $line.Trim()
        if (-not $candidate) { continue }
        if ($candidate -like '*\Microsoft\WindowsApps\*') { continue }
        if (Test-PythonExe $candidate) { return $candidate }
    }

    foreach ($name in @('python3', 'python')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        if ($cmd.Source -like '*\Microsoft\WindowsApps\*') { continue }
        if (Test-PythonExe $cmd.Source) { return $cmd.Source }
    }

    $patterns = @(
        "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe",
        "$env:LOCALAPPDATA\Python\pythoncore-*\python.exe",
        "$env:LOCALAPPDATA\Python\bin\python.exe",
        "$env:ProgramFiles\Python*\python.exe",
        "${env:ProgramFiles(x86)}\Python*\python.exe"
    )
    foreach ($pattern in $patterns) {
        $installed = Get-ChildItem $pattern -ErrorAction SilentlyContinue |
            Sort-Object { $_.Directory.Name } -Descending |
            Select-Object -First 1
        if ($installed -and (Test-PythonExe $installed.FullName)) {
            return $installed.FullName
        }
    }

    return $null
}

$systemPython = Find-SystemPython
if (-not $systemPython) {
    Write-Host 'Python is installed but this shell cannot find it.' -ForegroundColor Red
    Write-Host ''
    Write-Host 'Windows often blocks the "python" command even when Python is installed:'
    Write-Host '  • The Microsoft Store "python.exe" alias runs first (fake stub)'
    Write-Host '  • Python was installed without "Add to PATH"'
    Write-Host ''
    Write-Host 'Try these in PowerShell (send output if build still fails):'
    Write-Host '  py -0p'
    Write-Host '  where.exe python'
    Write-Host '  Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Recurse -Filter python.exe'
    Write-Host ''
    Write-Host 'Quick fixes:'
    Write-Host '  1. Settings → Apps → App execution aliases → OFF python.exe / python3.exe'
    Write-Host '  2. Re-run Python installer → Modify → check "Add python.exe to PATH"'
    Write-Host '  3. Or build the venv with the full path, e.g.:'
    Write-Host '     & "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv'
    Write-Host ''
    Write-Host 'Or skip building: use dist\FootageWorkflow.exe (no Python needed).'
    Write-Host ''
    exit 1
}

Write-Host "Using Python: $systemPython"

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
                $pythonHome = $Matches[1].Trim().Trim('"')
                $basePython = Join-Path $pythonHome 'python.exe'
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
    & $systemPython -m venv $venvDir
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

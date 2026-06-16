# PyInstaller build for Windows .exe
$ErrorActionPreference = "Stop"
$PlatformDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $PlatformDir "../..")).Path
Set-Location $Root

function Test-GoodPython {
    param([string]$Exe)
    if (-not $Exe -or -not (Test-Path $Exe)) { return $false }
    if ($Exe -match "Inkscape") { return $false }
    try {
        $ver = & $Exe -c "import sys; print(sys.version_info >= (3, 10))" 2>$null
        return $ver -eq "True"
    }
    catch {
        return $false
    }
}

function Find-Python {
    $candidates = @()
    $candidates += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }
    $candidates += @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe"
    )
    foreach ($name in @("python3", "python")) {
        $found = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
        if ($found) { $candidates += $found }
    }
    foreach ($exe in ($candidates | Select-Object -Unique)) {
        if ($exe -match "WindowsApps") { continue }
        if (Test-GoodPython $exe) { return $exe }
    }
    return $null
}

$python = Find-Python
if (-not $python) {
    Write-Error "No suitable Python 3.10+ found. Install from https://python.org/downloads/ (Inkscape Python is skipped)."
}

Write-Host "Using Python: $python"
Write-Host "Installing build deps..."
& $python -m pip install -q -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed"
}

$version = & $python -c "import sys; sys.path.insert(0, 'app'); from version import __version__; print(__version__)"
Write-Host "Building CursorTunnelApp.exe v$version (no console window)..."
& $python -m PyInstaller --noconfirm --onefile --noconsole --name CursorTunnelApp `
  --add-data "app/static;static" `
  --add-data "cluster;cluster" `
  --paths "app" `
  --hidden-import paramiko `
  app/main.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed"
}

$exe = Join-Path $Root "dist\CursorTunnelApp.exe"
if (-not (Test-Path $exe)) {
    Write-Error "Build finished but $exe was not created"
}

Write-Host ""
Write-Host "Done: $exe"
Write-Host "Double-click dist\CursorTunnelApp.exe to open the dashboard in your browser."

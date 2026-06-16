# Cursor Tunnel App launcher
param([switch]$ServerOnly)

$ErrorActionPreference = "Stop"
$AppName = "Cursor Tunnel App"
$AppSlug = "cursor-tunnel-app"
$LogBasename = "cursor-tunnel-app.log"

$PlatformDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $PlatformDir "../..")).Path
Set-Location $Root

$LogDir = Join-Path $env:APPDATA $AppSlug
$LogFile = Join-Path $LogDir $LogBasename
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log {
    param([string]$Message)
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Show-Error {
    param([string]$Message)
    Write-Log "ERROR: $Message"
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show(
        "$Message`n`nLog: $LogFile",
        $AppName,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    )
}

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

function Get-DashboardSettings {
    $port = 8765
    $openBrowser = $true
    $cfgPath = Join-Path $LogDir "config.json"
    if (Test-Path $cfgPath) {
        try {
            $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
            if ($cfg.listen_port) { $port = [int]$cfg.listen_port }
            if ($null -ne $cfg.open_browser) { $openBrowser = [bool]$cfg.open_browser }
        }
        catch {
            Write-Log "Could not read config.json, using defaults"
        }
    }
    return @{
        Port        = $port
        OpenBrowser = $openBrowser
        Url         = "http://127.0.0.1:$port/"
    }
}

function Open-DashboardBrowser {
    param([hashtable]$Dash)
    if (-not $Dash.OpenBrowser) {
        return
    }
    $url = $Dash.Url
    Write-Log "Waiting for dashboard at $url"
    for ($i = 0; $i -lt 90; $i++) {
        try {
            $null = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            Write-Log "Opening browser at $url"
            Start-Process $url
            return
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    Write-Log "Dashboard slow to respond; opening browser anyway"
    Start-Process $url
}

try {
    Write-Log "$AppName starting..."

    $dash = Get-DashboardSettings

    $python = Find-Python
    if (-not $python) {
        throw "No suitable Python 3.10+ found. Install from https://python.org/downloads/"
    }

    Write-Log "Using Python: $python"
    & $python -m pip install --upgrade pip 2>> $LogFile | Out-Null
    & $python -m pip install -r requirements.txt 2>> $LogFile
    if ($LASTEXITCODE -ne 0) {
        throw "pip install failed - see log"
    }

    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match 'python(w)?\.exe' -and $_.CommandLine -match 'main\.py' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

    $port = $dash.Port
    Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

    $pythonW = Join-Path (Split-Path $python -Parent) "pythonw.exe"
    $serverExe = if (Test-Path $pythonW) { $pythonW } else { $python }

    Write-Log "Starting server with $serverExe on port $port"
    Start-Process -FilePath $serverExe -ArgumentList "app/main.py" -WorkingDirectory $Root -WindowStyle Hidden

    Write-Log "$AppName ready at $($dash.Url)"

    if (-not $ServerOnly) {
        Open-DashboardBrowser -Dash $dash
    }
}
catch {
    Show-Error $_.Exception.Message
    exit 1
}

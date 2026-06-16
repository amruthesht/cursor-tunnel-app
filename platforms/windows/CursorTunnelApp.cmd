@echo off
cd /d "%~dp0"

if /i not "%~1"=="__run__" (
  start "" /min cmd /c "%~f0" __run__
  goto :eof
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-CursorTunnelApp.ps1"
if errorlevel 1 (
  echo.
  echo Cursor Tunnel App failed. Check %APPDATA%\cursor-tunnel-app\cursor-tunnel-app.log
  pause
  exit /b 1
)

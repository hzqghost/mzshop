@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tool\admin\restart.ps1"
if errorlevel 1 (
  echo.
  echo 重启失败，请查看上方错误。
  pause
)

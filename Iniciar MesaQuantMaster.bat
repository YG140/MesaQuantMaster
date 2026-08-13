@echo off
setlocal
set "MQM_ROOT=%~dp0"
start "Mesa Quant Master" powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File "%MQM_ROOT%start.ps1" -DedicatedWindow %*
exit /b 0

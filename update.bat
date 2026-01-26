@echo off
setlocal
set MSG=%~1
if "%MSG%"=="" set MSG=auto update
powershell -ExecutionPolicy Bypass -File "%~dp0push.ps1" "%MSG%"
endlocal

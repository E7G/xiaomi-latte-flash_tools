@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Xiaomi Mi Pad 2 CachyOS - BOOT REPAIR
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0flash-one-click.ps1" -BootOnly
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo Boot repair failed. See the error above.
pause
exit /b %RC%

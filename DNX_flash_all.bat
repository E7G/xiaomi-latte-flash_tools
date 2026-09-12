@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Xiaomi Mi Pad 2 CachyOS - ONE KEY FLASH
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0flash-one-click.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo Flash failed. See the error above.
pause
exit /b %RC%

@echo off
setlocal EnableExtensions
title Xiaomi Mi Pad 2 Arch Linux - Boot Partition Flash
color 0A

where fastboot.exe >nul 2>&1 || (
  echo ERROR: fastboot.exe not found in PATH.
  goto :fail
)
if not exist "%~dp0device_files\fastboot.efi" goto :missing
if not exist "%~dp0images\xiaomi-latte-boot.img" goto :missing

fastboot boot "%~dp0device_files\fastboot.efi" || goto :fail
fastboot getvar product 2>"%TEMP%\xiaomi-latte-product.txt"
findstr /r /c:"product: *latte" "%TEMP%\xiaomi-latte-product.txt" >nul || (
  echo ERROR: connected device is not Xiaomi Mi Pad 2 ^(latte^).
  goto :fail
)
fastboot oem unlock
fastboot flash boot "%~dp0images\xiaomi-latte-boot.img" || goto :fail
fastboot reboot || goto :fail

del "%TEMP%\xiaomi-latte-product.txt" >nul 2>&1
echo Boot partition flash complete.
pause
exit /b 0

:missing
echo ERROR: required boot image is missing.
:fail
del "%TEMP%\xiaomi-latte-product.txt" >nul 2>&1
echo Flash stopped because a required step failed.
pause
exit /b 1

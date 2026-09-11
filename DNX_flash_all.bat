@echo off
setlocal EnableExtensions
title Xiaomi Mi Pad 2 Arch Linux - Full Flash
color 0A

where fastboot.exe >nul 2>&1 || (
  echo ERROR: fastboot.exe not found in PATH.
  goto :fail
)

for %%F in (
  "device_files\fastboot.efi"
  "device_files\oemvars.txt"
  "device_files\oemvars-battery-config-fake-disabled.txt"
  "device_files\oemvars-battery-config-fake.txt"
  "images\gpt.bin"
  "images\xiaomi-latte-boot.img"
  "images\xiaomi-latte-rootfs.img"
) do if not exist "%~dp0%%~F" (
  echo ERROR: missing %%~F
  goto :fail
)

fastboot boot "%~dp0device_files\fastboot.efi" || goto :fail
fastboot getvar product 2>"%TEMP%\xiaomi-latte-product.txt"
findstr /r /c:"product: *latte" "%TEMP%\xiaomi-latte-product.txt" >nul || (
  echo ERROR: connected device is not Xiaomi Mi Pad 2 ^(latte^).
  goto :fail
)

fastboot oem unlock
fastboot flash oemvars "%~dp0device_files\oemvars.txt" || goto :fail
fastboot flash oemvars "%~dp0device_files\oemvars-battery-config-fake-disabled.txt" || goto :fail
fastboot flash oemvars "%~dp0device_files\oemvars-battery-config-fake.txt" || goto :fail
fastboot flash gpt "%~dp0images\gpt.bin" || goto :fail
fastboot flash boot "%~dp0images\xiaomi-latte-boot.img" || goto :fail
fastboot flash system "%~dp0images\xiaomi-latte-rootfs.img" || goto :fail
fastboot reboot || goto :fail

del "%TEMP%\xiaomi-latte-product.txt" >nul 2>&1
echo Flash complete.
pause
exit /b 0

:fail
del "%TEMP%\xiaomi-latte-product.txt" >nul 2>&1
echo Flash stopped because a required step failed.
pause
exit /b 1

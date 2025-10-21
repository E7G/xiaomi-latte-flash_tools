@echo off
Title  * ONE KEY TO FLASH
::setup the window size
mode con:cols=80 lines=35
::setup background and foreground color
cls

set debug=0

fastboot boot %~dp0device_files\boot\EFI\boot\fastboot.efi

color 0A
fastboot getvar product
fastboot getvar product 2>&1 | findstr /r /c:"^product: *latte" || echo Missmatching image and device || Timeout 10
fastboot getvar product 2>&1 | findstr /r /c:"^product: *latte" || exit /B 1

fastboot oem unlock
if %debug% == 1  Pause

fastboot flash oemvars %~dp0device_files\oemvars.txt
fastboot flash oemvars %~dp0device_files\oemvars-battery-config-fake-disabled.txt
fastboot flash oemvars %~dp0device_files\oemvars-battery-config-fake.txt

fastboot flash gpt %~dp0images\gpt.bin
fastboot format data
fastboot flash boot  %~dp0images\boot.img
fastboot flash system  %~dp0images\system.img
fastboot flash vendor %~dp0images\vendor.img

fastboot getvar secureboot
if %debug% == 1  Pause

fastboot reboot

@Echo Done!

Pause


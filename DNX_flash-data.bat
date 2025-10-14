@echo off
Title  * ONE KEY TO FLASH
::setup the window size
mode con:cols=80 lines=35
::setup background and foreground color
cls

set debug=0

fastboot boot %~dp0loader.efi

color 0A
fastboot getvar product
fastboot getvar product 2>&1 | findstr /r /c:"^product: *latte" || echo Missmatching image and device || Timeout 10
fastboot getvar product 2>&1 | findstr /r /c:"^product: *latte" || exit /B 1

fastboot oem unlock
if %debug% == 1  Pause

set "SIMG=%~dp0images\data.simg"
set "IMG=%~dp0images\data.img"
if exist "%SIMG%" (
    echo Using data.simg
    set "DATA_FILE=%SIMG%"
) else (
    echo data.simg not found, falling back to data.img
    set "DATA_FILE=%IMG%"
)
fastboot flash data "%DATA_FILE%"
if %debug% == 1  Pause

fastboot reboot

@Echo Done!

Pause


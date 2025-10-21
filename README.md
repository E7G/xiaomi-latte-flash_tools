# how to use
download [kernel file](https://github.com/Qs315490/android-x86-kernel-latte/actions/runs/18484752772) to `./kernel-6.15-package.zip`  
download [Bliss-v14.10.3-x86_64-OFFICIAL-foss-20241012.iso](https://sourceforge.net/projects/blissos-x86/files/Official/BlissOS14/FOSS/Generic/Bliss-v14.10.3-x86_64-OFFICIAL-foss-20241012.iso/download)  
install `7z` `squashfs-tools` `f2fs-tools` package
```bash
bash build_tool.sh
# windows users can use DNX_flash_all.bat
# run this code to flash
fastboot boot device_files/fasttboot.efi
fastboot flash gpt images/gpt.bin
fastboot flash boot images/boot.img
fastboot flash system images/system.img
fastboot flash data images/data.img # or data.simg
```


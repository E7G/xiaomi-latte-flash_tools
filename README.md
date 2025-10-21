# how to use
download [kernel file](https://github.com/Qs315490/linux_latte/releases/download/v1.1.3-alpha/linux-upstream-6.14.0-2-x86_64.pkg.tar.zst) to `./device_file/linux-upstream-6.14.0-2-x86_64.pkg.tar.zst`  
check kernel has nbd.ko  
install `qemu-utils` `arch-install-script` `btrfs-utils` package
```bash
bash build_rootfs.sh
# windows users can use DNX_flash_all.bat
# run this code to flash
fastboot boot device_files/fasttboot.efi
fastboot flash gpt images/gpt.bin
fastboot flash boot  images/xiaomi-latte-boot.img
fastboot flash system  images/xiaomi-latte-root.img
```
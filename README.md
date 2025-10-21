# how to use
```bash
python3 gpt_ini2bin.py
# put images in ./images
# windows users can use DNX_flash_all.bat
# run this code to flash
fastboot boot device_files/fasttboot.efi
fastboot flash gpt images/gpt.bin
fastboot flash boot  images/xiaomi-latte-boot.img
fastboot flash system  images/xiaomi-latte-root.img
```
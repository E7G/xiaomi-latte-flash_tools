#!/bin/sh

UDC=`ls /sys/class/udc/|head -n 1`
SERIAL=/dev/ttyGS0

if [ -n "$UDC" ];then
    echo "UDC found: $UDC"
else
    echo "No UDC found"
    exit 0
fi

cd /config/usb_gadget/
mkdir -p g1
cd g1

echo 0x1d6b > idVendor   # Linux Foundation
echo 0x0104 > idProduct  # Multifunction Composite Gadget
echo 0x0100 > bcdDevice # v1.0.0
echo 0x0200 > bcdUSB    # USB2.0

mkdir -p strings/0x409
echo "315490" > strings/0x409/serialnumber
echo "QuickSwift" > strings/0x409/manufacturer
echo "Composite Gadget" > strings/0x409/product

mkdir -p configs/c.1/strings/0x409
echo "Composite Config" > configs/c.1/strings/0x409/configuration
echo 500 > configs/c.1/MaxPower

# 添加RNDIS功能
# mkdir -p functions/rndis.usb0
# echo "RNDIS" > functions/rndis.usb0/os_desc/interface.rndis/compatible_id
# echo "5162001" > functions/rndis.usb0/os_desc/interface.rndis/sub_compatible_id
# ln -s functions/rndis.usb0 configs/c.1/
# echo 1 > os_desc/use
# echo 0xcd > os_desc/b_vendor_code
# echo MSFT100 > os_desc/qw_sign

# 检查 /dev/mmcblk0 是否存在
# if [ -b /dev/mmcblk0 ]; then
#     mkdir -p functions/mass_storage.usb0
#     echo 0 > functions/mass_storage.usb0/stall
#     echo 0 > functions/mass_storage.usb0/lun.0/cdrom
#     echo 0 > functions/mass_storage.usb0/lun.0/ro
#     echo 0 > functions/mass_storage.usb0/lun.0/nofua
#     echo /dev/mmcblk0 > functions/mass_storage.usb0/lun.0/file
#     ln -s functions/mass_storage.usb0 configs/c.1/
# fi

# 添加CDC ACM串口功能
mkdir -p functions/acm.usb0
ln -s functions/acm.usb0 configs/c.1/

# 启用 USB 设备控制器
if [ -n "$UDC" ];then
    echo "$UDC" > UDC
fi

# 检查设备是否已连接
ls /dev/ttyGS*

start ttygs0

echo OK
return 0
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

# 添加USB网络功能
mkdir -p functions/ecm.usb0
# echo "RNDIS" > functions/ecm.usb0/os_desc/interface.rndis/compatible_id
# echo "5162001" > functions/ecm.usb0/os_desc/interface.rndis/sub_compatible_id
echo "021234567890" > functions/ecm.usb0/dev_addr    # Android 的 MAC
echo "021234567891" > functions/ecm.usb0/host_addr   # 对端的 MAC
ln -s functions/ecm.usb0 configs/c.1/
echo 1 > os_desc/use
echo 0xcd > os_desc/b_vendor_code
echo MSFT100 > os_desc/qw_sign

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
# mkdir -p functions/acm.usb0
# ln -s functions/acm.usb0 configs/c.1/

# 启用 USB 设备控制器
if [ -n "$UDC" ];then
    echo "$UDC" > UDC
fi

# 检查设备是否已连接
ls /dev/ttyGS*
ip link show usb0
# 等待 usb0
while [ ! -d /sys/class/net/usb0 ]; do
    sleep 1
done

# 设置 ip地址
ip addr add 192.168.255.1/24 dev usb0
# 启动 usb0 网络接口
ip link set usb0 up
# 强制让 local 流量走 main 表
ip rule add from all lookup main pref 100

start dnsmasq_rndis

echo OK
return 0
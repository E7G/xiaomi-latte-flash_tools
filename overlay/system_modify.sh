#!/system/bin/sh
set -e

BUILD_PROP="system/vendor/build.prop"
MARKER_START="# start modify"
MARKER_END="# end modify"

echo "Config build.prop ..."
sed -i 's/ro.com.android.dateformat=MM-dd-yyyy/ro.com.android.dateformat=yyyy-MM-dd/g' $BUILD_PROP

if ! grep -qF "$MARKER_START" "$BUILD_PROP"; then
cat << EOF >> $BUILD_PROP
$MARKER_START
# 设置时区为上海
persist.sys.timezone=Asia/Shanghai
# 设置语言为中文（简体）
persist.sys.language=zh
persist.sys.country=CN
# 可选：同时设置 ro.product.locale（推荐用于 Android 6.0+）
ro.product.locale=zh-CN
# 设置DPI
ro.sf.lcd_density=320
# 默认开启无线ADB
service.adb.tcp.port=5555
# 开启USB配置文件系统, 从传统sys配置转为configfs
sys.usb.configfs=1
$MARKER_END
EOF
fi
echo "Config build.prop done."

echo "Config fstab ..."
sed -i '/mmc/d' "fstab.bliss_x86_64"
sed -i '/mmc/d' "system/vendor/etc/fstab.internal.x86"
echo "Config fstab done."

# 删除不必要的应用
echo "Removing unnecessary apps..."
rm -rf "system/app/AboutBliss"
rm -rf "system/app/com.googlecode.eyesfree.setorientation_1.1.4-10"
rm -rf "system/priv-app/BlissUpdater"
rm -rf "system/product/app/yetCalc"
rm -rf "system/product/app/messaging"
rm -rf "system/product/priv-app/Contacts"
rm -rf "system/product/priv-app/Dialer"
rm -rf "system/system_ext/priv-app/com.farmerbb.taskbar"
rm -rf "system/system_ext/priv-app/com.farmerbb.taskbar.support"
rm -rf "system/system_ext/priv-app/smart-dock"
echo "Removing unnecessary apps done."

# 删除不必要的固件
echo "Removing unnecessary firmware..."
rm -rf "system/vendor/firmware/amd"*
rm -rf "system/vendor/firmware/radeon"
rm -rf "system/vendor/firmware/amlogic"
rm -rf "system/vendor/firmware/arm"
rm -rf "system/vendor/firmware/nvidia"
rm -rf "system/vendor/firmware/qcom"
rm -rf "system/vendor/firmware/iwlwifi-"*
echo "Removing unnecessary firmware done."

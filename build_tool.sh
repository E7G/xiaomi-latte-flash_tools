#!/bin/bash
set -e
# set -x
shopt -s expand_aliases

CURRENT_DIR=$(pwd)
echo "Current directory: $CURRENT_DIR"
DEVICE_FILES_DIR="$CURRENT_DIR/device_files"
BUILD_DIR="$CURRENT_DIR/build"
OUTPUT_DIR="$CURRENT_DIR/images"
BOOT_DIR="$CURRENT_DIR/boot"

# blissos 官方镜像
ISO_FILE=$(ls *.iso | head -n 1)
# 来自 https://github.com/Qs315490/android-x86-kernel-latte action编译的内核打包文件
KERNEL_PACKAGE_FILE=$(ls kernel-*-package.zip | head -n 1)
# https://dl.fedoraproject.org/pub/fedora/linux/releases/43/Everything/x86_64/os/Packages/s/shim-x64-15.8-3.x86_64.rpm
SHIM_PACKAGE_FILE=$(ls shim-x64-*.x86_64.rpm | head -n 1)
# https://dl.fedoraproject.org/pub/fedora/linux/releases/43/Everything/x86_64/os/Packages/g/grub2-efi-x64-2.12-40.fc43.x86_64.rpm
GRUB_PACKAGE_FILE=$(ls grub2-efi-x64-*.x86_64.rpm | head -n 1)

mkdir -p "$BUILD_DIR" "$OUTPUT_DIR" "$BOOT_DIR"/EFI/{boot,BlissOS}

is_mount() {
    if [ -z "$1" ]; then
        echo "Usage: is_mount <mount_point>"
        return 1
    fi
    grep "$1" /proc/mounts &>/dev/null
	return $?
}

gpt() {
    python gpt_ini2bin.py
}

unpack_iso() {
    echo "Unpacking ISO..."
    mkdir -p $BUILD_DIR/iso
    7z x "$ISO_FILE" "-o$BUILD_DIR/iso"
    echo "Unpacking ISO done."
}

unpack_shim_grub_package() {
    echo "Unpacking shim and grub package..."
    if [ -d "$BUILD_DIR/shim_grub" ]; then
        rm -rf "$BUILD_DIR/shim_grub"
    fi

    # need rpm2cpio
    mkdir -p "$BUILD_DIR/shim_grub"
    cd "$BUILD_DIR/shim_grub"
    rpm2cpio "$CURRENT_DIR/$SHIM_PACKAGE_FILE" | cpio -idmv
    rpm2cpio "$CURRENT_DIR/$GRUB_PACKAGE_FILE" | cpio -idmv
    cd -
    echo "Unpacking shim and grub package done."
}

copy_shim_grub_to_efi() {
    if [ ! -d "$BUILD_DIR/shim_grub" ]; then
        unpack_shim_grub_package
    fi
    echo "Copying shim and grub files..."
    mkdir -p "$BOOT_DIR/EFI/boot"
    cp "$BUILD_DIR/shim_grub"/boot/efi/EFI/fedora/shimx64.efi "$BOOT_DIR/EFI/boot/bootx64.efi"
    cp "$BUILD_DIR/shim_grub"/boot/efi/EFI/fedora/mmx64.efi "$BOOT_DIR/EFI/boot/mmx64.efi"
    cp "$BUILD_DIR/shim_grub"/boot/efi/EFI/fedora/grubx64.efi "$BOOT_DIR/EFI/boot/grubx64.efi"
    echo "Copying shim and grub files done."
}

unpack_initrd() {
    echo "Unpacking initrd..."
    mkdir -p "$BUILD_DIR/initrd"
    cd "$BUILD_DIR/initrd"
    zcat ../iso/initrd.img | cpio -id
    cd -
    echo "Unpacking initrd done."
}

patch_initrd() {
    cd "$BUILD_DIR/initrd"
    patch -p1 < "$DEVICE_FILES_DIR/initrd.patch"
    if [ -f "$DEVICE_FILES_DIR/dsdt.aml" ]; then
        iasl -ve -ts "$DEVICE_FILES_DIR/dsdt.dsl"
    fi
    mkdir -p kernel/firmware/acpi
    cp "$DEVICE_FILES_DIR/dsdt.aml" kernel/firmware/acpi/dsdt.aml
    cd -
}

pack_initrd() {
    echo "Packing initrd..."
    cd "$BUILD_DIR/initrd"
    find . | cpio --create --format='newc' | gzip > "$BOOT_DIR/EFI/BlissOS/initrd.cpio.gz"
    cd -
    rm -rf "$BUILD_DIR/initrd"
    echo "Packing initrd done."
}

unpack_kernel_package() {
    echo "Unpacking kernel package..."
    if [ -d "$BUILD_DIR/kernel" ]; then
        rm -rf "$BUILD_DIR/kernel"
    fi
    mkdir -p "$BUILD_DIR/kernel"
    unzip -o "$KERNEL_PACKAGE_FILE" -d "$BUILD_DIR"
    FILE=$(ls "$BUILD_DIR"/kernel-*.tar.gz | head -n 1)
    tar -xzf "$FILE" -C "$BUILD_DIR/kernel"
    echo "Unpacking kernel package done."
}

copy_kernel_to_efi() {
    echo "Copying kernel..."
    if [ ! -d "$BUILD_DIR/kernel" ]; then
        unpack_kernel_package
    fi
    cd "$BUILD_DIR/kernel" 
    FILE=$(ls vmlinuz-* | head -n 1)
    cp "$FILE" "$BOOT_DIR/EFI/BlissOS/vmlinuz"
    cd -
    echo "Copying kernel done."
}

build_boot_image() {
    echo "Creating boot image..."
    mkdir -p "$OUTPUT_DIR"
    truncate -s 64M "$OUTPUT_DIR/boot.img"

    echo "Formatting boot image..."
    mkfs.vfat -F 32 -n ESP "$OUTPUT_DIR/boot.img"
    echo "Formatting boot image done."

    echo "Mounting boot image..."
    mount_dir="$BUILD_DIR/boot_mount"
    if is_mount "$mount_dir"; then
        # 如果已经挂载，先卸载
        umount -R "$mount_dir"
    fi
    mkdir -p "$mount_dir"
    mount -o loop "$OUTPUT_DIR/boot.img" "$mount_dir"
    echo "Mounting boot image done."

    echo "Copying boot files to boot image..."
    cp -r "$BOOT_DIR/"* "$mount_dir/"
    cat <<EOF >> "$mount_dir/EFI/boot/grub.cfg"
search --no-floppy --set=root --label ESP
set prefix="(\$root)/EFI/BlissOS"
configfile \$prefix/grub.cfg

EOF
    cp "$DEVICE_FILES_DIR/grub.cfg" "$mount_dir/EFI/BlissOS/"
    cp "$DEVICE_FILES_DIR/"*.efi "$mount_dir/EFI/BlissOS/"
    cp "$DEVICE_FILES_DIR/MOK.cer" "$mount_dir/"
    echo "Copying boot files done."

    umount "$mount_dir"
    rm -rf "$mount_dir"
    echo "Boot image created at $OUTPUT_DIR/boot.img"
}

unpack_system_image() {
    echo "Unpacking system image..."
    # image is squashfs, need squashfs-tools
    unsquashfs -d "$BUILD_DIR/" "$BUILD_DIR/iso/system.sfs"
    echo "Unpacking system image done."
}

system_mount_dir="$BUILD_DIR/system_mount"
mount_system_image() {
    if is_mount "$system_mount_dir"; then
        # 如果已经挂载，先卸载
        umount -R "$system_mount_dir"
    fi
    mkdir -p "$system_mount_dir"
    mount -o loop "$BUILD_DIR/system.img" "$system_mount_dir"
}

copy_file_to_system() {
    if [ ! -d "$BUILD_DIR/kernel" ]; then
        unpack_kernel_package
    fi
    modules_dir="$system_mount_dir/system/lib/modules"
    if [ ! -d "$modules_dir" ]; then
        echo "Kernel modules directory not found: $modules_dir"
        exit 1
    fi
    echo "Copying kernel modules..."
    rm -rf "$modules_dir"/*
    cp -rf "$BUILD_DIR"/kernel/lib/modules/* "$modules_dir/"
    echo "Copying kernel modules done."

    echo "Copying firmware..."
    cp -rf "$DEVICE_FILES_DIR/BCM4356A2.hcd" "$system_mount_dir/system/vendor/firmware/brcm/"
    cp -rf "$DEVICE_FILES_DIR/brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt" "$system_mount_dir/system/vendor/firmware/brcm/"
    echo "Copying firmware done."

    echo "Copying autio config ..."
    UCM_DIR="$system_mount_dir/system/usr/share/alsa/ucm2/conf.d"
    mkdir -p "$UCM_DIR"/cht-bsw-rt5659
    cp -rf "$DEVICE_FILES_DIR/cht-bsw-rt5659.conf" "$UCM_DIR"/cht-bsw-rt5659/
    cp -rf "$DEVICE_FILES_DIR/HiFi.conf" "$UCM_DIR"/cht-bsw-rt5659/
    echo "Copying audio config done."

    echo "build keyboard remap program ..."
    gcc $DEVICE_FILES_DIR/mipad2_keymap.c -o $system_mount_dir/system/bin/mipad2_keymap -static
    chmod 777 $system_mount_dir/system/bin/mipad2_keymap 
    echo "build keyboard remap program done."

    echo "Config build.prop ..."
    sed -i 's/ro.com.android.dateformat=MM-dd-yyyy/ro.com.android.dateformat=yyyy-MM-dd/g' "$system_mount_dir/system/vendor/build.prop"

    cat << EOF >> "$system_mount_dir/system/vendor/build.prop"
# 设置时区为上海
persist.sys.timezone=Asia/Shanghai
# 设置语言为中文（简体）
persist.sys.language=zh
persist.sys.country=CN
# 可选：同时设置 ro.product.locale（推荐用于 Android 6.0+）
ro.product.locale=zh-CN
# 设置DPI
ro.sf.lcd_density=320
EOF
    echo "Config build.prop done."

    echo "Config init ..."
    cat << EOF >> "$system_mount_dir/init.environ.rc"
# 小米平板2电容触摸按键重映射服务
service mipad2_keymap /system/bin/mipad2_keymap
    class main
    user root
    group root input
    # 必须有 input 权限才能访问 /dev/input/event*
    disabled
    oneshot
    # 在输入设备初始化完成后启动
    start-delay 2

# 在 sys.boot_completed 后启动（可选，更保险）
on property:sys.boot_completed=1
    start mipad2_keymap
    # 系统启动完成后设置 captive portal URLs
    exec -- /system/bin/settings put global captive_portal_https_url https://connect.rom.miui.com/generate_204

EOF
    echo "Config init done."

    # 删除不必要的应用
    echo "Removing unnecessary apps..."
    rm -rf "$system_mount_dir/system/app/com.googlecode.eyesfree.setorientation_1.1.4-10"
    rm -rf "$system_mount_dir/system/priv-app/BlissUpdater"
    rm -rf "$system_mount_dir/system/product/app/yetCalc"
    rm -rf "$system_mount_dir/system/product/app/messaging"
    rm -rf "$system_mount_dir/system/product/priv-app/Contacts"
    rm -rf "$system_mount_dir/system/product/priv-app/Dialer"
    rm -rf "$system_mount_dir/system/system_ext/priv-app/com.farmerbb.taskbar"
    rm -rf "$system_mount_dir/system/system_ext/priv-app/com.farmerbb.taskbar.support"
    rm -rf "$system_mount_dir/system/system_ext/priv-app/smart-dock"
    echo "Removing unnecessary apps done."

    # 删除不必要的固件
    echo "Removing unnecessary firmware..."
    rm -rf "$system_mount_dir/system/vendor/firmware/amd"*
    rm -rf "$system_mount_dir/system/vendor/firmware/amlogic"
    rm -rf "$system_mount_dir/system/vendor/firmware/arm"
    rm -rf "$system_mount_dir/system/vendor/firmware/nvidia"
    echo "Removing unnecessary firmware done."

    sync
}

pack_system_image() {
    echo "Packing system image..."
    if command -v mkfs.erofs &> /dev/null;then
        echo "erofs-utils found, using erofs for system image."
        # erofs, need erofs-utils
        mkfs.erofs -L system -zlzma "$OUTPUT_DIR/system.img" "$system_mount_dir"
    elif command -v mksquashfs &> /dev/null;then
        echo "squashfs-tools found, using squashfs for system image."
        # squashfs, need squashfs-tools
        mksquashfs "$system_mount_dir" "$OUTPUT_DIR/system.img" -comp xz -Xcompression-level 19 -b 1M -Xdict-size 1M -noappend
    else
        echo "erofs-utils and squashfs-tools not found, no package"
        umount "$system_mount_dir"
        cp "$BUILD_DIR/system.img" "$OUTPUT_DIR/system.img"
    fi

    umount "$system_mount_dir" || true
    rm -rf "$system_mount_dir"
    echo "Packing system image done."
}

create_data_image() {
    echo "Creating data image..."
    truncate -s 1G "$OUTPUT_DIR/data.img"

    echo "Formatting data image..."
    if command -v mkfs.f2fs &> /dev/null;then
        echo "f2fs-tools found, using f2fs for data image."
        # f2fs, need f2fs-tools
        # mkfs.f2fs -S -f "$OUTPUT_DIR/data.img"
        mkfs.f2fs -l data -f "$OUTPUT_DIR/data.img"
    else
        echo "f2fs-tools not found, using ext4 for data image."
        mkfs.ext4 -L data -s -F "$OUTPUT_DIR/data.img"
    fi

    echo "Formatting data image done."
}

convert_data_to_sparse() {
    img2simg "$OUTPUT_DIR/data.img" "$OUTPUT_DIR/data.simg"
}

install_libhoudini() {
    echo "Installing libhoudini..."
    libhoudini_file=$(ls *houdini*.zip|head -n 1)
    if [ ! -f "$libhoudini_file" ];then
        echo "libhoudini file not found."
    fi
    mount_system_image
    libhoudini_dir="$BUILD_DIR/libhoudini"
    mkdir -p $libhoudini_dir
    unzip $libhoudini_file -d "$libhoudini_dir/"

    echo Delete the original libhoudini
    rm -rf "$system_mount_dir/system/etc/binfmt_misc/*"
    rm -rf "$system_mount_dir/system/vendor/etc/binfmt_misc/*"
    # 32 bit
    rm -rf "$system_mount_dir/system/bin/houdini"
    rm -rf "$system_mount_dir/system/bin/arm"
    rm -rf "$system_mount_dir/system/vendor/bin/houdini"
    rm -rf "$system_mount_dir/system/vendor/bin/arm"
    rm -rf "$system_mount_dir/system/lib/libhoudini.so"
    rm -rf "$system_mount_dir/system/lib/arm"
    rm -rf "$system_mount_dir/system/vendor/lib/libhoudini.so"
    rm -rf "$system_mount_dir/system/vendor/lib/arm"
    # 64 bit
    rm -rf "$system_mount_dir/system/bin/houdini64"
    rm -rf "$system_mount_dir/system/bin/arm64"
    rm -rf "$system_mount_dir/system/vendor/bin/houdini64"
    rm -rf "$system_mount_dir/system/vendor/bin/arm64"
    rm -rf "$system_mount_dir/system/lib64/libhoudini.so"
    rm -rf "$system_mount_dir/system/lib64/arm64"
    rm -rf "$system_mount_dir/system/vendor/lib64/libhoudini.so"
    rm -rf "$system_mount_dir/system/vendor/lib64/arm64"

    echo Delete libndk_translation
    # 32 bit
    rm -rf "$system_mount_dir/system/bin/ndk_translation_program_runner_binfmt_misc"
    rm -rf "$system_mount_dir/system/bin/arm"
    rm -rf "$system_mount_dir/system/etc/ld.config.arm.txt"
    rm -rf "$system_mount_dir/system/lib/libndk_translation.so"
    rm -rf "$system_mount_dir/system/lib/libndk_translation_proxy_*.so"
    rm -rf "$system_mount_dir/system/lib/arm"
    # 64 bit
    rm -rf "$system_mount_dir/system/bin/ndk_translation_program_runner_binfmt_misc_arm64"
    rm -rf "$system_mount_dir/system/bin/arm64"
    rm -rf "$system_mount_dir/system/etc/ld.config.arm64.txt"
    rm -rf "$system_mount_dir/system/lib64/libndk_translation.so"
    rm -rf "$system_mount_dir/system/lib64/libndk_translation_proxy_*.so"
    rm -rf "$system_mount_dir/system/lib64/arm64"

    chmod -R 777 "$libhoudini_dir"/*/prebuilts/
    cp -r "$libhoudini_dir"/*/prebuilts/{bin,lib,lib64} "$system_mount_dir/system/"
    cp -r "$libhoudini_dir"/*/prebuilts/etc "$system_mount_dir/system/vendor/"

    echo "Installing libhoudini done."
}

all() {
    gpt

    umount -R "$BUILD_DIR"/* || true
    rm -rf "$BUILD_DIR"/*
    unpack_iso

    unpack_initrd
    patch_initrd
    pack_initrd
    unpack_shim_grub_package
    copy_shim_grub_to_efi
    unpack_kernel_package
    copy_kernel_to_efi
    build_boot_image

    unpack_system_image
    mount_system_image
    copy_file_to_system
    # libhoudini
    if [ -f "$CURRENT_DIR/"*houdini*.zip ];then
        install_libhoudini
    fi
    pack_system_image

    create_data_image
    if command -v img2simg &> /dev/null; then
        convert_data_to_sparse
    else
        echo "img2simg not found, skipping sparse conversion."
    fi

    rm -rf $BUILD_DIR
}

if [ -z $1 ];then
    all
else
    $1
fi
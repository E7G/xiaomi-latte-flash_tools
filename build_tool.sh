#!/bin/bash
set -e
# set -x
shopt -s expand_aliases

VER=15

CURRENT_DIR=$(pwd)
echo "Current directory: $CURRENT_DIR"
DEVICE_FILES_DIR="$CURRENT_DIR/device_files"
BUILD_DIR="$CURRENT_DIR/build"
BOOT_DIR="$BUILD_DIR/boot"
DATA_DIR="$BUILD_DIR/data"
SYSTEM_DIR="$BUILD_DIR/system"
ISO_DIR="$BUILD_DIR/iso"
INITRD_DIR="$BUILD_DIR/initrd"
KERNEL_DIR="$BUILD_DIR/kernel"
SHIM_GRUB_DIR="$BUILD_DIR/shim_grub"
IMAGE_DIR="$CURRENT_DIR/images"

INITRD_FILE="$INITRD_DIR.cpio.gz"

OVERLAY_DIR="$CURRENT_DIR/overlay"
OVERLAY_BOOT_DIR="$OVERLAY_DIR/boot"
OVERLAY_SYSTEM_DIR="$OVERLAY_DIR/system"
OVERLAY_DATA_DIR="$OVERLAY_DIR/data"

# blissos 官方镜像
ISO_FILE=$(ls Bliss*v$VER.*.iso | head -n 1)
# 来自 https://github.com/Qs315490/android-x86-kernel-latte action编译的内核打包文件
KERNEL_PACKAGE_FILE=$(ls kernel-*-package.zip | head -n 1)
# https://dl.fedoraproject.org/pub/fedora/linux/releases/43/Everything/x86_64/os/Packages/s/shim-x64-15.8-3.x86_64.rpm
SHIM_PACKAGE_FILE=$(ls shim-x64*.rpm | head -n 1)
# https://dl.fedoraproject.org/pub/fedora/linux/releases/43/Everything/x86_64/os/Packages/g/grub2-efi-x64-2.12-40.fc43.x86_64.rpm
GRUB_PACKAGE_FILE=$(ls grub2-efi-x64*.rpm | head -n 1)

mkdir -p "$BUILD_DIR" "$IMAGE_DIR"

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
    mkdir -p $ISO_DIR
    7z x "$ISO_FILE" "-o$ISO_DIR"
    echo "Unpacking ISO done."
}

unpack_shim_grub_package() {
    echo "Unpacking shim and grub package..."
    if [ -d "$SHIM_GRUB_DIR" ]; then
        rm -rf "$SHIM_GRUB_DIR"
    fi

    # need rpm2cpio
    mkdir -p "$SHIM_GRUB_DIR"
    cd "$SHIM_GRUB_DIR"
    rpm2cpio "$CURRENT_DIR/$SHIM_PACKAGE_FILE" | cpio -idmv
    rpm2cpio "$CURRENT_DIR/$GRUB_PACKAGE_FILE" | cpio -idmv
    cd -
    echo "Unpacking shim and grub package done."
}

copy_shim_grub_to_efi() {
    if [ ! -d "$SHIM_GRUB_DIR" ]; then
        unpack_shim_grub_package
    fi
    echo "Copying shim and grub files..."
    mkdir -p "$BOOT_DIR/EFI/boot"
    cp "$SHIM_GRUB_DIR"/boot/efi/EFI/fedora/shimx64.efi "$BOOT_DIR/EFI/boot/bootx64.efi"
    cp "$SHIM_GRUB_DIR"/boot/efi/EFI/fedora/mmx64.efi "$BOOT_DIR/EFI/boot/mmx64.efi"
    cp "$SHIM_GRUB_DIR"/boot/efi/EFI/fedora/grubx64.efi "$BOOT_DIR/EFI/boot/grubx64.efi"
    echo "Copying shim and grub files done."
}

unpack_initrd() {
    echo "Unpacking initrd..."
    mkdir -p "$INITRD_DIR"
    cd "$INITRD_DIR"
    zcat "$ISO_DIR/initrd.img" | cpio -id
    cd -
    echo "Unpacking initrd done."
}

patch_initrd() {
    cd "$INITRD_DIR"
    patch -p1 < "$DEVICE_FILES_DIR/initrd.patch"
    if [ ! -f "$DEVICE_FILES_DIR/dsdt.aml" ]; then
        iasl -ve -ts "$DEVICE_FILES_DIR/dsdt.dsl"
    fi
    mkdir -p kernel/firmware/acpi
    cp "$DEVICE_FILES_DIR/dsdt.aml" kernel/firmware/acpi/
    cd -
}

pack_initrd() {
    echo "Packing initrd..."
    cd "$INITRD_DIR"
    find . | cpio --create --format='newc' | gzip > "$INITRD_FILE"
    cd -
    rm -rf "$INITRD_DIR"
    echo "Packing initrd done."
}

unpack_kernel_package() {
    echo "Unpacking kernel package..."
    if [ -d "$KERNEL_DIR" ]; then
        rm -rf "$KERNEL_DIR"
    fi
    mkdir -p "$KERNEL_DIR"
    unzip -o "$KERNEL_PACKAGE_FILE" -d "$BUILD_DIR"
    FILE=$(ls "$BUILD_DIR"/kernel-*.tar.gz | head -n 1)
    tar -xzf "$FILE" -C "$KERNEL_DIR"
    echo "Unpacking kernel package done."
}

build_boot_image() {
    echo "Creating boot image..."
    mkdir -p "$IMAGE_DIR"
    truncate -s 64M "$IMAGE_DIR/boot.img"

    echo "Formatting boot image..."
    mkfs.vfat -F 32 -n ESP "$IMAGE_DIR/boot.img"
    echo "Formatting boot image done."

    echo "Mounting boot image..."
    if is_mount "$BOOT_DIR"; then
        # 如果已经挂载，先卸载
        umount -R "$BOOT_DIR"
    fi
    mkdir -p "$BOOT_DIR"
    mount -o loop "$IMAGE_DIR/boot.img" "$BOOT_DIR"
    echo "Mounting boot image done."

    echo "Copying boot files to boot image..."
    install -D "$SHIM_GRUB_DIR/boot/efi/EFI/BOOT/BOOTX64.EFI" "$BOOT_DIR/EFI/boot/bootx64.efi"
	install -D "$SHIM_GRUB_DIR/boot/efi/EFI/fedora/mmx64.efi" "$BOOT_DIR/EFI/boot/mmx64.efi"
	install -D "$SHIM_GRUB_DIR/boot/efi/EFI/fedora/grubx64.efi" "$BOOT_DIR/EFI/boot/grubx64.efi"
	install -D "$INITRD_FILE" "$BOOT_DIR/EFI/BlissOS/initrd.cpio.gz"
	install -D "$KERNEL_DIR"/vmlinuz-* "$BOOT_DIR/EFI/BlissOS/vmlinuz"
    cp -r "$OVERLAY_BOOT_DIR/"* "$BOOT_DIR/" || true
    echo "Copying boot files done."

    umount "$BOOT_DIR"
    rm -rf "$BOOT_DIR"
    echo "Boot image created at $IMAGE_DIR/boot.img"
}

unpack_system_image() {
    echo "Unpacking system image..."
    # image is squashfs, need squashfs-tools
    if [ -f "$ISO_DIR/system.sfs" ]; then
        unsquashfs -d "$BUILD_DIR/" "$ISO_DIR/system.sfs"
    elif [ -f "$ISO_DIR/system.efs" ]; then
        fsck.erofs --extract="$BUILD_DIR/" "$ISO_DIR/system.efs"
    fi
    echo "Unpacking system image done."
}

mount_system_image() {
    if is_mount "$SYSTEM_DIR"; then
        # 如果已经挂载，先卸载
        umount -R "$SYSTEM_DIR"
    fi
    mkdir -p "$SYSTEM_DIR"
    mount -o loop "$BUILD_DIR/system.img" "$SYSTEM_DIR"
}

copy_file_to_system() {
    if [ ! -d "$KERNEL_DIR" ]; then
        unpack_kernel_package
    fi
    modules_dir="$SYSTEM_DIR/system/lib/modules"
    if [ ! -d "$modules_dir" ]; then
        echo "Kernel modules directory not found: $modules_dir"
        exit 1
    fi
    echo "Copying kernel modules..."
    rm -rf "$modules_dir"/*
    cp -rf "$KERNEL_DIR"/lib/modules/* "$modules_dir/"
    echo "Copying kernel modules done."

    KEY_REMAP_SRC="$DEVIDE_FILES_DIR/mipad2_keymap.c"
    KEY_REMAP_DST="$SYSTEM_DIR/system/bin/key-remap"
    if [ ! -d "$KEY_REMAP_SRC" ]; then
        gcc "$KEY_REMAP_SRC" -o "$KEY_REMAP_DST" -static
    fi

    if [ -f "$OVERLAY_DIR/system_modify.sh" ]; then
        echo "Running system_modify.sh..."
        cd "$SYSTEM_DIR"; bash "$OVERLAY_DIR/system_modify.sh"; cd -
        echo "Running system_modify.sh done."
    fi

    cp -r "$OVERLAY_SYSTEM_DIR/"* "$SYSTEM_DIR/" || true
    chmod -R 755 "$SYSTEM_DIR"

    sync
}

pack_system_image() {
    echo "Packing system image..."
    if command -v mkfs.erofs &> /dev/null;then
        echo "erofs-utils found, using erofs for system image."
        # erofs, need erofs-utils
        mkfs.erofs -L system -zlzma "$IMAGE_DIR/system.img" "$SYSTEM_DIR"
    elif command -v mksquashfs &> /dev/null;then
        echo "squashfs-tools found, using squashfs for system image."
        # squashfs, need squashfs-tools
        mksquashfs "$SYSTEM_DIR" "$IMAGE_DIR/system.img" -comp xz -Xcompression-level 19 -b 1M -Xdict-size 1M -noappend
    else
        echo "erofs-utils and squashfs-tools not found, no package"
        umount "$SYSTEM_DIR"
        cp "$BUILD_DIR/system.img" "$IMAGE_DIR/system.img"
    fi

    umount "$SYSTEM_DIR" || true
    rm -rf "$SYSTEM_DIR"
    echo "Packing system image done."
}

create_data_image() {
    echo "Creating data image..."
    truncate -s 1G "$IMAGE_DIR/data.img"

    echo "Formatting data image..."
    if command -v mkfs.f2fs &> /dev/null;then
        echo "f2fs-tools found, using f2fs for data image."
        # f2fs, need f2fs-tools
        # mkfs.f2fs -S -f "$IMAGE_DIR/data.img"
        mkfs.f2fs -l data -f "$IMAGE_DIR/data.img"
    else
        echo "f2fs-tools not found, using ext4 for data image."
        mkfs.ext4 -L data -s -F "$IMAGE_DIR/data.img"
    fi
    mkdir -p "$DATA_DIR"
    mount -o loop "$IMAGE_DIR/data.img" "$DATA_DIR"
    cp -r "$OVERLAY_DATA_DIR/"* "$DATA_DIR/" || true
    umount "$DATA_DIR"

    echo "Formatting data image done."
}

convert_data_to_sparse() {
    img2simg "$IMAGE_DIR/data.img" "$IMAGE_DIR/data.simg"
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
    rm -rf "$SYSTEM_DIR/system/etc/binfmt_misc/*"
    rm -rf "$SYSTEM_DIR/system/vendor/etc/binfmt_misc/*"
    # 32 bit
    rm -rf "$SYSTEM_DIR/system/bin/houdini"
    rm -rf "$SYSTEM_DIR/system/bin/arm"
    rm -rf "$SYSTEM_DIR/system/vendor/bin/houdini"
    rm -rf "$SYSTEM_DIR/system/vendor/bin/arm"
    rm -rf "$SYSTEM_DIR/system/lib/libhoudini.so"
    rm -rf "$SYSTEM_DIR/system/lib/arm"
    rm -rf "$SYSTEM_DIR/system/vendor/lib/libhoudini.so"
    rm -rf "$SYSTEM_DIR/system/vendor/lib/arm"
    # 64 bit
    rm -rf "$SYSTEM_DIR/system/bin/houdini64"
    rm -rf "$SYSTEM_DIR/system/bin/arm64"
    rm -rf "$SYSTEM_DIR/system/vendor/bin/houdini64"
    rm -rf "$SYSTEM_DIR/system/vendor/bin/arm64"
    rm -rf "$SYSTEM_DIR/system/lib64/libhoudini.so"
    rm -rf "$SYSTEM_DIR/system/lib64/arm64"
    rm -rf "$SYSTEM_DIR/system/vendor/lib64/libhoudini.so"
    rm -rf "$SYSTEM_DIR/system/vendor/lib64/arm64"

    echo Delete libndk_translation
    # 32 bit
    rm -rf "$SYSTEM_DIR/system/bin/ndk_translation_program_runner_binfmt_misc"
    rm -rf "$SYSTEM_DIR/system/bin/arm"
    rm -rf "$SYSTEM_DIR/system/etc/ld.config.arm.txt"
    rm -rf "$SYSTEM_DIR/system/lib/libndk_translation.so"
    rm -rf "$SYSTEM_DIR/system/lib/libndk_translation_proxy_*.so"
    rm -rf "$SYSTEM_DIR/system/lib/arm"
    # 64 bit
    rm -rf "$SYSTEM_DIR/system/bin/ndk_translation_program_runner_binfmt_misc_arm64"
    rm -rf "$SYSTEM_DIR/system/bin/arm64"
    rm -rf "$SYSTEM_DIR/system/etc/ld.config.arm64.txt"
    rm -rf "$SYSTEM_DIR/system/lib64/libndk_translation.so"
    rm -rf "$SYSTEM_DIR/system/lib64/libndk_translation_proxy_*.so"
    rm -rf "$SYSTEM_DIR/system/lib64/arm64"

    chmod -R 777 "$libhoudini_dir"/*/prebuilts/
    cp -r "$libhoudini_dir"/*/prebuilts/* "$SYSTEM_DIR/system/vendor/"
    cd "$SYSTEM_DIR/system/"
        ln -s vendor/bin/houdini64 bin/houdini64
        ln -s vendor/bin/arm64 bin/arm64
        ln -s vendor/lib64/arm64 lib64/arm64
        ln -s vendor/lib64/libhoudini.so lib64/libhoudini.so
        ln -s vendor/bin/houdini bin/houdini
        ln -s vendor/bin/arm bin/arm
        ln -s vendor/lib/arm lib/arm
        ln -s vendor/lib/libhoudini.so lib/libhoudini.so
    cd -

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